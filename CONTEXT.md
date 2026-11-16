# CivicAudit AI - Comprehensive System & Architecture Context

> **Project Name:** CivicAudit AI - Agentic  
> **Version:** 4.0.0-Autonomous-Council  
> **Tagline:** Autonomous Public Procurement Oversight & Real-Time LLM Multi-Agent Tribunal  
> **Status:** Production-Ready Hackathon Release  
> **Target Problem:** Forensic detection of fraudulent price-gouging, collusive bid-rigging, and corrupt over-invoicing in public municipal procurement tenders.

---

## 1. Executive Summary & Core Mission

Every year, municipal governments and state institutions disburse over **$13 Trillion (15–20% of global GDP)** in public procurement. According to the United Nations Office on Drugs and Crime (UNODC) and the World Bank, **20% to 30% of public procurement budgets are siphoned off** due to fraudulent price-gouging, collusive supplier cartels, and disguised over-invoicing in voluminous Bill of Quantities (BOQ) spreadsheets.

**CivicAudit AI (v4.0)** introduces a **True Autonomous Multi-Agent Cognitive Tribunal** where three specialized LLM agents debate each procurement line-item in real-time, cross-referencing fresh live web market telemetry, weighing statutory public procurement allowances (VAT, AIT, warranty), and issuing binding judicial consensus rulings.

---

## 2. Repository Structure & Directory Organization

The workspace is organized into a clean decoupled full-stack architecture:
- `backend/`: Python FastAPI REST API server, Multi-Agent Cognitive Tribunal, and live market verification engine.
- `frontend/`: Modern Next.js 16 (React 19, Tailwind CSS 4, Lucide Icons) client dashboard.
- `_archive/`: Historical snapshots and legacy branches.

### Project Layout (`hackathon/`)

```text
hackathon/
├── backend/                       # Python FastAPI Server (Port 8000)
│   ├── config.py                  # Central audit thresholds, paths & AI provider settings
│   ├── conftest.py                # Pytest test suite configuration
│   ├── requirements.txt           # Production Python dependencies
│   ├── run_audit.py               # Headless Forensic CLI Entry Point
│   ├── web_server.py              # FastAPI Web API & CORS Platform
│   ├── .env.example               # Multi-provider environment configuration template
│   ├── core/
│   │   ├── models.py              # Pydantic v2 schemas with safe type coercions
│   │   ├── llm_client.py          # Universal multi-provider AI waterfall & Groq pool
│   │   ├── agents/
│   │   │   ├── auditor_orchestrator.py # Multi-stage pipeline orchestrator
│   │   │   └── consensus_council.py    # 3-Agent adversarial deliberation tribunal
│   │   ├── prompts/
│   │   │   └── system_prompts.py       # Specialized forensic persona prompts (Scout, Advocate, Arbiter)
│   │   └── tools/
│   │       ├── anomaly_engine.py       # Statistical variance & risk calculator
│   │       ├── dossier_generator.py    # Legal audit dossier markdown synthesizer
│   │       ├── file_extractor.py       # Zero-crash document parser (PDF, XLSX, CSV, JSON)
│   │       ├── market_verifier.py      # Live web search, 35% sanity guard & benchmark index
│   │       ├── procurement_parser.py   # Header-agnostic BOQ table & semantic parser
│   │       └── type_utils.py           # Bulletproof type converters (currency symbols, commas, blanks)
│   ├── data/sample_tenders/       # Ready-to-audit demo procurement dockets
│   │   ├── municipal_it_tender_2025.json
│   │   ├── civil_works_lighting_2025.json
│   │   └── real_world_tender.csv
│   ├── reports/                   # Auto-generated legal audit dossiers (.md)
│   └── tests/                     # 32 automated forensic & council verification tests
│
├── frontend/                      # Next.js 16 Client Platform (Port 3000)
│   ├── src/
│   │   ├── app/                   # App Router layout and main page
│   │   ├── components/            # Header, Ingestion, Metrics, Tribunal, Table, Settings
│   │   ├── lib/api.ts             # REST client connecting to http://127.0.0.1:8000
│   │   └── types/audit.ts         # TypeScript interfaces
│   ├── .env.local                 # Next.js config (NEXT_PUBLIC_API_URL=http://127.0.0.1:8000)
│   ├── package.json               # Next.js scripts and dependencies
│   └── README.md                  # Frontend developer guide
│
├── start-backend.ps1              # One-click launcher for backend
├── start-frontend.ps1             # One-click launcher for frontend
├── README.md                      # Root hackathon overview
└── CONTEXT.md                     # This document
```
├── reports/                      # Auto-generated legal audit dossiers (.md)
│   ├── Audit_Dossier_CSV-REAL_WORLD_TENDER.md
│   └── Audit_Dossier_MUNI-IT-2025-089.md
├── tests/                        # 32 automated forensic & council verification tests
│   ├── test_anomaly_engine.py
│   ├── test_dirty_data_edge_cases.py
│   ├── test_file_extractor.py
│   ├── test_groq_pool.py
│   ├── test_llm_council.py
│   ├── test_openrouter.py
│   ├── test_orchestrator.py
│   ├── test_procurement_parser.py
│   └── test_real_world_domain_fixes.py
└── ui/
    └── app.py                    # Streamlit alternate visual dashboard
```

---

## 3. End-to-End Technical Workflow

```
   [ Tender Docket: PDF / Excel / CSV / JSON / OCR Text ]
                          │
                          ▼
   ┌─────────────────────────────────────────────────────────┐
   │  STAGE 1: Ingestion & Zero-Crash Normalization          │
   │  • FileExtractor: PDF (stream decompress), Excel, CSV   │
   │  • ProcurementParserTool: 2-pass column detection       │
   │  • type_utils: Strips $, €, ৳, commas, dirty blanks     │
   │  • Output: List[ProcurementLineItem]                    │
   └──────────────────────────┬──────────────────────────────┘
                              │
                              ▼
   ┌─────────────────────────────────────────────────────────┐
   │  STAGE 2: Contemporaneous Market Verification           │
   │  • Normalizes search query (strips tender codes CIV-049)│
   │  • 4-tier live waterfall: DuckDuckGo -> Serper ->       │
   │    Tavily -> Forensic Wholesale Benchmark Index         │
   │  • Forensic Sanity Guard: 35% Floor Guard for Machinery │
   │  • Output: MarketBenchmark (fair market unit floor)     │
   └──────────────────────────┬──────────────────────────────┘
                              │
                              ▼
   ┌─────────────────────────────────────────────────────────┐
   │  STAGE 3: Adversarial Multi-Agent Deliberation Council  │
   │  • Turn 1: 🕵️‍♂️ Agent Scout (Wholesale floor investigator)│
   │  • Turn 2: 💼 Agent Advocate (Defends 25% VAT/AIT buffer)│
   │  • Turn 3: ⚖️ Chief Auditor (Issues binding JSON ruling) │
   │  • Modes: 'llm', 'hybrid', or 'deterministic' fallback  │
   │  • Output: Consensus Fair Price & Debate Transcript     │
   └──────────────────────────┬──────────────────────────────┘
                              │
                              ▼
   ┌─────────────────────────────────────────────────────────┐
   │  STAGE 4: Statistical Anomaly & Fiscal Loss Engine      │
   │  • Gouging % = ((Quoted - Consensus) / Consensus) * 100 │
   │  • Loss = max(0, (Quoted - Consensus) * Quantity)       │
   │  • Risk Tier: NORMAL, WARNING (>30%), CRITICAL (>75%)   │
   │  • Docket Risk Score (0 to 100)                         │
   │  • Output: List[AnomalyFinding]                         │
   └──────────────────────────┬──────────────────────────────┘
                              │
                              ▼
   ┌─────────────────────────────────────────────────────────┐
   │  STAGE 5: Forensic Dossier Synthesis & Presentation     │
   │  • Executive summary, legal citations (UNCAC Art 9, PPR)│
   │  • Immediate recommended actions (contract freeze, TEC) │
   │  • Delivered via:                                       │
   │    1. FastAPI Tailwind CSS Web Dashboard (Port 8000)    │
   │    2. Headless Rich CLI Table Format                    │
   │    3. Exportable Legal Markdown Dossier in reports/     │
   └─────────────────────────────────────────────────────────┘
```

---

## 4. Key Components Deep Dive

### 4.1. The 3-Agent Cognitive Tribunal (`core/agents/consensus_council.py`)
- **Agent Scout (Intel 🕵️‍♂️):** Challenges vendor prices by establishing the unadorned factory floor rate, exposing markups over wholesale.
- **Agent Advocate (Vendor Counsel 💼):** Counters Scout with statutory Public Procurement Rules: 15% VAT, 7.5% Advance Income Tax (AIT), 3-year warranty, logistics, and performance bank guarantees—granting a legitimate **25% statutory cushion**.
- **Chief Forensic Auditor (Judicial Arbiter ⚖️):** Adjudicates the debate, reconciling the floor and ceiling into a binding consensus rate, and returns strict JSON (`consensus_price`, `verdict`, `ruling_text`).

### 4.2. Operating Modes (`COUNCIL_MODE`)
- **`llm` (Full Cognitive Mode):** Every procurement line-item undergoes a multi-turn LLM deliberation.
- **`hybrid` (Adaptive Mode):** Suspected anomalies (>25% markup) trigger the live LLM tribunal; compliant items pass through millisecond statutory formulas.
- **`deterministic` (Statutory Fallback):** Zero-token mathematical formulas. Operates in air-gapped environments or when no API keys are present.

### 4.3. Universal AI Provider Cascade & Pool (`core/llm_client.py`)
- **Groq Multi-Key Rotation Pool:** Supports 1 to 10 keys (`GROQ_API_KEY`, `GROQ_API_KEY_2`..`10` or comma-separated). When a key encounters HTTP 429 rate limits, it automatically rotates to the next available key.
- **OpenRouter Free Tier Cascade:** Automatically cycles across 11 top free models (e.g., `llama-3.3-70b-instruct:free`, `gemini-2.0-flash-exp:free`, `deepseek-r1:free`).
- **Direct Providers:** DeepSeek, Google Gemini, OpenAI, Anthropic, Mistral, and local offline Ollama/vLLM (`http://localhost:11434/v1`).
- **Resilience:** Strict timeouts (5.0s–8.0s) ensure the web server never freezes; automatic graceful fallback to deterministic formulas if LLMs time out.

### 4.4. Contemporaneous Market Verification (`core/tools/market_verifier.py`)
- **Evidentiary Standard:** Zero cached prices to satisfy legal forensic standards.
- **Query Cleaning:** Strips internal tender codes (`CIV-049`, `IT-008`), test tags (`[FRAUD TEST]`), and generic descriptors.
- **35% Sanity Guard:** Discards scraping anomalies (such as \$6,000 toy excavators or scrap parts matching an industrial \$58,000 excavator). Scraped machinery rates must be $\ge 35\%$ of quoted price.
- **Regex Currency Enforcement:** Requires explicit currency markers (`$`, `USD`) to prevent confusing lighting specifications (`160,000 Lux`) with monetary prices.

### 4.5. Bulletproof Ingestion (`file_extractor.py`, `procurement_parser.py`, `type_utils.py`)
- **Formats:** PDF, Excel (`.xlsx`), CSV, JSON, raw OCR text.
- **Header-Agnostic Column Detection:** Uses a two-pass detection algorithm to identify item ID, name, specification, quantity, unit price, and total amount.
- **`type_utils.py`:** Coerces strings containing `$`, `€`, `£`, `৳`, `₹`, commas, scientific notation, and dirty whitespace into clean floats and integers without throwing exceptions.

---

## 5. Mathematical & Forensic Formulas

1. **Price Gouging Variance:**
   $$\text{Gouging Percentage} = \left( \frac{\text{Quoted Unit Price} - \text{Consensus Fair Price}}{\text{Consensus Fair Price}} \right) \times 100$$

2. **Taxpayer Fiscal Loss:**
   $$\text{Taxpayer Loss} = \max(0, \; (\text{Quoted Unit Price} - \text{Consensus Fair Price}) \times \text{Quantity})$$

3. **Statutory Tolerance Bounds:**
   $$\text{Fair Ceiling} = \text{Factory Wholesale Floor} \times 1.25 \quad (\text{15\% VAT} + \text{7.5\% AIT} + \text{Overhead})$$
   $$\text{Consensus Price} = \text{Factory Wholesale Floor} \times 1.22$$
   $$\text{If Quoted Price} \le \text{Fair Ceiling} \implies \mathbf{COMPLIANT}$$

4. **Docket Composite Risk Score (0 to 100):**
   $$\text{Risk Score} = (N_{\text{critical}} \times 25) + (N_{\text{warning}} \times 10) + \left( \frac{\text{Total Loss}}{\text{Total Budget}} \times 40 \right)$$
   - $\ge 70$: **CRITICAL / HIGH FRAUD RISK**
   - $40 - 69$: **ELEVATED CONCERN**
   - $< 40$: **ACCEPTABLE / LOW RISK**

---

## 6. How to Set Up and Start the Application

### 6.1. Environment Setup (Windows PowerShell)

> **Important Note for this Machine:**  
> Typing `python` directly in PowerShell triggers the Windows App Execution Alias (`Microsoft\WindowsApps\python.exe`), which fails. The true Python 3.13 installation is at:  
> `C:\Users\bijid\AppData\Local\Programs\Python\Python313\python.exe`

#### Step 1: Navigate to the Active Project
```powershell
cd C:\code\hackathon\CivicAudit-agentic-AI
```

#### Step 2: Create a Dedicated Virtual Environment
```powershell
& "C:\Users\bijid\AppData\Local\Programs\Python\Python313\python.exe" -m venv .venv
```

#### Step 3: Activate the Virtual Environment
```powershell
.\.venv\Scripts\Activate.ps1
```
*(If script execution is disabled on PowerShell, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first).*

#### Step 4: Install Dependencies
```powershell
pip install -r requirements.txt
```

#### Step 5: Configure Environment (`.env`)
```powershell
Copy-Item .env.example .env
```
*(Optional: Open `.env` and add your OpenRouter, Groq, or Gemini API keys. If no keys are added, the system automatically runs in deterministic mode without error).*

---

### 6.2. Starting the Application

#### Option A: Decoupled Full-Stack Architecture (Next.js @latest + FastAPI Backend)

**Terminal 1 (Backend API Server - Port 8000):**
```powershell
cd C:\code\hackathon\CivicAudit-agentic-AI
.\.venv\Scripts\Activate.ps1
python web_server.py
```
*FastAPI backend starts at `http://127.0.0.1:8000` with CORSMiddleware enabled.*

**Terminal 2 (Next.js Frontend Client - Port 3000):**
```powershell
cd C:\code\hackathon\CivicAudit-agentic-AI\frontend
pnpm run dev
```
*Next.js frontend starts at `http://localhost:3000` connected to `http://127.0.0.1:8000` via `NEXT_PUBLIC_API_URL`.*

#### Option B: Standalone FastAPI Glassmorphism UI
```powershell
python web_server.py
```
- Open browser at: **`http://127.0.0.1:8000`**

#### Option C: Headless CLI Forensic Audit
```powershell
# Fast statutory deterministic mode
python run_audit.py --mode deterministic

# Smart hybrid mode on real-world CSV tender
python run_audit.py --file data/sample_tenders/real_world_tender.csv --mode hybrid

# Full cognitive LLM multi-agent council mode
python run_audit.py --mode llm
```

#### Option D: Alternative Streamlit Dashboard
```powershell
streamlit run ui/app.py
```

---

### 6.3. Running the Test Suite
```powershell
pytest -v -p no:cacheprovider tests
```
Executes all 32 automated forensic tests covering:
- Ingestion of dirty and malformed data
- Multi-agent council deliberation and LLM timeout fallbacks
- Groq multi-key pool rotation and rate-limit handling
- Market verifier sanity guard and regex boundary filtering
- Anomaly calculation and composite risk scoring

---

## 7. Configuration Reference (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `COUNCIL_MODE` | `llm` | Operating mode: `llm`, `hybrid`, or `deterministic` |
| `LLM_PROVIDER` | `auto` | Selected provider: `auto`, `openrouter`, `groq`, `deepseek`, `gemini`, `openai`, `anthropic`, `mistral`, `local`, `custom` |
| `OPENROUTER_API_KEY` | *(empty)* | OpenRouter API Key |
| `OPENROUTER_MODEL` | `meta-llama/llama-3.3-70b-instruct:free` | Model identifier |
| `OPENROUTER_AUTO_FREE` | `true` | Automatically cycles through 11 free models |
| `GROQ_API_KEY` | *(empty)* | Primary Groq API Key |
| `GROQ_API_KEY_2`..`10` | *(empty)* | Additional Groq keys for automatic failover pool |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model identifier |
| `GEMINI_API_KEY` | *(empty)* | Google Gemini API Key |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Gemini model |
| `LOCAL_LLM_URL` | *(empty)* | e.g. `http://localhost:11434/v1` for offline Ollama |
| `WARNING_THRESHOLD_PERCENT` | `30.0` | Suspicious markup threshold |
| `CRITICAL_THRESHOLD_PERCENT`| `75.0` | Critical price-gouging flag threshold |
| `DEFAULT_CURRENCY` | `USD` | Display currency symbol |
