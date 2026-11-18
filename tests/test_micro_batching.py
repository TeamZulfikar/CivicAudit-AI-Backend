import pytest
from unittest.mock import patch
from core.models import ProcurementLineItem, MarketBenchmark
from core.agents.consensus_council import MultiAgentPriceCouncil
from core.agents.auditor_orchestrator import CivicAuditOrchestrator

def test_deliberate_batch_deterministic():
    """
    Verifies deliberate_batch handles a list of items and returns aligned results.
    """
    item1 = ProcurementLineItem(item_id="T-01", name="Office Chair", quantity=10, quoted_unit_price=160.0)
    bm1 = MarketBenchmark(item_name="Office Chair", fair_market_unit_price=150.0, price_source="GSA")

    item2 = ProcurementLineItem(item_id="T-02", name="Executive Desk", quantity=2, quoted_unit_price=800.0)
    bm2 = MarketBenchmark(item_name="Executive Desk", fair_market_unit_price=600.0, price_source="PWD")

    batch = [(item1, bm1), (item2, bm2)]
    results = MultiAgentPriceCouncil.deliberate_batch(batch)

    assert len(results) == 2
    consensus1, transcript1, _ = results[0]
    consensus2, transcript2, _ = results[1]

    assert consensus1 > 0
    assert len(transcript1) == 3
    assert consensus2 > 0
    assert len(transcript2) == 3

def test_deliberate_batch_llm_mock():
    """
    Verifies that deliberate_batch executes a single LLM call for a batch of items
    and parses individual consensus prices and arguments.
    """
    item1 = ProcurementLineItem(item_id="T-01", name="Server Rack 42U", quantity=4, quoted_unit_price=780.0)
    bm1 = MarketBenchmark(item_name="Server Rack 42U", fair_market_unit_price=437.50, price_source="GSA")

    item2 = ProcurementLineItem(item_id="T-02", name="Gold-Plated HDMI Cable", quantity=100, quoted_unit_price=120.0)
    bm2 = MarketBenchmark(item_name="Gold-Plated HDMI Cable", fair_market_unit_price=23.12, price_source="Wholesale")

    batch = [(item1, bm1), (item2, bm2)]

    mock_batch_json = """[
        {
            "item_id": "T-01",
            "consensus_price": 546.88,
            "scout_argument": "Quoted $780 is +78% above the $437.50 baseline floor.",
            "advocate_argument": "Enclosure includes statutory shipping and packaging allowances.",
            "auditor_ruling": "Consensus ceiling capped at $546.88 under 25% statutory cushion.",
            "verdict": "FLAGGED_OVERCHARGE"
        },
        {
            "item_id": "T-02",
            "consensus_price": 28.90,
            "scout_argument": "Severe gouging detected: $120 vs wholesale floor $23.12 (+419%).",
            "advocate_argument": "Gold plating cannot justify 400% markup.",
            "auditor_ruling": "Consensus ceiling established at $28.90.",
            "verdict": "CRITICAL_GOUGING"
        }
    ]"""

    with patch("core.llm_client.LLMClient.is_available", return_value=True), \
         patch("core.llm_client.LLMClient.complete", return_value=mock_batch_json):
        results = MultiAgentPriceCouncil.deliberate_batch(batch)

        assert len(results) == 2
        assert results[0][0] == 546.88
        assert "T-01" in results[0][1][2].argument or "Consensus" in results[0][1][2].argument
        assert results[1][0] == 28.90
        assert "CRITICAL_GOUGING" in results[1][1][2].argument

def test_orchestrator_with_micro_batching():
    """
    Verifies that CivicAuditOrchestrator runs end-to-end with batching enabled.
    """
    sample_data = {
        "tender_id": "TEST-BATCH-01",
        "title": "Batching Integration Test",
        "procuring_entity": "Municipal Directorate",
        "items": [
            {"item_id": "B-1", "name": "Cat6 Patch Cord 2m", "quantity": 50, "quoted_unit_price": 5.50},
            {"item_id": "B-2", "name": "USB Optical Mouse", "quantity": 20, "quoted_unit_price": 12.00},
            {"item_id": "B-3", "name": "27-inch IPS Monitor", "quantity": 5, "quoted_unit_price": 210.00}
        ]
    }

    orchestrator = CivicAuditOrchestrator()
    with patch("config.AuditConfig.COUNCIL_BATCH_SIZE", 2), \
         patch("core.llm_client.LLMClient.is_available", return_value=False):
        dossier = orchestrator.audit_tender(
            tender_id="TEST-BATCH-01",
            title="Batching Integration Test",
            procuring_entity="Municipal Directorate",
            tender_source_data=sample_data
        )

        assert dossier.tender_id == "TEST-BATCH-01"
        assert len(dossier.findings) == 3
        assert dossier.total_quoted_budget > 0
