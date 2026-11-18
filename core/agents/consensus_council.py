import json
import re
import logging
from typing import Tuple, List, Optional
from core.models import ProcurementLineItem, MarketBenchmark, AgentDebateTurn
from core.llm_client import LLMClient
from core.tools.type_utils import safe_float
from core.prompts.system_prompts import (
    SCOUT_AGENT_PROMPT,
    ADVOCATE_AGENT_PROMPT,
    CHIEF_AUDITOR_PROMPT
)
from config import AuditConfig

logger = logging.getLogger("CivicAudit.Council")

class MultiAgentPriceCouncil:
    """
    Autonomous LLM-Powered Multi-Agent Consensus Tribunal (v4.0 Agentic Engine).
    
    Orchestrates a real-time, multi-turn cognitive debate among 3 specialized AI personas:
    1. Agent Scout (🕵️‍♂️): Ruthless public investigator challenging inflated supplier quotes.
    2. Agent Advocate (💼): Procurement economist defending statutory allowances (VAT, AIT, warranty).
    3. Chief Auditor (⚖️): Judicial magistrate weighing evidence to issue a binding consensus ruling.
    
    Operating Modes (Configurable via COUNCIL_MODE):
    - 'llm': Full cognitive LLM agentic deliberation on every line-item.
    - 'hybrid': Full LLM debate on flagged anomalies; deterministic on compliant items.
    - 'deterministic': High-speed mathematical statutory formula fallback (zero token consumption).
    """

    @classmethod
    def deliberate(
        cls,
        item: ProcurementLineItem,
        raw_benchmark: MarketBenchmark
    ) -> Tuple[float, List[AgentDebateTurn], str]:
        """
        Main entry point for Council deliberation. Dispatches to selected operating mode.
        """
        mode = getattr(AuditConfig, "COUNCIL_MODE", "llm").lower()
        quoted = max(0.0, float(item.quoted_unit_price))
        floor = max(0.01, float(raw_benchmark.fair_market_unit_price))

        if mode == "deterministic" or not LLMClient.is_available():
            return cls.deliberate_deterministic(item, raw_benchmark)
        elif mode == "hybrid":
            # In hybrid mode: invoke LLM if quote exceeds standard 25% statutory cushion
            if quoted > (floor * 1.25):
                return cls.deliberate_llm(item, raw_benchmark)
            else:
                return cls.deliberate_deterministic(item, raw_benchmark)
        else:
            # Full LLM council mode
            return cls.deliberate_llm(item, raw_benchmark)

    @classmethod
    def deliberate_batch(
        cls,
        batch: List[Tuple[ProcurementLineItem, MarketBenchmark]]
    ) -> List[Tuple[float, List[AgentDebateTurn], str]]:
        """
        Micro-Batching & Map-Reduce Multi-Agent Consensus Tribunal:
        Evaluates a batch of line items (e.g. 15-25 items) in a single LLM prompt,
        reducing API roundtrips by 90-95% and eliminating per-item system prompt token overhead.
        """
        if not batch:
            return []

        mode = getattr(AuditConfig, "COUNCIL_MODE", "llm").lower()
        if mode == "deterministic" or not LLMClient.is_available():
            return [cls.deliberate_deterministic(it, bm) for it, bm in batch]

        if mode == "hybrid":
            results = [None] * len(batch)
            flagged_indices = []
            flagged_sub_batch = []
            for idx, (it, bm) in enumerate(batch):
                quoted = max(0.0, float(it.quoted_unit_price))
                floor = max(0.01, float(bm.fair_market_unit_price))
                if quoted > (floor * 1.25):
                    flagged_indices.append(idx)
                    flagged_sub_batch.append((it, bm))
                else:
                    results[idx] = cls.deliberate_deterministic(it, bm)

            if flagged_sub_batch:
                sub_results = cls._deliberate_batch_llm(flagged_sub_batch)
                for f_idx, res in zip(flagged_indices, sub_results):
                    results[f_idx] = res

            return results
        else:
            # Full LLM batch mode
            return cls._deliberate_batch_llm(batch)

    @classmethod
    def _deliberate_batch_llm(
        cls,
        batch: List[Tuple[ProcurementLineItem, MarketBenchmark]]
    ) -> List[Tuple[float, List[AgentDebateTurn], str]]:
        """
        Executes a single structured Micro-Batch LLM deliberation across multiple items.
        Falls back to deliberate_deterministic on any individual parsing failure.
        """
        items_payload = []
        for idx, (it, bm) in enumerate(batch):
            quoted = max(0.0, float(it.quoted_unit_price))
            floor = max(0.01, float(bm.fair_market_unit_price))
            markup = round(((quoted - floor) / floor * 100), 1) if floor > 0 else 0.0
            item_key = str(it.item_id or f"ITEM-{idx+1:03d}").strip()
            items_payload.append({
                "item_id": item_key,
                "name": it.name,
                "specification": it.specification,
                "quantity": it.quantity,
                "quoted_unit_rate": quoted,
                "wholesale_floor_rate": floor,
                "markup_percentage": markup,
                "benchmark_source": bm.price_source
            })

        system_instruction = (
            "You are the Supreme Forensic Procurement Tribunal comprising 3 adversarial personas:\n"
            "1. Agent Scout (Market Data Investigator): Challenges unjustified price gouging over wholesale trading floor.\n"
            "2. Agent Advocate (Procurement Economist): Defends legitimate statutory overheads (15% VAT, 7.5% AIT, freight, warranty ~25% cushion).\n"
            "3. Chief Auditor (Judicial Arbiter): Issues legally binding statutory consensus ceiling price in USD.\n\n"
            "Evaluate each procurement line item in the provided JSON batch.\n"
            "For each item, formulate:\n"
            "- 'item_id': str (must match input item_id exactly)\n"
            "- 'consensus_price': float (binding fair ceiling unit price in USD, usually between floor and floor * 1.25 unless higher is economically justified)\n"
            "- 'scout_argument': str (concise challenge on floor discrepancy)\n"
            "- 'advocate_argument': str (concise economic defense regarding tax/cushion)\n"
            "- 'auditor_ruling': str (judicial consensus verdict reasoning)\n"
            "- 'verdict': str ('APPROVED' | 'FLAGGED_OVERCHARGE' | 'CRITICAL_GOUGING')\n\n"
            "Return strictly a valid JSON array of objects, one per item in the batch. No conversational intro or markdown prose."
        )

        user_prompt = f"Batch Procurement Deliberation ({len(items_payload)} items):\n" + json.dumps(items_payload, indent=2)

        try:
            raw_resp = LLMClient.complete(
                prompt=user_prompt,
                system_instruction=system_instruction,
                temperature=0.2
            )
            if not raw_resp:
                raise ValueError("Empty response from LLM batch council")

            cleaned = raw_resp.strip()
            cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.MULTILINE)
            cleaned = re.sub(r'```\s*$', '', cleaned, flags=re.MULTILINE).strip()
            array_match = re.search(r'\[.*\]', cleaned, re.DOTALL)
            if array_match:
                cleaned = array_match.group(0)
            cleaned = re.sub(r',\s*\]', ']', cleaned)
            parsed_rulings = json.loads(cleaned)

            rulings_map = {}
            if isinstance(parsed_rulings, list):
                for r in parsed_rulings:
                    if isinstance(r, dict) and r.get("item_id"):
                        rulings_map[str(r["item_id"]).strip().lower()] = r

            results = []
            for idx, (it, bm) in enumerate(batch):
                item_key = str(it.item_id or f"ITEM-{idx+1:03d}").strip().lower()
                decision = rulings_map.get(item_key)
                if not decision and isinstance(parsed_rulings, list) and idx < len(parsed_rulings):
                    decision = parsed_rulings[idx] if isinstance(parsed_rulings[idx], dict) else None

                if decision:
                    quoted = max(0.0, float(it.quoted_unit_price))
                    floor_price = max(0.01, float(bm.fair_market_unit_price))
                    default_ceiling = round(floor_price * 1.25, 2)
                    consensus = safe_float(decision.get("consensus_price"), default_ceiling)
                    if consensus <= 0.0 or consensus < (floor_price * 0.5) or consensus > (max(quoted, floor_price) * 1.5):
                        consensus = default_ceiling

                    scout_text = str(decision.get("scout_argument") or f"Scout verified baseline trading floor at ${floor_price:,.2f}.").strip()
                    advocate_text = str(decision.get("advocate_argument") or f"Advocate notes statutory tax/overhead tolerance up to ${default_ceiling:,.2f}.").strip()
                    auditor_text = str(decision.get("auditor_ruling") or f"Tribunal consensus established at ${consensus:,.2f}.").strip()
                    verdict = str(decision.get("verdict") or "APPROVED").strip()

                    transcript = [
                        AgentDebateTurn(agent_name="Agent Scout (Intel)", role="Market Data Investigator", avatar="🕵️‍♂️", argument=scout_text),
                        AgentDebateTurn(agent_name="Agent Advocate (Vendor)", role="Procurement Economics Specialist", avatar="💼", argument=advocate_text),
                        AgentDebateTurn(agent_name="Chief Auditor (Arbiter)", role="Public Integrity Officer", avatar="⚖️", argument=f"Tribunal Ruling: {auditor_text} [VERDICT: {verdict}]")
                    ]
                    provider_name = getattr(LLMClient, "get_active_provider_name", lambda: "Multi-Agent Pool")()
                    notes = f"Batch Micro-Council Deliberation via {provider_name} (Consensus: ${consensus:,.2f})"
                    results.append((consensus, transcript, notes))
                else:
                    results.append(cls.deliberate_deterministic(it, bm))

            return results

        except Exception as e:
            logger.warning(f"Batch LLM deliberation failed ({e}). Falling back to deterministic council...")
            return [cls.deliberate_deterministic(it, bm) for it, bm in batch]

    @classmethod
    def deliberate_llm(
        cls,
        item: ProcurementLineItem,
        raw_benchmark: MarketBenchmark
    ) -> Tuple[float, List[AgentDebateTurn], str]:
        """
        Executes a real 3-turn adversarial LLM conversation.
        """
        quoted = max(0.0, float(item.quoted_unit_price))
        floor_price = max(0.01, float(raw_benchmark.fair_market_unit_price))
        scout_markup = ((quoted - floor_price) / floor_price * 100) if floor_price > 0 else 0.0

        try:
            # =================================================================
            # TURN 1: AGENT SCOUT (DATA INVESTIGATOR 🕵️‍♂️)
            # =================================================================
            scout_user_prompt = (
                f"Line Item: '{item.name}' (Specification: {item.specification})\n"
                f"Quoted Unit Price: ${quoted:,.2f}\n"
                f"Verified Wholesale Trading Floor: ${floor_price:,.2f} ({raw_benchmark.price_source})\n"
                f"Vendor Markup over Floor: {scout_markup:+.1f}%\n\n"
                f"Present your aggressive investigative challenge against this line item."
            )
            scout_msg = LLMClient.complete(
                prompt=scout_user_prompt,
                system_prompt=SCOUT_AGENT_PROMPT,
                max_tokens=220,
                temperature=0.3
            )
            if not scout_msg or len(scout_msg.strip()) < 10:
                raise ValueError("Empty response from Scout Agent")

            # =================================================================
            # TURN 2: AGENT ADVOCATE (VENDOR COUNSEL 💼)
            # =================================================================
            fair_ceiling = round(floor_price * 1.25, 2)
            advocate_user_prompt = (
                f"Line Item: '{item.name}' | Quoted Price: ${quoted:,.2f} | Wholesale Floor: ${floor_price:,.2f}\n"
                f"Maximum Justifiable Statutory Ceiling (+25% for 15% VAT, 7.5% AIT, overhead, warranty): ${fair_ceiling:,.2f}\n\n"
                f"Agent Scout has issued this challenge:\n\"{scout_msg.strip()}\"\n\n"
                f"Present your defense explaining what portion is justified by statutory taxes/logistics and whether the quoted price is defensible."
            )
            advocate_msg = LLMClient.complete(
                prompt=advocate_user_prompt,
                system_prompt=ADVOCATE_AGENT_PROMPT,
                max_tokens=240,
                temperature=0.3
            )
            if not advocate_msg or len(advocate_msg.strip()) < 10:
                raise ValueError("Empty response from Advocate Agent")

            # =================================================================
            # TURN 3: CHIEF FORENSIC AUDITOR (JUDICIAL ARBITER ⚖️)
            # =================================================================
            auditor_user_prompt = (
                f"Tender Line Item: '{item.name}' (Qty: {item.quantity})\n"
                f"Quoted Unit Price: ${quoted:,.2f} | Wholesale Floor: ${floor_price:,.2f}\n\n"
                f"[TRIBUNAL RECORD - ARGUMENT 1]\nAgent Scout (Intel): \"{scout_msg.strip()}\"\n\n"
                f"[TRIBUNAL RECORD - ARGUMENT 2]\nAgent Advocate (Vendor): \"{advocate_msg.strip()}\"\n\n"
                f"Issue your binding judicial consensus price and official tribunal verdict in the required JSON format."
            )
            auditor_resp = LLMClient.complete(
                prompt=auditor_user_prompt,
                system_prompt=CHIEF_AUDITOR_PROMPT,
                max_tokens=260,
                temperature=0.1
            )
            if not auditor_resp:
                raise ValueError("Empty response from Chief Auditor")

            # Parse Judicial Decision JSON
            consensus_price, verdict, ruling_text = cls._parse_auditor_decision(
                auditor_resp, floor_price, quoted
            )

            # Assemble Deliberation Transcript
            transcript = [
                AgentDebateTurn(
                    agent_name="Agent Scout (Intel)",
                    role="Market Data Investigator",
                    avatar="🕵️‍♂️",
                    argument=scout_msg.strip()
                ),
                AgentDebateTurn(
                    agent_name="Agent Advocate (Vendor)",
                    role="Procurement Economics Specialist",
                    avatar="💼",
                    argument=advocate_msg.strip()
                ),
                AgentDebateTurn(
                    agent_name="Chief Auditor (Arbiter)",
                    role="Public Integrity Officer",
                    avatar="⚖️",
                    argument=f"Tribunal Ruling: {ruling_text} [VERDICT: {verdict}]"
                )
            ]

            reconciliation_notes = (
                f"Autonomous LLM Council Deliberation (Scout Floor: ${floor_price:,.2f} | "
                f"Consensus Established: ${consensus_price:,.2f} via {LLMClient.get_active_provider_name()})"
            )
            return consensus_price, transcript, reconciliation_notes

        except Exception as e:
            logger.warning(f"LLM Agent Council encounter: {e}. Gracefully activating statutory deterministic fallback...")
            return cls.deliberate_deterministic(item, raw_benchmark)

    @classmethod
    def deliberate_deterministic(
        cls,
        item: ProcurementLineItem,
        raw_benchmark: MarketBenchmark
    ) -> Tuple[float, List[AgentDebateTurn], str]:
        """
        High-speed statutory formula deliberation (Fallback & Zero-Token Mode).
        """
        quoted = max(0.0, float(item.quoted_unit_price))
        floor_price = max(0.01, float(raw_benchmark.fair_market_unit_price))
        scout_markup = ((quoted - floor_price) / floor_price * 100) if floor_price > 0 else 0.0

        transcript: List[AgentDebateTurn] = []

        # Turn 1: Scout
        scout_msg = (
            f"Based on commercial wholesale registries ({raw_benchmark.price_source}), "
            f"the baseline trading floor for '{item.name}' is ${floor_price:,.2f}. "
            f"The vendor's quoted price of ${quoted:,.2f} represents a {scout_markup:+.1f}% markup."
        )
        transcript.append(AgentDebateTurn(
            agent_name="Agent Scout (Intel)",
            role="Market Data Investigator",
            avatar="🕵️‍♂️",
            argument=scout_msg
        ))

        # Turn 2: Advocate
        commercial_cushion = 1.25  # 25% statutory procurement allowance
        fair_ceiling = round(floor_price * commercial_cushion, 2)
        
        if quoted > fair_ceiling * 1.5:
            advocate_msg = (
                f"Even incorporating maximum statutory allowances (15% VAT, 7.5% AIT, 10% contractor margin, "
                f"3-year enterprise warranty, and delivery logistics), the justifiable statutory ceiling is ${fair_ceiling:,.2f}. "
                f"I cannot defend a quoted rate of ${quoted:,.2f}; this represents flagrant over-invoicing beyond all procurement rules."
            )
        elif quoted > fair_ceiling:
            advocate_msg = (
                f"While the factory wholesale floor is ${floor_price:,.2f}, municipal public contracts legally mandate "
                f"vendor VAT, AIT deduction, bank guarantees, and delivery overheads. A rate up to ${fair_ceiling:,.2f} (+25%) "
                f"is fully defensible under Public Procurement Rules."
            )
        else:
            advocate_msg = (
                f"The quoted rate of ${quoted:,.2f} is well within competitive commercial boundaries ({scout_markup:+.1f}%), "
                f"safely covered by statutory procurement allowances (VAT, AIT, warranty, and overhead)."
            )

        transcript.append(AgentDebateTurn(
            agent_name="Agent Advocate (Vendor)",
            role="Procurement Economics Specialist",
            avatar="💼",
            argument=advocate_msg
        ))

        # Turn 3: Chief Auditor
        consensus_price = max(0.01, round(floor_price * 1.22, 2))
        markup_over_consensus = ((quoted - consensus_price) / consensus_price * 100) if consensus_price > 0 else 0.0

        if markup_over_consensus > 50:
            auditor_msg = (
                f"Council Ruling: Consensus fair market ceiling established at ${consensus_price:,.2f}. "
                f"Quoted rate of ${quoted:,.2f} ({markup_over_consensus:+.1f}% over consensus ceiling, {scout_markup:+.1f}% over floor) "
                f"flagrantly breaches Public Procurement Due Diligence statutes. "
                f"VERDICT: CRITICAL FRAUD/GOUGING RISK. Immediate contract freeze recommended."
            )
        elif quoted > fair_ceiling or markup_over_consensus > 10.0:
            auditor_msg = (
                f"Council Ruling: Consensus fair rate established at ${consensus_price:,.2f}. "
                f"Quoted rate of ${quoted:,.2f} ({markup_over_consensus:+.1f}%) exceeds statutory tolerance. "
                f"VERDICT: ELEVATED ANOMALY. Itemized supplier cost breakdown required."
            )
        else:
            auditor_msg = (
                f"Council Ruling: Consensus fair rate confirmed at ${consensus_price:,.2f}. "
                f"Quoted rate of ${quoted:,.2f} is approved within statutory market tolerance ({scout_markup:+.1f}% over floor). "
                f"VERDICT: COMPLIANT."
            )

        transcript.append(AgentDebateTurn(
            agent_name="Chief Auditor (Arbiter)",
            role="Public Integrity Officer",
            avatar="⚖️",
            argument=auditor_msg
        ))

        reconciliation_summary = (
            f"Statutory Formula Deliberation (Scout Floor: ${floor_price:,.2f} | "
            f"Advocate Ceiling: ${fair_ceiling:,.2f} | Consensus: ${consensus_price:,.2f})"
        )
        return consensus_price, transcript, reconciliation_summary

    @classmethod
    def _parse_auditor_decision(
        cls,
        raw_text: str,
        floor_price: float,
        quoted_price: float
    ) -> Tuple[float, str, str]:
        """
        Safely extracts JSON response from Chief Auditor LLM output.
        """
        # Default statutory baseline
        default_consensus = max(0.01, round(floor_price * 1.22, 2))
        default_verdict = "COMPLIANT" if quoted_price <= (floor_price * 1.25) else ("CRITICAL FRAUD/GOUGING RISK" if quoted_price > (floor_price * 1.75) else "ELEVATED ANOMALY")
        default_ruling = f"Consensus fair rate confirmed at ${default_consensus:,.2f} based on statutory procurement evaluation."

        clean = raw_text.strip()
        if "```json" in clean:
            clean = clean.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in clean:
            clean = clean.split("```", 1)[1].split("```", 1)[0].strip()

        try:
            data = json.loads(clean)
            c_price = safe_float(data.get("consensus_price"), default=default_consensus)
            # Sanity bound: consensus cannot be less than 90% of floor or greater than quoted
            if c_price < (floor_price * 0.90) or c_price > (floor_price * 2.0):
                c_price = default_consensus
            verdict = str(data.get("verdict") or default_verdict).strip()
            ruling = str(data.get("ruling_text") or default_ruling).strip()
            return round(c_price, 2), verdict, ruling
        except Exception:
            # Regex extraction fallback if JSON format was broken
            price_match = re.search(r'"consensus_price"\s*:\s*([0-9\.]+)', raw_text)
            if price_match:
                c_price = safe_float(price_match.group(1), default_consensus)
                return round(c_price, 2), default_verdict, default_ruling
            return default_consensus, default_verdict, default_ruling
