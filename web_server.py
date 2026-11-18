import os
import json
import base64
import queue
import threading
import traceback
import logging
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn

from config import AuditConfig
from core.agents.auditor_orchestrator import CivicAuditOrchestrator
from core.tools.dossier_generator import DossierGeneratorTool
from core.tools.procurement_parser import ProcurementParserTool
from core.tools.file_extractor import FileExtractor
from core.llm_client import LLMClient

logger = logging.getLogger("CivicAudit.WebServer")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="CivicAudit AI Server")

# Enable CORS for decoupled frontend architectures (e.g. Next.js on port 3000)
allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
env_frontend = os.getenv("FRONTEND_URL", "").strip()
if env_frontend and env_frontend not in allowed_origins:
    allowed_origins.append(env_frontend)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|[\w\.-]+)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CustomTenderRequest(BaseModel):
    title: str = "Real-World Procurement Tender"
    procuring_entity: str = "Public Works & Procurement Directorate"
    tender_id: str = "REAL-TND-2025"
    raw_text: str

class FileUploadRequest(BaseModel):
    filename: str
    file_base64: str
    title: str = "Uploaded Tender Document"
    procuring_entity: str = "Public Procurement Authority"
    tender_id: str = "UPLOAD-TND-2025"

class StreamAuditRequest(BaseModel):
    mode: str = "sample"  # "sample" | "custom" | "upload"
    sample: Optional[str] = "municipal_it_tender_2025.json"
    title: Optional[str] = "Municipal Official Procurement Docket"
    procuring_entity: Optional[str] = "City Corporation Procurement Directorate"
    tender_id: Optional[str] = "TND-2025-089"
    raw_text: Optional[str] = None
    filename: Optional[str] = None
    file_base64: Optional[str] = None

class SettingsPayload(BaseModel):
    llm_provider: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    openrouter_model: Optional[str] = None
    openrouter_auto_free: Optional[bool] = None
    api_key: Optional[str] = None
    council_mode: Optional[str] = None

@app.get("/api/settings")
def get_settings():
    return {
        "active_brain": LLMClient.get_active_provider_name(),
        "llm_provider": AuditConfig.LLM_PROVIDER,
        "council_mode": getattr(AuditConfig, "COUNCIL_MODE", "llm"),
        "openrouter_model": AuditConfig.OPENROUTER_MODEL,
        "openrouter_auto_free": AuditConfig.OPENROUTER_AUTO_FREE,
        "has_openrouter_key": bool(AuditConfig.OPENROUTER_API_KEY),
        "has_groq_key": bool(AuditConfig.GROQ_API_KEY),
        "free_models": LLMClient.OPENROUTER_FREE_MODELS
    }

@app.post("/api/save_settings")
def save_settings(data: SettingsPayload):
    try:
        env_path = AuditConfig.DATA_DIR.parent / ".env"
        env_lines = []
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                env_lines = f.readlines()

        def update_or_add_env(key, val):
            nonlocal env_lines
            found = False
            for idx, line in enumerate(env_lines):
                if line.strip().startswith(f"{key}="):
                    env_lines[idx] = f"{key}={val}\n"
                    found = True
                    break
            if not found:
                env_lines.append(f"{key}={val}\n")

        if data.council_mode:
            c_mode = data.council_mode.lower().strip()
            AuditConfig.COUNCIL_MODE = c_mode
            os.environ["COUNCIL_MODE"] = c_mode
            update_or_add_env("COUNCIL_MODE", c_mode)

        if data.llm_provider:
            AuditConfig.LLM_PROVIDER = data.llm_provider
            os.environ["LLM_PROVIDER"] = data.llm_provider
            update_or_add_env("LLM_PROVIDER", data.llm_provider)

        if data.openrouter_model:
            AuditConfig.OPENROUTER_MODEL = data.openrouter_model
            os.environ["OPENROUTER_MODEL"] = data.openrouter_model
            update_or_add_env("OPENROUTER_MODEL", data.openrouter_model)

        if data.openrouter_auto_free is not None:
            AuditConfig.OPENROUTER_AUTO_FREE = data.openrouter_auto_free
            os.environ["OPENROUTER_AUTO_FREE"] = str(data.openrouter_auto_free).lower()
            update_or_add_env("OPENROUTER_AUTO_FREE", str(data.openrouter_auto_free).lower())

        if data.api_key and data.api_key.strip():
            k = data.api_key.strip()
            p = (data.llm_provider or AuditConfig.LLM_PROVIDER).lower()
            if p == "openrouter":
                AuditConfig.OPENROUTER_API_KEY = k
                os.environ["OPENROUTER_API_KEY"] = k
                update_or_add_env("OPENROUTER_API_KEY", k)
            elif p == "groq":
                AuditConfig.GROQ_API_KEY = k
                os.environ["GROQ_API_KEY"] = k
                update_or_add_env("GROQ_API_KEY", k)
            elif p == "deepseek":
                AuditConfig.DEEPSEEK_API_KEY = k
                os.environ["DEEPSEEK_API_KEY"] = k
                update_or_add_env("DEEPSEEK_API_KEY", k)
            elif p == "gemini":
                AuditConfig.GEMINI_API_KEY = k
                os.environ["GEMINI_API_KEY"] = k
                update_or_add_env("GEMINI_API_KEY", k)
            elif p == "openai":
                AuditConfig.OPENAI_API_KEY = k
                os.environ["OPENAI_API_KEY"] = k
                update_or_add_env("OPENAI_API_KEY", k)
            elif p == "anthropic":
                AuditConfig.ANTHROPIC_API_KEY = k
                os.environ["ANTHROPIC_API_KEY"] = k
                update_or_add_env("ANTHROPIC_API_KEY", k)

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(env_lines)

        return {
            "status": "success",
            "active_brain": LLMClient.get_active_provider_name(),
            "council_mode": getattr(AuditConfig, "COUNCIL_MODE", "llm")
        }
    except Exception as e:
        logger.error(f"Save settings error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": f"Failed to save settings: {str(e)}"})

@app.post("/api/test_ai")
def test_ai():
    try:
        active = LLMClient.get_active_provider_name()
        res = LLMClient.complete("Respond strictly with 'Audit Brain Online' and nothing else.")
        if res:
            return {"status": "success", "provider": active, "response": res.strip()}
        else:
            return {"status": "error", "provider": active, "error": "No response returned. Please verify your API key."}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/")
def api_root():
    return {
        "service": "CivicAudit AI - Multi-Agent Procurement Forensic Engine",
        "version": AuditConfig.VERSION,
        "status": "online",
        "active_brain": LLMClient.get_active_provider_name(),
        "council_mode": getattr(AuditConfig, "COUNCIL_MODE", "llm").upper(),
        "docs_url": "/docs",
        "openapi_url": "/openapi.json"
    }

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "active_brain": LLMClient.get_active_provider_name(),
        "council_mode": getattr(AuditConfig, "COUNCIL_MODE", "llm")
    }

@app.get("/api/audit")
def execute_audit(sample: str = "municipal_it_tender_2025.json"):
    try:
        # Security hardening: Prevent path traversal by isolating basename and enforcing directory boundary
        clean_filename = Path(sample).name
        sample_path = (AuditConfig.SAMPLES_DIR / clean_filename).resolve()
        samples_dir_resolved = AuditConfig.SAMPLES_DIR.resolve()

        if not sample_path.is_relative_to(samples_dir_resolved) or not sample_path.exists():
            sample_path = AuditConfig.SAMPLES_DIR / "municipal_it_tender_2025.json"

        logs = []
        def log_capture(phase, msg, data=None):
            logs.append(f"[{phase}] {msg}")

        orchestrator = CivicAuditOrchestrator(step_callback=log_capture)

        if sample_path.suffix.lower() == ".csv":
            items = ProcurementParserTool.parse_from_csv(sample_path)
            tender_data = {
                "tender_id": f"CSV-{sample_path.stem.upper()}",
                "title": f"Government Bill of Quantities ({sample_path.name})",
                "procuring_entity": "Municipal Public Works Department",
                "items": [it.model_dump() for it in items]
            }
        else:
            with open(sample_path, "r", encoding="utf-8") as f:
                tender_data = json.load(f)

        dossier = orchestrator.audit_tender(
            tender_id=tender_data.get("tender_id", "TND-999"),
            title=tender_data.get("title", "Public Municipal Tender"),
            procuring_entity=tender_data.get("procuring_entity", "Government Municipal Board"),
            tender_source_data=tender_data
        )

        markdown_dossier = DossierGeneratorTool.render_markdown(dossier)

        return JSONResponse(content={
            "dossier": dossier.model_dump(),
            "logs": logs,
            "markdown": markdown_dossier
        })
    except Exception as e:
        logger.error(f"Audit error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": f"Audit execution failed: {str(e)}"})

@app.post("/api/audit_custom")
def execute_custom_audit(req: CustomTenderRequest):
    try:
        logs = []
        def log_capture(phase, msg, data=None):
            logs.append(f"[{phase}] {msg}")

        orchestrator = CivicAuditOrchestrator(step_callback=log_capture)
        tender_data = {
            "tender_id": req.tender_id,
            "title": req.title,
            "procuring_entity": req.procuring_entity,
            "raw_text": req.raw_text
        }

        dossier = orchestrator.audit_tender(
            tender_id=req.tender_id,
            title=req.title,
            procuring_entity=req.procuring_entity,
            tender_source_data=tender_data
        )

        markdown_dossier = DossierGeneratorTool.render_markdown(dossier)

        return JSONResponse(content={
            "dossier": dossier.model_dump(),
            "logs": logs,
            "markdown": markdown_dossier
        })
    except Exception as e:
        logger.error(f"Custom audit error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": f"Custom audit execution failed: {str(e)}"})

@app.post("/api/upload_tender")
def upload_and_audit(req: FileUploadRequest):
    """
    Synchronous threadpool endpoint: Handles large uploads safely without event-loop blocking.
    """
    try:
        # Security hardening: Reject payloads larger than 25MB (approx 35MB base64)
        if len(req.file_base64) > 35 * 1024 * 1024:
            return JSONResponse(status_code=413, content={"error": "Uploaded file exceeds the maximum 25MB security limit."})

        logs = []
        def log_capture(phase, msg, data=None):
            logs.append(f"[{phase}] {msg}")

        logs.append(f"[INIT] Ingesting uploaded file: {req.filename}")

        # Decode base64
        base64_str = req.file_base64
        if "," in base64_str:
            base64_str = base64_str.split(",", 1)[1]
        file_bytes = base64.b64decode(base64_str)

        # Extract text from PDF / Excel / CSV
        extracted_text = FileExtractor.process_uploaded_file(req.filename, file_bytes)
        logs.append(f"[STAGE_1] Successfully processed {req.filename} ({len(extracted_text)} characters extracted)")

        tender_data = {
            "tender_id": req.tender_id,
            "title": req.title,
            "procuring_entity": req.procuring_entity,
            "raw_text": extracted_text
        }

        # If it's a CSV or Excel file, parse directly with Pandas (0 tokens)
        filename_lower = (req.filename or "").lower()
        if filename_lower.endswith(".csv") or filename_lower.endswith((".xlsx", ".xls")):
            try:
                csv_items = ProcurementParserTool.parse_from_csv(extracted_text)
                if csv_items and len(csv_items) >= 1:
                    tender_data["items"] = [it.model_dump() for it in csv_items]
            except Exception:
                pass
        # If it's a JSON file, parse directly
        elif filename_lower.endswith(".json"):
            try:
                json_obj = json.loads(extracted_text)
                if "items" in json_obj:
                    tender_data = json_obj
            except Exception:
                pass

        orchestrator = CivicAuditOrchestrator(step_callback=log_capture)
        dossier = orchestrator.audit_tender(
            tender_id=req.tender_id,
            title=req.title,
            procuring_entity=req.procuring_entity,
            tender_source_data=tender_data
        )

        markdown_dossier = DossierGeneratorTool.render_markdown(dossier)

        return JSONResponse(content={
            "dossier": dossier.model_dump(),
            "logs": logs,
            "markdown": markdown_dossier
        })
    except Exception as e:
        logger.error(f"Upload and audit error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": f"Document processing failed: {str(e)}"})

@app.post("/api/audit_stream")
async def execute_streaming_audit(req: StreamAuditRequest, request: Request):
    cancel_event = threading.Event()
    events = queue.Queue()
    accumulated_logs = []

    def check_cancelled() -> bool:
        return cancel_event.is_set()

    def log_capture(phase, msg, data=None, progress=None):
        if cancel_event.is_set():
            raise InterruptedError("Client disconnected. Aborting audit to preserve API tokens.")
        formatted = f"[{phase}] {msg}"
        accumulated_logs.append(formatted)
        events.put({
            "type": "progress",
            "phase": phase,
            "message": msg,
            "log": formatted,
            "progress": progress or {}
        })

    def run_investigation():
        try:
            if cancel_event.is_set():
                return

            orchestrator = CivicAuditOrchestrator(
                step_callback=log_capture,
                is_cancelled=check_cancelled
            )

            if req.mode == "sample":
                clean_filename = Path(req.sample or "municipal_it_tender_2025.json").name
                sample_path = (AuditConfig.SAMPLES_DIR / clean_filename).resolve()
                samples_dir_resolved = AuditConfig.SAMPLES_DIR.resolve()

                if not sample_path.is_relative_to(samples_dir_resolved) or not sample_path.exists():
                    sample_path = AuditConfig.SAMPLES_DIR / "municipal_it_tender_2025.json"

                if sample_path.suffix.lower() == ".csv":
                    items = ProcurementParserTool.parse_from_csv(sample_path)
                    tender_data = {
                        "tender_id": f"CSV-{sample_path.stem.upper()}",
                        "title": f"Government Bill of Quantities ({sample_path.name})",
                        "procuring_entity": "Municipal Public Works Department",
                        "items": [it.model_dump() for it in items]
                    }
                else:
                    with open(sample_path, "r", encoding="utf-8") as f:
                        tender_data = json.load(f)

                if cancel_event.is_set():
                    return

                dossier = orchestrator.audit_tender(
                    tender_id=tender_data.get("tender_id", req.tender_id or "TND-999"),
                    title=tender_data.get("title", req.title or "Public Municipal Tender"),
                    procuring_entity=tender_data.get("procuring_entity", req.procuring_entity or "Government Municipal Board"),
                    tender_source_data=tender_data
                )

            elif req.mode == "upload":
                if not req.file_base64:
                    raise ValueError("No file content provided for upload.")

                if len(req.file_base64) > 35 * 1024 * 1024:
                    raise ValueError("File size exceeds 25MB statutory limit.")

                base64_str = req.file_base64
                if "," in base64_str:
                    base64_str = base64_str.split(",", 1)[1]
                file_bytes = base64.b64decode(base64_str)

                extracted_text = FileExtractor.process_uploaded_file(req.filename or "uploaded.txt", file_bytes)
                tender_data = {
                    "tender_id": req.tender_id or "UPLOAD-TND-2025",
                    "title": req.title or "Uploaded Tender Document",
                    "procuring_entity": req.procuring_entity or "Public Procurement Authority",
                    "raw_text": extracted_text
                }
                upload_filename = (req.filename or "").lower()
                if upload_filename.endswith(".csv") or upload_filename.endswith((".xlsx", ".xls")):
                    try:
                        csv_items = ProcurementParserTool.parse_from_csv(extracted_text)
                        if csv_items and len(csv_items) >= 1:
                            tender_data["items"] = [it.model_dump() for it in csv_items]
                    except Exception:
                        pass
                else:
                    try:
                        clean_extracted = (extracted_text or "").strip()
                        if clean_extracted.startswith("{") or clean_extracted.startswith("["):
                            json_obj = json.loads(clean_extracted)
                            if isinstance(json_obj, dict) and any(k in json_obj for k in ["items", "line_items", "boq_items"]):
                                tender_data = json_obj
                            elif isinstance(json_obj, list):
                                tender_data["items"] = json_obj
                    except Exception:
                        pass

                if cancel_event.is_set():
                    return

                dossier = orchestrator.audit_tender(
                    tender_id=req.tender_id or "UPLOAD-TND-2025",
                    title=req.title or "Uploaded Tender Document",
                    procuring_entity=req.procuring_entity or "Public Procurement Authority",
                    tender_source_data=tender_data
                )

            else:  # "custom" raw text
                if cancel_event.is_set():
                    return

                tender_data = {
                    "tender_id": req.tender_id or "CUSTOM-TND-2025",
                    "title": req.title or "Real-World Procurement Tender",
                    "procuring_entity": req.procuring_entity or "Public Works & Procurement Directorate",
                    "raw_text": req.raw_text or ""
                }
                dossier = orchestrator.audit_tender(
                    tender_id=req.tender_id or "CUSTOM-TND-2025",
                    title=req.title or "Real-World Procurement Tender",
                    procuring_entity=req.procuring_entity or "Public Works & Procurement Directorate",
                    tender_source_data=tender_data
                )

            if cancel_event.is_set():
                return

            markdown_dossier = DossierGeneratorTool.render_markdown(dossier)

            events.put({
                "type": "complete",
                "dossier": dossier.model_dump(),
                "logs": accumulated_logs,
                "markdown": markdown_dossier
            })
        except InterruptedError:
            logger.info("Audit run successfully interrupted and halted to preserve API tokens.")
        except Exception as e:
            if not cancel_event.is_set():
                logger.error(f"Streaming audit error: {e}", exc_info=True)
                events.put({
                    "type": "error",
                    "error": str(e),
                    "traceback": traceback.format_exc()
                })
        finally:
            events.put(None)

    worker = threading.Thread(target=run_investigation, daemon=True)
    worker.start()

    async def event_stream():
        try:
            while True:
                # Active disconnect check to immediately release server resources and preserve API tokens
                if await request.is_disconnected():
                    logger.warning("Client disconnected from SSE stream. Triggering token-guard cancellation.")
                    cancel_event.set()
                    break

                try:
                    ev = events.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.2)
                    continue

                if ev is None:
                    break

                yield f"data: {json.dumps(ev)}\n\n"
        except (asyncio.CancelledError, GeneratorExit):
            logger.warning("SSE Stream connection terminated by client. Halting background agent worker.")
            cancel_event.set()
            raise
        except Exception as e:
            logger.error(f"Error during streaming: {e}")
            cancel_event.set()
        finally:
            cancel_event.set()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    print(f"Starting CivicAudit AI Web Platform on http://{host}:{port} ...")
    uvicorn.run(app, host=host, port=port)
