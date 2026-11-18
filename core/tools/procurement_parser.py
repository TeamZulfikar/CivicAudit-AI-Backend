import io
import json
import re
import csv
from pathlib import Path
from typing import List, Dict, Any, Union, Optional
try:
    import pandas as pd
except Exception:
    pd = None
from core.models import ProcurementLineItem
from core.llm_client import LLMClient
from core.tools.type_utils import safe_float, safe_int

def _notna(val: Any) -> bool:
    if val is None:
        return False
    if pd is not None:
        try:
            return bool(pd.notna(val))
        except Exception:
            pass
    s = str(val).strip().lower()
    return s not in ["", "nan", "none", "null", "n/a", "undefined"]

class ProcurementParserTool:
    """
    Production-Grade Ingestion Tool for Real-World Procurement Documents.
    Zero-Crash Architecture: All conversions are completely shielded against empty strings,
    currency markers, malformed tables, and incomplete data.
    
    Supports:
    1. Structured JSON dockets
    2. Excel & CSV Bill of Quantities (BOQ) spreadsheets
    3. AI LLM Semantic Extraction (for messy PDFs, scanned layouts, OCR text)
    4. Heuristic tabular and regex parsing fallback
    """
    name: str = "procurement_parser"
    description: str = "Extracts procurement line items from JSON, CSV, Excel, and raw PDF text/tables."

    @staticmethod
    def parse_from_json(json_data: Dict[str, Any]) -> List[ProcurementLineItem]:
        items: List[ProcurementLineItem] = []
        raw_items = json_data.get("items") or json_data.get("line_items") or json_data.get("boq_items") or []
        
        for idx, it in enumerate(raw_items, 1):
            if not isinstance(it, dict):
                continue
            name = str(it.get("name") or it.get("item_name") or it.get("description") or f"Procurement Item {idx}").strip()
            # Clean enclosing quotes, braces, colons from name
            name = re.sub(r'^["\'\{\}\:\,\s]+|["\'\{\}\:\,\s]+$', '', name).strip()
            
            # Skip metadata keys or summary headers
            if not name or any(name.lower().startswith(bad) for bad in [
                "tender_id", '"tender_id"', "title", '"title"', "procuring_entity",
                "items", "line_items", "total", "grand total", "subtotal", "sub-total", "vat", "tax", "{", "}"
            ]):
                continue
                
            spec = str(it.get("specification") or it.get("specs") or "Standard commercial specification").strip()
            spec = re.sub(r'^["\'\{\}\:\,\s]+|["\'\{\}\:\,\s]+$', '', spec).strip()
            category = str(it.get("category") or "General Goods").strip()
            quantity = safe_int(it.get("quantity", 1), default=1)
            if quantity <= 0:
                quantity = 1
            
            unit_price = safe_float(it.get("quoted_unit_price") or it.get("unit_price") or it.get("rate") or 0.0)
            total_price = safe_float(it.get("quoted_total_price") or it.get("total_price") or it.get("amount") or 0.0)
            
            # Cross-calculate and auto-correct unit vs total price
            if quantity > 1 and total_price > 0:
                # If unit price was accidentally set to total price or is 0
                if abs(unit_price - total_price) < 0.01 or unit_price > total_price or unit_price <= 0:
                    unit_price = round(total_price / quantity, 2)
                elif abs(unit_price * quantity - total_price) > (total_price * 0.4) and unit_price > (total_price / quantity * 2.5):
                    unit_price = round(total_price / quantity, 2)
            elif unit_price <= 0 and total_price > 0:
                unit_price = round(total_price / max(1, quantity), 2)
            elif total_price <= 0 and unit_price > 0:
                total_price = round(unit_price * max(1, quantity), 2)
                
            items.append(ProcurementLineItem(
                item_id=str(it.get("item_id") or f"BOQ-{idx:03d}"),
                name=name,
                specification=spec,
                category=category,
                quantity=quantity,
                quoted_unit_price=unit_price,
                quoted_total_price=total_price
            ))
        return items

    @staticmethod
    def parse_from_csv(csv_path_or_buffer: Union[str, Path, io.StringIO, Any]) -> List[ProcurementLineItem]:
        columns: List[str] = []
        rows: List[Dict[str, Any]] = []
        try:
            raw_text = ""
            if isinstance(csv_path_or_buffer, str):
                if "\n" in csv_path_or_buffer or "\r" in csv_path_or_buffer:
                    raw_text = csv_path_or_buffer
                else:
                    with open(csv_path_or_buffer, 'r', encoding='utf-8', errors='ignore') as f:
                        raw_text = f.read()
            elif isinstance(csv_path_or_buffer, Path):
                with open(csv_path_or_buffer, 'r', encoding='utf-8', errors='ignore') as f:
                    raw_text = f.read()
            elif hasattr(csv_path_or_buffer, "read"):
                raw_c = csv_path_or_buffer.read()
                raw_text = raw_c.decode('utf-8', errors='ignore') if isinstance(raw_c, bytes) else str(raw_c)

            cleaned_csv = re.sub(r'(?<=\d),(?=\d{3}\b)', '', raw_text)

            # Smart Header Row Auto-Detection:
            # Handles real-world tenders where rows 0-3 contain ministry titles, dates, or blanks
            lines = [line for line in cleaned_csv.splitlines() if line.strip()]
            header_row_idx = 0
            header_keywords = ["item", "description", "particular", "qty", "quantity", "rate", "price", "amount", "unit", "spec", "code"]
            for idx, line in enumerate(lines[:10]):
                lower_line = line.lower()
                matches = sum(1 for kw in header_keywords if kw in lower_line)
                if matches >= 2:
                    header_row_idx = idx
                    break

            if pd is not None:
                try:
                    df = pd.read_csv(io.StringIO(cleaned_csv), skiprows=header_row_idx, index_col=False)
                    columns = list(df.columns)
                    rows = [row.to_dict() for _, row in df.iterrows()]
                except Exception:
                    rows = []

            if not rows and cleaned_csv:
                csv_slice = "\n".join(lines[header_row_idx:]) if lines else cleaned_csv
                reader = csv.DictReader(io.StringIO(csv_slice))
                if reader.fieldnames:
                    columns = [str(f) for f in reader.fieldnames]
                    rows = list(reader)
        except Exception:
            return []

        id_col = None
        name_col = None
        spec_col = None
        category_col = None
        qty_col = None
        price_col = None
        total_col = None

        # Two-pass column detection: Pass 1 identifies specific columns, Pass 2 matches remaining
        for col in columns:
            c_str = str(col).lower().strip()
            c_clean = re.sub(r'[\(\)\[\]\$\€\৳\£\/_\-]', ' ', c_str).strip()
            tokens = c_clean.split()
            
            # 1. Price column detection (Must NOT be total)
            if any(k in c_clean for k in ["unit rate", "unit price", "unit cost", "rate unit", "price unit"]) or (
                any(k in tokens for k in ["rate", "price", "cost"]) and not any(t in tokens for t in ["total", "sum", "subtotal", "amount"])
            ):
                if not price_col:
                    price_col = col
            # 2. Total column detection
            elif any(k in c_clean for k in ["total price", "total amount", "quoted total", "line total", "subtotal", "sub total"]) or any(t in tokens for t in ["total", "amount"]):
                if not total_col:
                    total_col = col
            # 3. Quantity column detection
            elif any(k in tokens for k in ["qty", "quantity", "count", "units", "unit", "nos", "number", "volume"]):
                if not qty_col:
                    qty_col = col
            # 4. Item ID / Code column detection (Strict: must have id, code, or sl)
            elif any(k in c_clean for k in ["item id", "item code", "item_id", "item_code", "product code", "sl no", "sl.", "serial no"]) or (
                any(t in tokens for t in ["id", "code", "sl"]) and not any(t in tokens for t in ["description", "particulars", "name"])
            ):
                if not id_col:
                    id_col = col
            # 5. Specification column detection
            elif any(k in c_clean for k in ["specification", "specifications", "technical specs", "technical specification", "specs", "brand", "model"]):
                if not spec_col:
                    spec_col = col
            # 6. Category column detection
            elif any(k in c_clean for k in ["category", "categories", "department", "sector", "class"]):
                if not category_col:
                    category_col = col
            # 7. Item Name / Description column detection (Explicitly avoid pure ID/Code columns)
            elif any(k in c_clean for k in [
                "item description", "particulars", "description", "goods", "equipment",
                "asset", "material", "product name", "item name", "name of item"
            ]) or (
                any(t in tokens for t in ["name", "item", "title"]) and not any(t in tokens for t in ["id", "code", "sl", "no"])
            ):
                if not name_col:
                    name_col = col

        # Fallback if name_col was not detected: pick first column that is not price/total/qty
        if not name_col:
            for col in columns:
                if col not in [price_col, total_col, qty_col, id_col]:
                    name_col = col
                    break

        items: List[ProcurementLineItem] = []
        if name_col and (price_col or total_col):
            for idx, row in enumerate(rows):
                try:
                    raw_name = str(row.get(name_col) or "").strip()
                    if not raw_name or raw_name.lower() in [
                        "nan", "none", "null", "total", "grand total", "subtotal", "sub-total",
                        "vat", "tax", "signature", "authorized signature", "date",
                        "tender_id", "boq_id", "tender no", "status", "organization"
                    ] or any(raw_name.lower().startswith(m) for m in ['"tender_id"', "tender_id:", "tender_id"]):
                        continue

                    # Extract ID and clean product name
                    raw_id = str(row.get(id_col) or "").strip() if id_col and _notna(row.get(id_col)) else ""
                    if not raw_id or raw_id.lower() in ["nan", "none"]:
                        raw_id = f"CSV-{idx+1:03d}"

                    clean_name = raw_name
                    # Only search for prefix code if ID was not already provided by an ID column
                    if raw_id.startswith("CSV-") or not raw_id:
                        code_match = re.match(r'^([A-Z0-9\-_]{2,10})\s*[:\|\.]\s*(.+)$|^([A-Z0-9\-_]{2,10})\s+-\s+(.+)$', raw_name)
                        if code_match:
                            extracted_code = (code_match.group(1) or code_match.group(3)).strip()
                            clean_name = (code_match.group(2) or code_match.group(4)).strip()
                            raw_id = extracted_code

                    # If clean_name is purely a short code (e.g. "CIV-049") and spec_col has real text
                    if re.match(r'^[A-Z0-9\-_]{2,10}$', clean_name) and spec_col and _notna(row.get(spec_col)):
                        spec_text = str(row.get(spec_col) or "").strip()
                        if spec_text and len(spec_text) > 3:
                            if raw_id.startswith("CSV-") or not raw_id:
                                raw_id = clean_name
                            clean_name = spec_text

                    # Extract Specification and Category
                    spec = str(row.get(spec_col) or "").strip() if spec_col and _notna(row.get(spec_col)) else "Standard commercial specification"
                    category = str(row.get(category_col) or "").strip() if category_col and _notna(row.get(category_col)) else "Procurement Asset"
                        
                    qty = safe_int(row.get(qty_col), default=1) if qty_col and _notna(row.get(qty_col)) else 1
                    
                    unit_price = safe_float(row.get(price_col), default=0.0) if price_col and _notna(row.get(price_col)) else 0.0
                    total_price = safe_float(row.get(total_col), default=0.0) if total_col and _notna(row.get(total_col)) else 0.0
                    
                    # Unit vs Total Price Reconciliation:
                    # In real-world BOQs, line total is often erroneously placed in the unit rate column,
                    # or unit rate is left blank or identical to line total when qty > 1.
                    if qty > 1 and total_price > 0:
                        if abs(unit_price - total_price) < 0.01 or unit_price >= total_price or unit_price <= 0:
                            unit_price = round(total_price / qty, 2)
                        elif abs(unit_price * qty - total_price) > (total_price * 0.4) and unit_price > (total_price / qty * 2.5):
                            unit_price = round(total_price / qty, 2)
                    elif qty > 1 and unit_price > 0 and total_price <= 0:
                        total_price = round(unit_price * qty, 2)
                    elif unit_price <= 0 and total_price > 0:
                        unit_price = round(total_price / max(1, qty), 2)
                    elif total_price <= 0 and unit_price > 0:
                        total_price = round(unit_price * max(1, qty), 2)
                        
                    if unit_price > 0 or total_price > 0:
                        items.append(ProcurementLineItem(
                            item_id=raw_id,
                            name=clean_name,
                            specification=spec,
                            category=category,
                            quantity=qty,
                            quoted_unit_price=unit_price,
                            quoted_total_price=total_price
                        ))
                except Exception:
                    continue
                    continue
        return items

    @staticmethod
    def parse_from_text(raw_text: str) -> List[ProcurementLineItem]:
        """
        Multi-Stage Ingestion Pipeline:
        0. Direct JSON parsing if raw text is valid JSON (zero-token instant parse)
        1. AI LLM Extraction (high-accuracy semantic parsing for messy PDF / OCR text)
        2. Direct CSV / Tabular parsing if data resembles structured rows
        3. Heuristic regex and delimiter parsing fallback (zero-dependency)
        """
        if not raw_text or not raw_text.strip():
            return []

        # Stage 0: Direct JSON parsing check (handles raw JSON, markdown-wrapped JSON, and repaired JSON)
        clean_text = raw_text.strip()
        clean_json_text = re.sub(r'^```(?:json)?\s*', '', clean_text, flags=re.MULTILINE)
        clean_json_text = re.sub(r'```\s*$', '', clean_json_text, flags=re.MULTILINE).strip()

        if clean_json_text.startswith("{") or clean_json_text.startswith("["):
            try:
                parsed_json = json.loads(clean_json_text)
                if isinstance(parsed_json, dict):
                    if any(k in parsed_json for k in ["items", "line_items", "boq_items"]):
                        return ProcurementParserTool.parse_from_json(parsed_json)
                elif isinstance(parsed_json, list):
                    return ProcurementParserTool.parse_from_json({"items": parsed_json})
            except Exception:
                # Truncated or malformed JSON repair
                try:
                    obj_matches = re.findall(r'\{[^{}]*\}', clean_json_text)
                    recovered_items = []
                    for om in obj_matches:
                        try:
                            item_obj = json.loads(om)
                            if isinstance(item_obj, dict) and any(k in item_obj for k in ["name", "item_name", "description"]):
                                recovered_items.append(item_obj)
                        except Exception:
                            continue
                    if recovered_items:
                        return ProcurementParserTool.parse_from_json({"items": recovered_items})
                except Exception:
                    pass

        # Stage 1: Fast Structured CSV / Tabular Parsing via Pandas (Instant, Zero LLM Tokens)
        # If the input text is a valid CSV (commas with rows), parse directly with Pandas first.
        if "," in raw_text and ("\n" in raw_text or "\r" in raw_text) and "|" not in raw_text:
            try:
                csv_items = ProcurementParserTool.parse_from_csv(raw_text)
                if csv_items and len(csv_items) >= 1:
                    return csv_items
            except Exception:
                pass

        # Stage 2: AI LLM Extraction (High-accuracy semantic parsing for messy PDF / OCR / unstructured text)
        if LLMClient.is_available():
            try:
                llm_items = LLMClient.parse_messy_tender_text(raw_text)
                if llm_items and isinstance(llm_items, list):
                    extracted = []
                    for idx, it in enumerate(llm_items, 1):
                        if not isinstance(it, dict):
                            continue
                        raw_name = str(it.get("name") or it.get("item_name") or f"Procurement Item {idx}").strip()
                        if not raw_name or raw_name.lower() in ["total", "subtotal", "grand total", "vat", "tax"]:
                            continue
                        raw_id = str(it.get("item_id") or it.get("code") or f"AI-{idx:03d}").strip()
                        
                        # Separate prefix code if present
                        code_m = re.match(r'^([A-Z0-9\-_]{2,10})\s*[:\|\-\.\)]\s*(.+)$', raw_name)
                        if code_m:
                            raw_id = code_m.group(1).strip()
                            raw_name = code_m.group(2).strip()
                            
                        qty = safe_int(it.get("quantity", 1), default=1)
                        unit_price = safe_float(it.get("quoted_unit_price", 0.0), default=0.0)
                        total_price = safe_float(it.get("quoted_total_price", 0.0), default=0.0)

                        if qty > 1 and total_price > 0:
                            if abs(unit_price - total_price) < 0.01 or unit_price >= total_price or unit_price <= 0:
                                unit_price = round(total_price / qty, 2)
                            elif abs(unit_price * qty - total_price) > (total_price * 0.4) and unit_price > (total_price / qty * 2.5):
                                unit_price = round(total_price / qty, 2)
                        elif qty > 1 and unit_price > 0 and total_price <= 0:
                            total_price = round(unit_price * qty, 2)
                        elif unit_price <= 0 and total_price > 0:
                            unit_price = round(total_price / max(1, qty), 2)
                        elif total_price <= 0 and unit_price > 0:
                            total_price = round(unit_price * max(1, qty), 2)
                        
                        if unit_price > 0:
                            extracted.append(ProcurementLineItem(
                                item_id=raw_id,
                                name=raw_name,
                                specification=str(it.get("specification") or "AI Extracted Specification"),
                                category=str(it.get("category") or "AI Ingested"),
                                quantity=qty,
                                quoted_unit_price=unit_price,
                                quoted_total_price=total_price if total_price > 0 else round(unit_price * qty, 2)
                            ))
                    if extracted:
                        return extracted
            except Exception:
                pass

        # Stage 3: Deterministic Heuristic Line Parsing
        items: List[ProcurementLineItem] = []
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        item_counter = 1

        for line in lines:
            # Skip obvious header/footer rows
            if line.lower().startswith(("page ", "total", "subtotal", "grand total", "signature", "date:")):
                continue

            # Skip JSON structure rows and JSON metadata key-value pairs
            if re.match(r'^\s*["\']?[a-zA-Z0-9_\-]+["\']?\s*:\s*["\']?[^"\']+["\']?,?\s*$', line) or line in ["{", "}", "[", "]", "},", "],"]:
                continue
            if any(bad in line.lower() for bad in ['"tender_id"', '"title"', '"procuring_entity"', '"items"', '"line_items"', '"specification"']):
                continue

            # Case 1: Tabular split by tabs, pipes, or 2+ spaces
            parts = [p.strip() for p in re.split(r'[\t|]+|\s{2,}', line) if p.strip()]
            if len(parts) >= 3:
                # Detect if parts[0] is an ID/Code (e.g. "IT-008", "CIV-049", "1.")
                first_part = parts[0]
                is_id = bool(re.match(r'^[A-Z0-9\-_]{2,10}$', first_part) or re.match(r'^\d{1,4}[\.\)]?$', first_part))
                
                if is_id and len(parts) >= 3:
                    item_id = first_part.rstrip('.)')
                    cand_name = parts[1]
                    remaining = parts[2:]
                else:
                    item_id = f"BOQ-{item_counter:03d}"
                    cand_name = first_part
                    remaining = parts[1:]

                # Check if cand_name has a prefix code e.g. "CIV-049 - Excavator"
                if item_id.startswith("BOQ-") or not item_id:
                    code_m = re.match(r'^([A-Z0-9\-_]{2,10})\s*[:\|\.]\s*(.+)$|^([A-Z0-9\-_]{2,10})\s+-\s+(.+)$', cand_name)
                    if code_m:
                        extracted_code = (code_m.group(1) or code_m.group(3)).strip()
                        cand_name = (code_m.group(2) or code_m.group(4)).strip()
                        item_id = extracted_code

                # Separate numeric vs text columns from remaining
                valid_nums = []
                spec_tokens = []
                for p in remaining:
                    val = safe_float(p, default=-1.0)
                    if val >= 0 and re.search(r'\d', p):
                        valid_nums.append(val)
                    else:
                        spec_tokens.append(p)

                if len(valid_nums) >= 1:
                    if len(valid_nums) == 1:
                        qty = 1
                        unit_price = valid_nums[0]
                    else:
                        qty = safe_int(valid_nums[0], default=1)
                        unit_price = valid_nums[1]

                    spec = " ".join(spec_tokens) if spec_tokens else "Standard tender technical specifications"

                    if unit_price > 0 and len(cand_name) > 1:
                        items.append(ProcurementLineItem(
                            item_id=item_id,
                            name=cand_name,
                            specification=spec,
                            category="Procurement Asset",
                            quantity=qty,
                            quoted_unit_price=unit_price,
                            quoted_total_price=round(unit_price * qty, 2)
                        ))
                        item_counter += 1
                        continue

            # Case 2: Comma or @ or colon separated pattern
            # Matches: "CIV-049: 20-Ton Hydraulic Excavator, 3 units @ $58,000" or "Executive Laptop, 10 units @ $2500"
            match = re.search(
                r"^(?:([A-Z0-9\-_]{2,10})\s*[:\|\-\.\)]\s*)?([^,@|]+?)(?:,\s*|\s*\|\s*|\s*:\s*|\s*-\s*)(\d+)\s*(?:units?|pcs|qty|nos)?\s*(?:@|at)?\s*[\$€৳£]?\s*([0-9,]+(?:\.[0-9]{2})?)",
                line,
                re.IGNORECASE
            )
            if match:
                extracted_id = match.group(1).strip() if match.group(1) else f"BOQ-{item_counter:03d}"
                name = match.group(2).strip()
                qty = safe_int(match.group(3), default=1)
                unit_price = safe_float(match.group(4), default=0.0)
                
                if unit_price > 0 and len(name) > 2:
                    items.append(ProcurementLineItem(
                        item_id=extracted_id,
                        name=name,
                        specification="Standard procurement grade",
                        category="Municipal Asset",
                        quantity=qty,
                        quoted_unit_price=unit_price,
                        quoted_total_price=round(unit_price * qty, 2)
                    ))
                    item_counter += 1
                    continue

        return items
