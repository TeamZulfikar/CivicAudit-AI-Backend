import time
import logging
from typing import List, Dict, Any, Callable, Optional
from core.models import ProcurementLineItem, AnomalyFinding, AuditDossier
from core.tools.procurement_parser import ProcurementParserTool
from core.tools.market_verifier import MarketVerifierTool
from core.tools.anomaly_engine import AnomalyEngineTool
from core.tools.dossier_generator import DossierGeneratorTool
from core.agents.consensus_council import MultiAgentPriceCouncil
from config import AuditConfig

logger = logging.getLogger("CivicAudit.Orchestrator")

class CivicAuditOrchestrator:
    """
    Lead Forensic Agent Orchestrator.
    Manages autonomous multi-step investigation, multi-agent price debate councils,
    real-time live web inquiries, state reflection, and dossier synthesis.
    (Operates with Zero Cached Prices to uphold legal, fresh evidentiary standards).
    """
    def __init__(
        self,
        step_callback: Optional[Callable[..., None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None
    ):
        self.step_callback = step_callback or (lambda *args, **kwargs: None)
        self.is_cancelled = is_cancelled or (lambda: False)
        self.parser = ProcurementParserTool()
        self.verifier = MarketVerifierTool()
        self.anomaly_engine = AnomalyEngineTool()
        self.dossier_generator = DossierGeneratorTool()

    def check_cancel(self):
        if self.is_cancelled and self.is_cancelled():
            logger.warning("Audit pipeline cancellation detected. Halting further LLM calls to preserve tokens.")
            raise InterruptedError("Audit operation cancelled by user or client disconnect.")

    def log(self, phase: str, message: str, data: Any = None, progress: Optional[Dict[str, Any]] = None):
        self.check_cancel()
        logger.info(f"[{phase}] {message}")
        if self.step_callback:
            try:
                self.step_callback(phase, message, data, progress)
            except TypeError:
                self.step_callback(phase, message, data)

    def audit_tender(
        self,
        tender_id: str,
        title: str,
        procuring_entity: str,
        tender_source_data: Dict[str, Any]
    ) -> AuditDossier:
        """
        Executes the autonomous forensic audit pipeline with Multi-Agent Price Consensus
        and 100% fresh, contemporaneous live web market evaluations.
        """
        self.log(
            "INIT",
            f"Initializing CivicAudit Special Investigation for Tender #{tender_id}",
            progress={
                "percentage": 5,
                "stage": 1,
                "stage_name": "Initialization",
                "step": f"Setting up evidentiary workspace for Tender #{tender_id}"
            }
        )
        time.sleep(0.1)

        # STAGE 1: INGESTION & DECOMPOSITION
        self.log(
            "STAGE_1",
            "Parsing Bill of Quantities (BOQ) and extracting line-items...",
            progress={
                "percentage": 10,
                "stage": 1,
                "stage_name": "Document Decomposition",
                "step": "Extracting structured line-items and procurement specifications"
            }
        )
        if "items" in tender_source_data or any(k in tender_source_data for k in ["line_items", "boq_items"]):
            line_items = self.parser.parse_from_json(tender_source_data)
        else:
            raw_text = tender_source_data.get("raw_text", "")
            clean_raw = (raw_text or "").strip()
            if clean_raw.startswith("{") or clean_raw.startswith("["):
                try:
                    parsed_json = json.loads(clean_raw)
                    if isinstance(parsed_json, dict) and any(k in parsed_json for k in ["items", "line_items", "boq_items"]):
                        line_items = self.parser.parse_from_json(parsed_json)
                    elif isinstance(parsed_json, list):
                        line_items = self.parser.parse_from_json({"items": parsed_json})
                    else:
                        line_items = self.parser.parse_from_text(raw_text)
                except Exception:
                    line_items = self.parser.parse_from_text(raw_text)
            else:
                line_items = self.parser.parse_from_text(raw_text)

        total_items = max(1, len(line_items))
        self.log(
            "STAGE_1",
            f"Successfully extracted {len(line_items)} procurement line items.",
            line_items,
            progress={
                "percentage": 15,
                "stage": 1,
                "stage_name": "Document Decomposition",
                "step": f"Parsed {len(line_items)} line items ready for tribunal cross-examination",
                "total_items": len(line_items)
            }
        )
        time.sleep(0.1)

        # STAGE 2: MULTI-AGENT MARKET INTELLIGENCE & DEBATE
        self.log(
            "STAGE_2",
            "Convening Multi-Agent Price Deliberation Council...",
            progress={
                "percentage": 18,
                "stage": 2,
                "stage_name": "Multi-Agent Deliberation",
                "step": "Empaneling Scout, Advocate, and Arbiter personas",
                "total_items": len(line_items)
            }
        )
        findings: List[AnomalyFinding] = []
        batch_size = max(1, getattr(AuditConfig, "COUNCIL_BATCH_SIZE", 20))

        for batch_start in range(0, len(line_items), batch_size):
            self.check_cancel()
            batch_slice = line_items[batch_start:batch_start + batch_size]

            # Step A: Query wholesale benchmarks for all items in this micro-batch
            batch_benchmarks = []
            for sub_idx, item in enumerate(batch_slice):
                self.check_cancel()
                idx = batch_start + sub_idx + 1
                pct_start = int(18 + ((idx - 1) / total_items) * 72)
                anomalies_so_far = len([f for f in findings if f.risk_level != "LOW_RISK_COMPLIANT"])

                self.log(
                    "STAGE_2",
                    f"[{idx}/{len(line_items)}] Conducting Fresh Live Inquiry on '{item.name}' (Quoted: ${item.quoted_unit_price:,.2f})...",
                    progress={
                        "percentage": pct_start,
                        "stage": 2,
                        "stage_name": "Market Telemetry Inquiry",
                        "step": f"Inquiring wholesale benchmark for '{item.name}'",
                        "current_item_index": idx,
                        "total_items": len(line_items),
                        "current_item_name": item.name,
                        "quoted_price": item.quoted_unit_price,
                        "anomalies_count": anomalies_so_far
                    }
                )
                raw_benchmark = self.verifier.query_benchmark(item.name, item.specification, item.quoted_unit_price)
                batch_benchmarks.append(raw_benchmark)

            # Step B: Convene Micro-Batch Multi-Agent Council (single LLM prompt for entire batch)
            self.check_cancel()
            batch_tuples = list(zip(batch_slice, batch_benchmarks))
            batch_deliberations = MultiAgentPriceCouncil.deliberate_batch(batch_tuples)

            # Step C: Evaluate Anomaly Findings & Stream Deliberation Logs Per Item
            for sub_idx, (item, raw_benchmark, (consensus_price, debate_transcript, summary)) in enumerate(
                zip(batch_slice, batch_benchmarks, batch_deliberations)
            ):
                idx = batch_start + sub_idx + 1
                finding = self.anomaly_engine.evaluate_item(
                    item=item,
                    benchmark=raw_benchmark,
                    consensus_price=consensus_price,
                    debate_transcript=debate_transcript
                )
                findings.append(finding)

                pct_end = int(18 + (idx / total_items) * 72)
                anomalies_updated = len([f for f in findings if f.risk_level != "LOW_RISK_COMPLIANT"])

                self.log(
                    "DEBATE",
                    f"🏛️ [Agent Debate on '{item.name}']: Floor ${raw_benchmark.fair_market_unit_price:,.2f} -> "
                    f"Council Consensus Established at ${consensus_price:,.2f}",
                    debate_transcript,
                    progress={
                        "percentage": pct_end,
                        "stage": 2,
                        "stage_name": "Tribunal Consensus Established",
                        "step": f"Consensus price: ${consensus_price:,.2f} (Quoted: ${item.quoted_unit_price:,.2f})",
                        "current_item_index": idx,
                        "total_items": len(line_items),
                        "current_item_name": item.name,
                        "consensus_price": consensus_price,
                        "quoted_price": item.quoted_unit_price,
                        "anomalies_count": anomalies_updated
                    }
                )

                if finding.risk_level == "CRITICAL_RED_FLAG":
                    self.log(
                        "ALERT",
                        f"⚠️ CRITICAL GOUGING CONFIRMED on '{item.name}': "
                        f"Quoted ${item.quoted_unit_price:,.2f} vs Consensus ${consensus_price:,.2f} "
                        f"(+{finding.gouging_percentage:.1f}%)",
                        finding,
                        progress={
                            "percentage": pct_end,
                            "stage": 2,
                            "stage_name": "Critical Anomaly Detected",
                            "step": f"Flagged +{finding.gouging_percentage:.1f}% markup on '{item.name}'",
                            "current_item_index": idx,
                            "total_items": len(line_items),
                            "current_item_name": item.name,
                            "anomalies_count": anomalies_updated
                        }
                    )

        time.sleep(0.1)

        # STAGE 4: SYNTHESIS & DOSSIER GENERATION
        self.check_cancel()
        total_anomalies = len([f for f in findings if f.risk_level != "LOW_RISK_COMPLIANT"])
        self.log(
            "STAGE_4",
            "Synthesizing multi-agent council evidence and compiling final Audit Dossier...",
            progress={
                "percentage": 94,
                "stage": 3,
                "stage_name": "Dossier Synthesis",
                "step": "Synthesizing legal memorandum and statutory clawback recommendations",
                "total_items": len(line_items),
                "anomalies_count": total_anomalies
            }
        )
        dossier = self.dossier_generator.compile_dossier(
            tender_id=tender_id,
            title=title,
            procuring_entity=procuring_entity,
            findings=findings
        )

        self.log(
            "COMPLETED",
            f"Audit Complete! Overall Risk Score: {dossier.risk_score}/100. "
            f"Total Taxpayer Funds at Risk: ${dossier.potential_taxpayer_loss:,.2f}",
            dossier,
            progress={
                "percentage": 100,
                "stage": 4,
                "stage_name": "Audit Finalized",
                "step": f"Docket risk score: {dossier.risk_score}/100",
                "risk_score": dossier.risk_score,
                "total_items": len(line_items),
                "anomalies_count": total_anomalies
            }
        )

        return dossier
