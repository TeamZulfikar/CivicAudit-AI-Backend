import pytest
from core.models import ProcurementLineItem, MarketBenchmark
from core.tools.procurement_parser import ProcurementParserTool
from core.tools.market_verifier import MarketVerifierTool
from core.agents.consensus_council import MultiAgentPriceCouncil

def test_unit_price_auto_reconciliation_when_total_in_unit_column():
    """
    Real-world Issue 1:
    Quantity = 30, Total = $23,400.00, but CSV/BOQ placed $23,400.00 in the Unit Rate column.
    The parser MUST detect that unit_price >= total_price with qty > 1 and recalculate unit_price = $780.00.
    """
    csv_content = (
        "Item Name,Quantity,Unit Rate,Total Amount\n"
        "Commercial Desktop PC Core i5 13th Gen,30,$23,400.00,$23,400.00\n"
        "Executive Laptop Core i7,10,$11,500.00,$11,500.00\n"
    )
    items = ProcurementParserTool.parse_from_csv(csv_content)
    assert len(items) == 2

    # Desktop PC: 23,400 / 30 = 780.00
    assert items[0].quantity == 30
    assert items[0].quoted_unit_price == 780.00
    assert items[0].quoted_total_price == 23400.00

    # Laptop: 11,500 / 10 = 1,150.00
    assert items[1].quantity == 10
    assert items[1].quoted_unit_price == 1150.00
    assert items[1].quoted_total_price == 11500.00

def test_multi_pack_price_normalization_in_scraper():
    """
    Real-world Issue 2:
    Cat6 2m Patch Cord quoted at $45.00 matched a Box of 25 cables ($50.99).
    The price extractor MUST divide $50.99 by 25 to get $2.04/cable, catching the overcharge.
    """
    snippet_box_25 = "Cat6 UTP Patch Cord 2 Meter Factory Molded, Box of 25 cables - $50.99 free shipping"
    extracted = MarketVerifierTool._extract_candidate_prices(snippet_box_25)
    assert len(extracted) == 1
    # 50.99 / 25 = 2.04
    assert extracted[0] == 2.04

    snippet_10_pack = "Molded RJ45 Gigabit Ethernet Patch Cable 10-pack - $29.90"
    extracted_10 = MarketVerifierTool._extract_candidate_prices(snippet_10_pack)
    assert len(extracted_10) == 1
    # 29.90 / 10 = 2.99
    assert extracted_10[0] == 2.99

def test_search_query_normalizer_strips_parens_and_marketing_filler():
    """
    Real-world Issue 3:
    Parenthetical specs and marketing buzzwords choke commercial search engines.
    _build_search_query must clean:
    'Commercial Desktop PC Core i5 13th Gen (8GB RAM, 512GB SSD, 21.5-inch Monitor)'
    -> 'Desktop PC Core i5 13th Gen'
    """
    raw_desktop = "Commercial Desktop PC Core i5 13th Gen (8GB RAM, 512GB SSD, 21.5-inch Monitor)"
    cleaned = MarketVerifierTool._build_search_query(raw_desktop)
    assert "Commercial" not in cleaned
    assert "8GB RAM" not in cleaned
    assert "21.5-inch" not in cleaned
    assert "Desktop PC Core i5 13th Gen" in cleaned

    raw_patch = "Cat6 UTP Patch Cord 2 Meter Factory Molded"
    cleaned_patch = MarketVerifierTool._build_search_query(raw_patch)
    assert "Factory Molded" not in cleaned_patch
    assert "Cat6 UTP Patch Cord 2 Meter" in cleaned_patch

    raw_copier = "Heavy Duty A3 Monochrome Laser Multifunction Photocopier (35 ppm)"
    cleaned_copier = MarketVerifierTool._build_search_query(raw_copier)
    assert "Heavy Duty" not in cleaned_copier
    assert "35 ppm" not in cleaned_copier
    assert "A3 Monochrome Laser Multifunction Photocopier" in cleaned_copier

def test_quoted_price_bias_removed_from_aggregator():
    """
    Real-world Issue 4:
    If vendor quotes $23,400.00 for a desktop, the aggregator must NOT discard genuine
    $750 market prices just because $750 < $4,680.
    """
    candidate_prices = [680.0, 720.0, 750.0, 810.0, 24999.0]
    fair_price = MarketVerifierTool._filter_and_aggregate_prices(
        candidate_prices,
        query="Desktop PC Core i5",
        quoted_price=23400.0
    )
    # The aggregator must match category anchor (base $750), filter out the $24,999 extreme,
    # and return the true market median (~$735), NOT $24,999!
    assert fair_price is not None
    assert 650.0 <= fair_price <= 850.0
    assert fair_price != 24999.0

def test_json_metadata_not_parsed_as_items():
    """
    Real-world Issue 5:
    Document headers like 'tender_id', 'title', 'organization' in messy text or JSON
    must NEVER be extracted as line items.
    """
    messy_text = (
        '{\n'
        '  "tender_id": "TND-2025-089",\n'
        '  "title": "Municipal IT Infrastructure Tender",\n'
        '  "items": [\n'
        '    {\n'
        '      "name": "Standard Wired Optical USB Mouse (1000 DPI)",\n'
        '      "quantity": 100,\n'
        '      "quoted_unit_price": 55.0\n'
        '    }\n'
        '  ]\n'
        '}'
    )
    items = ProcurementParserTool.parse_from_text(messy_text)
    assert len(items) == 1
    assert "tender_id" not in items[0].name.lower()
    assert items[0].name == "Standard Wired Optical USB Mouse (1000 DPI)"
    assert items[0].quantity == 100
    assert items[0].quoted_unit_price == 55.0
