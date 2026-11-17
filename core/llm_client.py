import os
import json
import logging
import re
from typing import List, Dict, Any, Optional
import requests
from config import AuditConfig
from core.tools.type_utils import safe_float

logger = logging.getLogger("CivicAudit.LLMClient")

class LLMClient:
    """
    Universal Multi-Provider LLM Brain.
    Supports:
    1. OpenRouter (Automatic Cascade of all Free models + 200+ paid models)
    2. Groq (Ultra-fast Llama-3.3-70B & Llama-3.1-8B)
    3. DeepSeek Direct API (deepseek-chat & deepseek-reasoner)
    4. Google Gemini (Gemini 2.0 Flash / 1.5 Pro)
    5. OpenAI (GPT-4o / GPT-4o-mini)
    6. Anthropic Claude (Claude 3.5 Sonnet / Haiku)
    7. Mistral AI (Mistral Small / Codestral)
    8. Local LLM / Ollama (http://localhost:11434/v1 for 100% private offline auditing)
    9. Custom OpenAI-compatible gateways (Sambanova, Together.ai, Fireworks, vLLM)
    
    All calls enforce strict timeouts (5.0s - 8.0s) so the web server never freezes.
    """

    # Top free tier models on OpenRouter (cycled automatically when rate-limited)
    OPENROUTER_FREE_MODELS: List[str] = [
        "openrouter/free",
        "openrouter/auto",
        "meta-llama/llama-3.3-70b-instruct:free",
        "google/gemini-2.0-flash-exp:free",
        "deepseek/deepseek-r1:free",
        "meta-llama/llama-3.1-8b-instruct:free",
        "mistralai/mistral-small-24b-instruct-2501:free",
        "qwen/qwen-2.5-coder-32b-instruct:free",
        "google/gemini-2.0-pro-exp-02-05:free",
        "microsoft/phi-3-medium-128k-instruct:free",
        "meta-llama/llama-3.2-3b-instruct:free"
    ]

    # Class-level state for Groq pool rotation
    _groq_active_key_index: int = 0

    @classmethod
    def _is_valid_key(cls, k: Any) -> bool:
        if not k:
            return False
        s = str(k).strip()
        return len(s) > 8 and not s.lower().startswith("your_")

    @classmethod
    def is_available(cls) -> bool:
        return bool(
            cls._is_valid_key(AuditConfig.OPENROUTER_API_KEY) or
            cls._is_valid_key(os.getenv("OPENROUTER_API_KEY")) or
            bool(AuditConfig.get_groq_api_keys()) or
            cls._is_valid_key(AuditConfig.DEEPSEEK_API_KEY) or
            cls._is_valid_key(AuditConfig.GEMINI_API_KEY) or 
            cls._is_valid_key(AuditConfig.OPENAI_API_KEY) or
            cls._is_valid_key(AuditConfig.ANTHROPIC_API_KEY) or
            cls._is_valid_key(AuditConfig.MISTRAL_API_KEY) or
            bool(AuditConfig.LOCAL_LLM_URL) or
            bool(AuditConfig.CUSTOM_LLM_BASE_URL)
        )

    @classmethod
    def get_active_provider_name(cls) -> str:
        provider = (AuditConfig.LLM_PROVIDER or os.getenv("LLM_PROVIDER", "auto")).lower()
        if provider != "auto":
            return provider.upper()

        if cls._is_valid_key(AuditConfig.OPENROUTER_API_KEY) or cls._is_valid_key(os.getenv("OPENROUTER_API_KEY")):
            model_tag = AuditConfig.OPENROUTER_MODEL.split('/')[-1] if '/' in AuditConfig.OPENROUTER_MODEL else AuditConfig.OPENROUTER_MODEL
            return f"OpenRouter ({model_tag})"
        groq_keys = AuditConfig.get_groq_api_keys()
        if groq_keys:
            key_count = len(groq_keys)
            key_suffix = f" [{key_count} Keys Pool]" if key_count > 1 else ""
            return f"Groq (Llama-3.3 70B{key_suffix})"
        if cls._is_valid_key(AuditConfig.DEEPSEEK_API_KEY):
            return "DeepSeek V3"
        if cls._is_valid_key(AuditConfig.GEMINI_API_KEY):
            return "Google Gemini"
        if cls._is_valid_key(AuditConfig.OPENAI_API_KEY):
            return "OpenAI GPT-4o"
        if cls._is_valid_key(AuditConfig.ANTHROPIC_API_KEY):
            return "Anthropic Claude"
        if cls._is_valid_key(AuditConfig.MISTRAL_API_KEY):
            return "Mistral AI"
        if AuditConfig.LOCAL_LLM_URL:
            return f"Local Ollama ({AuditConfig.LOCAL_LLM_MODEL})"
        if AuditConfig.CUSTOM_LLM_BASE_URL:
            return "Custom Provider Gateway"
        return "Deterministic Procurement Engine"

    # =========================================================================
    # Provider 1: OpenRouter (with Automatic Free Tier Cascade)
    # =========================================================================
    @classmethod
    def _call_openrouter(cls, prompt: str, system_instruction: str = "") -> Optional[str]:
        api_key = AuditConfig.OPENROUTER_API_KEY or os.getenv("OPENROUTER_API_KEY")
        if not cls._is_valid_key(api_key):
            return None

        primary_model = AuditConfig.OPENROUTER_MODEL or "meta-llama/llama-3.3-70b-instruct:free"
        base_url = (AuditConfig.OPENROUTER_BASE_URL or "https://openrouter.ai/api/v1").rstrip("/") + "/chat/completions"

        headers = {
            "Authorization": f"Bearer {api_key.strip()}",
            "HTTP-Referer": "https://civicaudit.ai",
            "X-Title": "CivicAudit AI",
            "Content-Type": "application/json"
        }

        # Build candidate list: primary model first, followed by free models cascade
        candidate_models = [primary_model]
        if AuditConfig.OPENROUTER_AUTO_FREE:
            for fm in cls.OPENROUTER_FREE_MODELS:
                if fm not in candidate_models:
                    candidate_models.append(fm)

        for model in candidate_models:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 2048
            }
            try:
                resp = requests.post(base_url, headers=headers, json=payload, timeout=8.0)
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices and "message" in choices[0]:
                        return choices[0]["message"]["content"]
                elif resp.status_code in [429, 502, 503, 504]:
                    logger.info(f"OpenRouter model '{model}' rate-limited or busy (HTTP {resp.status_code}). Cascading to next free model...")
                    continue
                else:
                    logger.warning(f"OpenRouter model '{model}' returned HTTP {resp.status_code}: {resp.text[:120]}")
            except Exception as e:
                logger.debug(f"OpenRouter model '{model}' connection attempt failed: {e}. Trying next...")
                continue

        return None

    # =========================================================================
    # Provider 2: Groq (with Multi-Key Pool & Automatic Failover on Rate Limit)
    # =========================================================================
    @classmethod
    def _call_groq(cls, prompt: str, system_instruction: str = "") -> Optional[str]:
        keys = AuditConfig.get_groq_api_keys()
        if not keys:
            return None

        num_keys = len(keys)
        start_index = cls._groq_active_key_index % num_keys

        for attempt in range(num_keys):
            idx = (start_index + attempt) % num_keys
            api_key = keys[idx]
            key_display = f"Key #{idx + 1}/{num_keys}"

            try:
                from groq import Groq
            except ImportError:
                logger.error("groq package is not installed.")
                return None

            try:
                client = Groq(api_key=api_key, timeout=8.0)
                completion = client.chat.completions.create(
                    model=AuditConfig.GROQ_MODEL or "llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=2048
                )
                cls._groq_active_key_index = idx
                if attempt > 0:
                    logger.info(f"✅ [Groq Pool] Successfully recovered and served response using {key_display}.")
                return completion.choices[0].message.content

            except Exception as e:
                err_str = str(e).lower()
                is_rate_limit = any(
                    marker in err_str for marker in [
                        "rate limit", "rate_limit", "429", "tpm", "rpm", 
                        "tokens per minute", "requests per minute", "quota"
                    ]
                )

                if is_rate_limit:
                    next_idx = (idx + 1) % num_keys
                    logger.warning(
                        f"⚠️ [Groq Pool] {key_display} hit Rate Limit (HTTP 429). "
                        f"Auto-rotating to Key #{next_idx + 1}/{num_keys}..."
                    )
                    cls._groq_active_key_index = next_idx
                    continue  # Failover to next key in pool

                # For model unavailability or transient timeout, try lightweight fallback on same key
                logger.debug(f"Groq primary model error on {key_display}: {e}. Trying instant 8B fallback...")
                try:
                    client = Groq(api_key=api_key, timeout=5.0)
                    completion = client.chat.completions.create(
                        model="llama-3.1-8b-instant",
                        messages=[
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.1,
                        max_tokens=2048
                    )
                    cls._groq_active_key_index = idx
                    return completion.choices[0].message.content
                except Exception as fb_err:
                    fb_str = str(fb_err).lower()
                    if any(m in fb_str for m in ["rate", "429", "tpm", "rpm"]):
                        next_idx = (idx + 1) % num_keys
                        logger.warning(
                            f"⚠️ [Groq Pool] {key_display} hit Rate Limit on fallback (HTTP 429). "
                            f"Auto-rotating to Key #{next_idx + 1}/{num_keys}..."
                        )
                        cls._groq_active_key_index = next_idx
                        continue
                    logger.warning(f"Groq error with {key_display}: {fb_err}")
                    cls._groq_active_key_index = (idx + 1) % num_keys

        logger.error("❌ [Groq Pool] All configured Groq API keys exhausted or rate-limited.")
        return None

    # =========================================================================
    # Provider 3: DeepSeek Direct API
    # =========================================================================
    @classmethod
    def _call_deepseek(cls, prompt: str, system_instruction: str = "") -> Optional[str]:
        api_key = AuditConfig.DEEPSEEK_API_KEY or os.getenv("DEEPSEEK_API_KEY")
        if not cls._is_valid_key(api_key):
            return None

        url = "https://api.deepseek.com/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": AuditConfig.DEEPSEEK_MODEL or "deepseek-chat",
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 2048
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=8.0)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"DeepSeek direct API error: {e}")
        return None

    # =========================================================================
    # Provider 4: Google Gemini Direct API
    # =========================================================================
    @classmethod
    def _call_gemini(cls, prompt: str, system_instruction: str = "") -> Optional[str]:
        api_key = AuditConfig.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
        if not cls._is_valid_key(api_key):
            return None
        
        model = AuditConfig.GEMINI_MODEL or "gemini-2.0-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": f"{system_instruction}\n\n{prompt}"}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048}
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=8.0)
            if resp.status_code == 200:
                data = resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            logger.warning(f"Gemini API request failed: {e}")
        return None

    # =========================================================================
    # Provider 5: OpenAI Direct API
    # =========================================================================
    @classmethod
    def _call_openai(cls, prompt: str, system_instruction: str = "") -> Optional[str]:
        api_key = AuditConfig.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
        if not cls._is_valid_key(api_key):
            return None
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, timeout=8.0)
            completion = client.chat.completions.create(
                model=AuditConfig.OPENAI_MODEL or "gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )
            return completion.choices[0].message.content
        except Exception as e:
            logger.warning(f"OpenAI API request failed: {e}")
        return None

    # =========================================================================
    # Provider 6: Anthropic Claude Direct API
    # =========================================================================
    @classmethod
    def _call_anthropic(cls, prompt: str, system_instruction: str = "") -> Optional[str]:
        api_key = AuditConfig.ANTHROPIC_API_KEY or os.getenv("ANTHROPIC_API_KEY")
        if not cls._is_valid_key(api_key):
            return None

        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key.strip(),
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        payload = {
            "model": AuditConfig.ANTHROPIC_MODEL or "claude-3-5-haiku-20241022",
            "max_tokens": 2048,
            "system": system_instruction,
            "messages": [{"role": "user", "content": prompt}]
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=8.0)
            if resp.status_code == 200:
                return resp.json()["content"][0]["text"]
        except Exception as e:
            logger.warning(f"Anthropic Claude API error: {e}")
        return None

    # =========================================================================
    # Provider 7: Mistral AI Direct API
    # =========================================================================
    @classmethod
    def _call_mistral(cls, prompt: str, system_instruction: str = "") -> Optional[str]:
        api_key = AuditConfig.MISTRAL_API_KEY or os.getenv("MISTRAL_API_KEY")
        if not cls._is_valid_key(api_key):
            return None

        url = "https://api.mistral.ai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": AuditConfig.MISTRAL_MODEL or "mistral-small-latest",
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=8.0)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"Mistral API error: {e}")
        return None

    # =========================================================================
    # Provider 8: Local Offline LLM (Ollama / LM Studio)
    # =========================================================================
    @classmethod
    def _call_local_llm(cls, prompt: str, system_instruction: str = "") -> Optional[str]:
        base_url = AuditConfig.LOCAL_LLM_URL or os.getenv("LOCAL_LLM_URL")
        if not base_url:
            return None

        url = base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": AuditConfig.LOCAL_LLM_MODEL or "llama3",
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1
        }
        try:
            resp = requests.post(url, json=payload, timeout=10.0)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"Local LLM connection to {url} error: {e}")
        return None

    # =========================================================================
    # Provider 9: Generic Custom Provider Gateway
    # =========================================================================
    @classmethod
    def _call_custom_gateway(cls, prompt: str, system_instruction: str = "") -> Optional[str]:
        base_url = AuditConfig.CUSTOM_LLM_BASE_URL or os.getenv("CUSTOM_LLM_BASE_URL")
        if not base_url:
            return None

        url = base_url.rstrip("/") + "/chat/completions"
        api_key = AuditConfig.CUSTOM_LLM_API_KEY or os.getenv("CUSTOM_LLM_API_KEY", "")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key.strip()}"

        payload = {
            "model": AuditConfig.CUSTOM_LLM_MODEL or "default",
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=8.0)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"Custom LLM gateway error: {e}")
        return None

    # =========================================================================
    # Universal Orchestrator Dispatch
    # =========================================================================
    @classmethod
    def complete(cls, prompt: str, system_instruction: str = "", system_prompt: str = "", **kwargs) -> Optional[str]:
        system_instruction = system_prompt or system_instruction
        provider = (AuditConfig.LLM_PROVIDER or os.getenv("LLM_PROVIDER", "auto")).lower()

        provider_map = {
            "openrouter": cls._call_openrouter,
            "groq": cls._call_groq,
            "deepseek": cls._call_deepseek,
            "gemini": cls._call_gemini,
            "openai": cls._call_openai,
            "anthropic": cls._call_anthropic,
            "mistral": cls._call_mistral,
            "local": cls._call_local_llm,
            "custom": cls._call_custom_gateway
        }

        # If a specific provider is explicitly selected, call it first
        if provider in provider_map:
            res = provider_map[provider](prompt, system_instruction)
            if res:
                return res

        # Automated Cascade Order (Prioritizes OpenRouter & Groq, then fails over seamlessly)
        all_providers = [
            cls._call_openrouter,
            cls._call_groq,
            cls._call_deepseek,
            cls._call_gemini,
            cls._call_openai,
            cls._call_anthropic,
            cls._call_mistral,
            cls._call_local_llm,
            cls._call_custom_gateway
        ]

        for call_fn in all_providers:
            try:
                res = call_fn(prompt, system_instruction)
                if res:
                    return res
            except Exception:
                continue

        return None

    @classmethod
    def parse_messy_tender_text(cls, raw_text: str) -> Optional[List[Dict[str, Any]]]:
        if not cls.is_available() or not raw_text.strip():
            return None

        system_instruction = (
            "You are a forensic public procurement document extraction engine. "
            "Extract all procurement line items from the provided tender/BOQ document. "
            "CRITICAL INSTRUCTION: Separate the Item Code/ID from the Product Name. "
            "For example, if an item is 'CIV-049 20-Ton Hydraulic Excavator', 'item_id' is 'CIV-049' "
            "and 'name' is '20-Ton Hydraulic Excavator'. Never put just an item code in 'name'. "
            "Return strictly a raw JSON array of objects with keys: "
            "'item_id' (str), 'name' (str, full descriptive product name without code), "
            "'specification' (str, technical specifications/model), 'category' (str), "
            "'quantity' (int), 'quoted_unit_price' (float). "
            "Do not include markdown fences or conversational text."
        )

        prompt = f"Extract procurement line items from this raw tender text:\n\n{raw_text[:6000]}"
        raw_res = cls.complete(prompt, system_instruction)
        if not raw_res:
            return None

        try:
            cleaned = raw_res.strip()
            cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.MULTILINE)
            cleaned = re.sub(r'```\s*$', '', cleaned, flags=re.MULTILINE).strip()

            array_match = re.search(r'\[.*\]', cleaned, re.DOTALL)
            if array_match:
                cleaned = array_match.group(0)

            cleaned = re.sub(r',\s*([\]\}])', r'\1', cleaned)
            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                return parsed
        except Exception as e:
            logger.warning(f"Failed to parse LLM JSON extraction: {e}")
        return None

    @classmethod
    def resolve_semantic_category(cls, item_name: str, specification: str = "") -> Optional[Dict[str, Any]]:
        if not cls.is_available():
            return None

        system_instruction = (
            "You are a procurement catalog resolution engine. Given a line item from a government tender, "
            "identify its standard commercial product category, standard wholesale benchmark search term, "
            "and estimated fair retail price in USD. "
            "Return strictly a JSON object with keys: "
            "'normalized_category' (str), 'search_term' (str), 'estimated_fair_price_usd' (float)."
        )

        prompt = f"Item: {item_name}\nSpecification: {specification}"
        raw_res = cls.complete(prompt, system_instruction)
        if not raw_res:
            return None

        try:
            cleaned = raw_res.strip()
            cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.MULTILINE)
            cleaned = re.sub(r'```\s*$', '', cleaned, flags=re.MULTILINE).strip()

            obj_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if obj_match:
                cleaned = obj_match.group(0)

            cleaned = re.sub(r',\s*\}', '}', cleaned)
            return json.loads(cleaned)
        except Exception as e:
            logger.warning(f"Failed to parse LLM semantic resolution: {e}")
            return None

    @classmethod
    def generate_smart_search_queries(cls, item_name: str, specification: str = "", category: str = "") -> Optional[Dict[str, str]]:
        """
        AI Forensic Search Query Formulation:
        Transforms messy, verbose, or unstructured tender line item descriptions
        (e.g., 'Supply, fitting and fixing of 4K PTZ outdoor camera with IP66 casing and mounting bracket')
        into clean, highly targeted commercial wholesale search queries.
        
        Returns:
            {
                "primary_query": "4K Outdoor PTZ Security Camera IP66",
                "generic_query": "PTZ CCTV Security Camera"
            }
        """
        if not cls.is_available():
            return None

        system_instruction = (
            "You are a forensic commercial procurement price search engineer. "
            "Given an item from an invoice or tender (which often contains tender legalese like "
            "'Supply of', 'Providing and fixing', 'Turnkey', internal codes, or verbose warranties), "
            "formulate precise, commercial product search queries suitable for e-commerce and wholesale pricing lookup.\n"
            "Rules:\n"
            "1. 'primary_query': Extract the exact commercial product name and critical technical specs (model, size, capacity). "
            "Strip internal codes (e.g. CIV-049, IT-008), filler words ('Supply of', 'Installation', 'Turnkey basis'), and warranty text.\n"
            "2. 'generic_query': Provide the standard commercial product category name as a fallback.\n"
            "Return strictly a JSON object with keys 'primary_query' (str) and 'generic_query' (str). "
            "No conversational markdown, explanation, or commentary."
        )

        prompt = f"Item Name: {item_name}\nSpecification: {specification}\nCategory: {category}"
        raw_res = cls.complete(prompt, system_instruction)
        if not raw_res:
            return None

        try:
            cleaned = raw_res.strip()
            cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.MULTILINE)
            cleaned = re.sub(r'```\s*$', '', cleaned, flags=re.MULTILINE).strip()
            obj_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if obj_match:
                cleaned = obj_match.group(0)
            cleaned = re.sub(r',\s*\}', '}', cleaned)
            data = json.loads(cleaned)
            if isinstance(data, dict) and data.get("primary_query"):
                return {
                    "primary_query": str(data["primary_query"]).strip(),
                    "generic_query": str(data.get("generic_query", "")).strip()
                }
        except Exception as e:
            logger.warning(f"Failed to parse LLM search query formulation: {e}")
        return None

    @classmethod
    def extract_price_from_search_snippets(
        cls,
        product_query: str,
        snippets: List[Dict[str, str]],
        quoted_unit_price: float = 0.0
    ) -> Optional[Dict[str, Any]]:
        """
        AI Forensic Price Scraper / Evaluator:
        Reads web search titles and snippets (from DuckDuckGo / Serper / Tavily) to extract the
        genuine commercial/wholesale single-unit price in USD.
        Filters out delivery fees, accessories, monthly installments, or MSRP anchors.
        """
        if not cls.is_available() or not snippets:
            return None

        system_instruction = (
            "You are a forensic commercial procurement price auditor. "
            "You are given search result snippets from wholesale and retail suppliers for a specific product. "
            "Extract the genuine single-unit commercial or wholesale purchase price in USD.\n"
            "Strict Guidelines:\n"
            "1. Ignore shipping/delivery fees, accessory add-ons, monthly lease/installment amounts, and discount savings.\n"
            "2. Extract the price for 1 unit (e.g. if price is per box of 10, calculate price for 1 unit if stated).\n"
            "3. Reject irrelevant items, replacement spare parts, or toys/mini models.\n"
            "Return strictly JSON with keys:\n"
            "- 'extracted_price': float (or null if no genuine price is found)\n"
            "- 'confidence': float (between 0.70 and 0.98)\n"
            "- 'source_title': str (the title of the source where the price was found)"
        )

        formatted_snippets = []
        for idx, s in enumerate(snippets[:5], 1):
            title = s.get("title", "")
            snippet = s.get("body", "") or s.get("snippet", "")
            if title or snippet:
                formatted_snippets.append(f"Result {idx}: [{title}] - {snippet}")

        if not formatted_snippets:
            return None

        prompt = (
            f"Product: {product_query}\n"
            f"Tender Quoted Unit Price: ${quoted_unit_price:,.2f}\n"
            f"Search Snippets:\n" + "\n".join(formatted_snippets)
        )

        raw_res = cls.complete(prompt, system_instruction)
        if not raw_res:
            return None

        try:
            cleaned = raw_res.strip()
            cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.MULTILINE)
            cleaned = re.sub(r'```\s*$', '', cleaned, flags=re.MULTILINE).strip()
            obj_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if obj_match:
                cleaned = obj_match.group(0)
            cleaned = re.sub(r',\s*\}', '}', cleaned)
            data = json.loads(cleaned)
            if isinstance(data, dict):
                price = safe_float(data.get("extracted_price"), 0.0)
                if price > 0.0:
                    return {
                        "fair_price": price,
                        "confidence": min(0.98, max(0.70, safe_float(data.get("confidence"), 0.92))),
                        "source_title": str(data.get("source_title", "Live Commercial Web Listing"))
                    }
        except Exception as e:
            logger.warning(f"Failed to parse LLM price extraction: {e}")
        return None
