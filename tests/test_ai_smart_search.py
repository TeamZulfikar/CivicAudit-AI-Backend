import pytest
from unittest.mock import patch, MagicMock
from core.tools.market_verifier import MarketVerifierTool
from core.llm_client import LLMClient
from core.models import MarketBenchmark

def test_ai_search_query_generation_mock():
    """
    Verifies that get_optimized_queries uses LLMClient to return clean queries
    and falls back to deterministic regex when LLM is unavailable.
    """
    # 1. Fallback / deterministic behavior
    with patch.object(LLMClient, "is_available", return_value=False):
        queries = MarketVerifierTool.get_optimized_queries(
            item_name="CIV-049 - 20-Ton Hydraulic Excavator",
            specification="Crawler Mounted 150HP Heavy Duty"
        )
        assert len(queries) >= 1
        assert "CIV-049" not in queries[0]
        assert "20-Ton Hydraulic Excavator" in queries[0]

    # 2. When LLM is available, returns AI-optimized primary and generic queries
    with patch.object(LLMClient, "is_available", return_value=True), \
         patch.object(LLMClient, "generate_smart_search_queries", return_value={
             "primary_query": "CAT 20-Ton Hydraulic Crawler Excavator",
             "generic_query": "Hydraulic Excavator Heavy Equipment"
         }):
        queries = MarketVerifierTool.get_optimized_queries(
            item_name="Supply and commissioning of CIV-049 20-Ton Hydraulic Excavator",
            specification="Standard commercial specification with 3 years warranty"
        )
        assert "CAT 20-Ton Hydraulic Crawler Excavator" in queries
        assert "Hydraulic Excavator Heavy Equipment" in queries

def test_extract_price_from_search_snippets_logic():
    """
    Verifies that extract_price_from_search_snippets parses JSON output properly
    and filters out noise.
    """
    snippets = [
        {"title": "Dell OptiPlex 7090 Desktop", "body": "Special wholesale price $650.00 each for bulk municipal orders. Free shipping."},
        {"title": "Accessories", "body": "Power cable adapter only $15.00."}
    ]

    mock_llm_response = '{"extracted_price": 650.0, "confidence": 0.95, "source_title": "Dell Wholesale Direct"}'

    with patch.object(LLMClient, "is_available", return_value=True), \
         patch.object(LLMClient, "complete", return_value=mock_llm_response):
        result = LLMClient.extract_price_from_search_snippets("Dell OptiPlex 7090 Desktop", snippets, 850.0)
        assert result is not None
        assert result["fair_price"] == 650.0
        assert result["confidence"] >= 0.90
        assert "Dell Wholesale Direct" in result["source_title"]

def test_multi_query_search_dispatch():
    """
    Verifies that _search_live_web_price accepts multiple candidate queries and searches them sequentially.
    """
    with patch.object(MarketVerifierTool, "_search_duckduckgo") as mock_ddg, \
         patch.object(MarketVerifierTool, "_search_serper", return_value=None), \
         patch.object(MarketVerifierTool, "_search_tavily", return_value=None):
        
        # First query returns None, second query returns valid price
        mock_ddg.side_effect = [
            None,
            {"fair_price": 45.0, "source": "Fresh Web Intel", "evidence": "https://example.com", "confidence": 0.92}
        ]

        res = MarketVerifierTool._search_live_web_price(["Unfindable Query 12345", "Standard Commercial Desk Chair"], 50.0)
        assert res is not None
        assert res["fair_price"] == 45.0
        assert mock_ddg.call_count == 2
