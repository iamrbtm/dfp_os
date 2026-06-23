from __future__ import annotations


import requests

from app.services.receipt_providers.base import BaseReceiptProvider, ProviderResult


AI_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "merchant_name": {"type": "string"},
        "store_name": {"type": "string"},
        "store_number": {"type": "string"},
        "address_line_1": {"type": "string"},
        "address_line_2": {"type": "string"},
        "city": {"type": "string"},
        "state": {"type": "string"},
        "postal_code": {"type": "string"},
        "phone": {"type": "string"},
        "receipt_number": {"type": "string"},
        "transaction_number": {"type": "string"},
        "date_time": {"type": "string"},
        "timezone": {"type": "string"},
        "subtotal": {"type": "number"},
        "tax_total": {"type": "number"},
        "fee_total": {"type": "number"},
        "discount_total": {"type": "number"},
        "tip_total": {"type": "number"},
        "deposit_total": {"type": "number"},
        "rounding_adjustment": {"type": "number"},
        "grand_total": {"type": "number"},
        "payment_method": {"type": "string"},
        "payment_card_brand": {"type": "string"},
        "payment_card_last4": {"type": "string"},
        "currency": {"type": "string"},
        "line_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "sku": {"type": "string"},
                    "upc": {"type": "string"},
                    "quantity": {"type": "number"},
                    "unit_price": {"type": "number"},
                    "line_total": {"type": "number"},
                    "line_discount": {"type": "number"},
                    "line_tax": {"type": "number"},
                    "taxable": {"type": "boolean"},
                    "confidence": {"type": "number"},
                },
            },
        },
        "confidence_overall": {"type": "number"},
        "low_confidence_fields": {"type": "array", "items": {"type": "string"}},
    },
}


MOCK_RESPONSE = {
    "merchant_name": "Mock Supermarket",
    "store_name": "Mock Supermarket #42",
    "store_number": "42",
    "address_line_1": "123 Mock Street",
    "city": "Mockville",
    "state": "MS",
    "postal_code": "12345",
    "phone": "(555) 123-4567",
    "receipt_number": "MOCK-001",
    "transaction_number": "TXN-MOCK-001",
    "date_time": "2026-01-15T14:30:00",
    "timezone": "America/Chicago",
    "subtotal": 42.50,
    "tax_total": 3.40,
    "fee_total": 0.50,
    "discount_total": 0,
    "tip_total": 0,
    "deposit_total": 0,
    "rounding_adjustment": 0,
    "grand_total": 46.40,
    "payment_method": "credit",
    "payment_card_brand": "Visa",
    "payment_card_last4": "4242",
    "currency": "USD",
    "line_items": [
        {
            "description": "Organic Milk 1gal",
            "sku": "MILK-ORG-1G",
            "quantity": 1,
            "unit_price": 4.50,
            "line_total": 4.50,
            "line_discount": 0,
            "line_tax": 0.36,
            "taxable": True,
            "confidence": 0.95,
        },
        {
            "description": "Wheat Bread Loaf",
            "sku": "BRD-WHT-001",
            "quantity": 2,
            "unit_price": 3.50,
            "line_total": 7.00,
            "line_discount": 0,
            "line_tax": 0.56,
            "taxable": True,
            "confidence": 0.92,
        },
        {
            "description": "Bananas 1lb",
            "sku": "FRT-BAN-001",
            "quantity": 1,
            "unit_price": 1.50,
            "line_total": 1.50,
            "line_discount": 0,
            "line_tax": 0,
            "taxable": False,
            "confidence": 0.88,
        },
    ],
    "confidence_overall": 0.92,
    "low_confidence_fields": [],
}


EXTRACTION_PROMPT = """You are a receipt parsing AI. Extract structured data from this receipt OCR text.

Rules:
1. Return ONLY valid JSON. No other text, markdown, or explanation.
2. Use null for fields you cannot determine.
3. Improve product titles: clarify incomplete names.
4. Extract EVERY line item you can find — line items are the actual products/services purchased.
5. Use the EXACT field names shown in the schema below.

Expected JSON schema:
%s

Receipt OCR text:
%s

Return ONLY valid JSON matching the schema above, with no additional text."""


OLLAMA_FALLBACK_URL = "http://localhost:11434"


OPENAI_DEFAULT_MODEL = "gpt-4o-mini"


class AIExtractionProvider(BaseReceiptProvider):
    name = "ai_extraction"

    def process(self, file_path: str, **kwargs) -> ProviderResult:
        raw_ocr_text = kwargs.get("raw_ocr_text", "")
        if not raw_ocr_text:
            return ProviderResult(success=False, errors=["No OCR text provided for AI extraction."])

        mock_key = kwargs.get("mock_key", "")
        if mock_key and mock_key.lower().strip() == "test":
            return self._mock_response()

        provider = kwargs.get("provider", "openai")

        if provider == "mock":
            return self._mock_response()

        if provider == "openai":
            api_key = kwargs.get("openai_api_key", "")
            if not api_key:
                return ProviderResult(success=False, errors=["OpenAI API key is required."])
            model = kwargs.get("openai_model", OPENAI_DEFAULT_MODEL)
            return self._call_openai(raw_ocr_text, api_key, model)

        # Ollama fallback path
        primary_url = kwargs.get("ollama_base_url", "http://localhost:11434")
        fallback_url = kwargs.get("ollama_fallback_url", OLLAMA_FALLBACK_URL)
        model = kwargs.get("model", "deepseek-r1:8b")

        urls = [primary_url]
        if fallback_url != primary_url:
            urls.append(fallback_url)

        last_error = None
        for base_url in urls:
            result = self._call_ollama(raw_ocr_text, base_url, model)
            if result.success:
                return result
            last_error = result

        if last_error:
            return last_error

        return ProviderResult(success=False, errors=["All Ollama endpoints failed."])

    def _mock_response(self) -> ProviderResult:
        import json as json_module
        return ProviderResult(
            success=True,
            raw_text="MOCK TEXT ENFORCED",
            raw_json=json_module.dumps(MOCK_RESPONSE),
            data=MOCK_RESPONSE,
            confidence=0.92,
            diagnostics={"provider": "mock", "model": "test"},
        )

    def _call_openai(self, ocr_text: str, api_key: str, model: str = OPENAI_DEFAULT_MODEL) -> ProviderResult:
        try:
            from openai import OpenAI
            import json as json_module
        except ImportError:
            return ProviderResult(success=False, errors=["openai package is not installed."])

        prompts = [
            EXTRACTION_PROMPT % (json_module.dumps(AI_EXTRACTION_SCHEMA, indent=2), ocr_text),
            (
                "The previous response was not valid JSON. Return ONLY valid JSON matching this schema:\n"
                f"{json_module.dumps(AI_EXTRACTION_SCHEMA, indent=2)}\n\n"
                f"Receipt OCR text:\n{ocr_text}"
            ),
        ]

        last_error = None
        for i, prompt in enumerate(prompts):
            try:
                client = OpenAI(api_key=api_key)
                response = client.chat.completions.create(
                    model=model,
                    response_format={"type": "json_object"},
                    messages=[{"role": "user", "content": prompt}],
                    timeout=120,
                )
                content = response.choices[0].message.content
                if not content or not content.strip():
                    last_error = ProviderResult(success=False, errors=[f"Empty response (attempt {i+1})"])
                    continue
                parsed = json_module.loads(content)
                return ProviderResult(
                    success=True,
                    raw_text=content,
                    raw_json=json_module.dumps(parsed),
                    data=parsed,
                    confidence=parsed.get("confidence_overall", 0.8),
                    diagnostics={"provider": "openai", "model": model, "retry": i > 0},
                )
            except json_module.JSONDecodeError:
                last_error = ProviderResult(success=False, errors=[f"OpenAI returned invalid JSON (attempt {i+1})"])
            except Exception as e:
                last_error = ProviderResult(success=False, errors=[f"OpenAI error (attempt {i+1}): {e}"])

        return last_error or ProviderResult(success=False, errors=["All OpenAI attempts failed."])

    def _call_ollama(self, ocr_text: str, base_url: str, model: str) -> ProviderResult:
        import json as json_module
        prompts = [
            EXTRACTION_PROMPT % (json_module.dumps(AI_EXTRACTION_SCHEMA, indent=2), ocr_text),
            (
                "The previous response was not valid JSON. Return ONLY valid JSON for this receipt data. "
                "Use null for unknown fields.\n\n"
                f"Receipt OCR text:\n{ocr_text}"
            ),
        ]
        last_error = None
        for i, prompt in enumerate(prompts):
            try:
                response = requests.post(
                    f"{base_url}/api/generate",
                    json={
                        "model": model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                        "options": {"temperature": 0.1, "num_predict": 4096},
                    },
                    timeout=120,
                )
                response.raise_for_status()
                body = response.json()
                raw_text = body.get("response", "")
                if not raw_text.strip():
                    last_error = ProviderResult(success=False, errors=[f"Empty response (attempt {i+1})"])
                    continue
                parsed = json_module.loads(raw_text)
                return ProviderResult(
                    success=True,
                    raw_text=raw_text,
                    raw_json=json_module.dumps(parsed),
                    data=parsed,
                    confidence=parsed.get("confidence_overall", 0.0),
                    diagnostics={"provider": "ollama", "model": model, "retry": i > 0},
                )
            except json_module.JSONDecodeError:
                last_error = ProviderResult(success=False, errors=[f"Invalid JSON from model (attempt {i+1})"])
            except Exception as e:
                last_error = ProviderResult(success=False, errors=[f"Ollama error (attempt {i+1}): {e}"])
        return last_error or ProviderResult(success=False, errors=["All Ollama attempts failed."])
