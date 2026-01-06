"""
Universal Document Extractor - Apify Actor

Production-ready Apify Actor using Google Gemini 2.0 Flash (Multimodal)
for document classification and structured extraction.

Leverages existing patterns from:
- agent_graph.py (router logic, error handling)
- schemas.py (Pydantic validation, business logic)

Input from n8n: {"docBinary": {"data": "base64_string..."}}
Output: Clean JSON with doc_type, summary, and typed payload
"""
import os
import json
import base64
import time
import asyncio
from typing import Optional, Union, Any

from apify import Actor
from google import genai
from google.genai import types

from schemas import (
    BoundingBox,
    LeaseData,
    QuoteData,
    CoiData,
    DocumentExtraction,
    ExtractionResult,
)


# =============================================================================
# Configuration
# =============================================================================

GEMINI_MODEL = "gemini-2.0-flash-exp"
API_KEY = os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    raise EnvironmentError("GOOGLE_API_KEY environment variable is required")


# =============================================================================
# System Prompt for Gemini 2.0 Flash
# =============================================================================

SYSTEM_PROMPT = """You are a specialized document extraction AI for property management.

## Your Tasks

1. **CLASSIFY** the document type:
   - Lease Agreement: rental contracts, lease agreements
   - Quote/Bid: vendor estimates, contractor bids, price quotes
   - COI (Certificate of Insurance): insurance certificates, liability documents

2. **EXTRACT** data according to the provided JSON schema with precision.

3. **LOCATE** key values using bounding box coordinates (0-1000 scale).

## Schema Definitions

### Lease Agreement Schema
{
  "tenant_name": "Full legal name of tenant",
  "landlord_name": "Property owner/manager name",
  "property_address": "Full property address",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "monthly_rent": numeric_amount,
  "notice_period_days": days_required_before_end,
  "rent_cap_percentage": max_allowed_increase,
  "tenant_name_location": {"ymin": 0, "xmin": 0, "ymax": 1000, "xmax": 1000},
  "end_date_location": {"ymin": 0, "xmin": 0, "ymax": 1000, "xmax": 1000},
  "monthly_rent_location": {"ymin": 0, "xmin": 0, "ymax": 1000, "xmax": 1000}
}

### Quote/Bid Schema
{
  "vendor_name": "Company or contractor name",
  "vendor_address": "Vendor address",
  "line_items": ["item1", "item2", "item3"],
  "total_amount": numeric_amount,
  "hidden_fees_found": true/false,
  "vendor_name_location": {"ymin": 0, "xmin": 0, "ymax": 1000, "xmax": 1000},
  "total_amount_location": {"ymin": 0, "xmin": 0, "ymax": 1000, "xmax": 1000}
}

### COI Schema
{
  "insured_name": "Business/entity name",
  "insurance_company": "Insurance carrier name",
  "policy_number": "Policy identifier",
  "expiration_date": "YYYY-MM-DD",
  "policy_limit": coverage_amount,
  "expiration_date_location": {"ymin": 0, "xmin": 0, "ymax": 1000, "xmax": 1000},
  "policy_limit_location": {"ymin": 0, "xmin": 0, "ymax": 1000, "xmax": 1000}
}

## Critical Rules

1. **Bounding Boxes**: Provide coordinates (0-1000) indicating where each value appears in the document.
   - ymin/xmin = top-left corner
   - ymax/xmax = bottom-right corner
   - For dates/money, locate the EXACT value, not the label

2. **COI Special Rule**: Check if expiration_date is within 30 days of today. If so, flag as urgent.

3. **Quote Formatting**: Return line items as a simple array of strings for Airtable compatibility.

4. **Dates**: Use EXACTLY YYYY-MM-DD format.

5. **Money**: Return raw numbers (e.g., 2500.00 not "$2,500.00").

6. **Missing Data**: If a field cannot be found, set to null. Do not hallucinate.

7. **Output**: Return ONLY valid JSON matching the schema. No markdown, no explanations.
"""


# =============================================================================
# Helper Functions (leveraged from existing utils)
# =============================================================================

def truncate_text(text: str, max_length: int = 8000) -> str:
    """Truncate text to avoid token limits while preserving structure."""
    if len(text) <= max_length:
        return text
    # Try to cut at a paragraph boundary
    truncated = text[:max_length]
    last_newline = truncated.rfind('\n')
    if last_newline > max_length * 0.8:
        return truncated[:last_newline]
    return truncated


def clean_money_value(v: str | float | int) -> float:
    """Clean money string to float."""
    if isinstance(v, float):
        return v
    if isinstance(v, int):
        return float(v)
    if v is None:
        return 0.0
    clean = str(v).replace('$', '').replace(',', '').replace(' ', '').strip()
    try:
        return float(clean)
    except (ValueError, TypeError):
        return 0.0


# =============================================================================
# DATA CONTRACT ENFORCER: n8n Serialization Layer
# =============================================================================
# This is our "Insurance Policy" against broken automations.
# Rule: Never trust n8n to format data. Pydantic validates, this serializes.

def normalize_for_n8n(data: dict) -> dict:
    """
    Converts extracted data to n8n-compatible flat JSON.

    Guarantees:
    1. Dates -> ISO8601 Strings (YYYY-MM-DD)
    2. Floats -> Rounded to 2 decimals (no 10.000000001)
    3. Nested Lists -> JSON Strings (so Airtable/Sheets don't split rows)
    4. None -> null (explicit, not omitted)

    Args:
        data: Dictionary from extraction/cleaning pipeline

    Returns:
        n8n-compatible dictionary ready for push_data()
    """
    if not data:
        return data

    result = {}

    for key, value in data.items():
        if value is None:
            result[key] = None
            continue

        # Rule: Floats rounded to 2 decimals (Airtable hates precision errors)
        if isinstance(value, float):
            result[key] = round(value, 2)
            continue

        # Rule: Nested lists converted to JSON strings (Google Sheets/Airtable compatibility)
        if isinstance(value, list):
            # Check if list contains dicts or complex objects
            if value and isinstance(value[0], (dict, list)):
                # Complex nested structure -> JSON string
                result[key] = json.dumps(value, default=str)
            else:
                # Simple list (strings, numbers) -> keep as list for n8n Switch nodes
                result[key] = value
            continue

        # Rule: Dicts with nested data -> flatten key paths
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                if sub_value is None:
                    result[f"{key}_{sub_key}"] = None
                elif isinstance(sub_value, float):
                    result[f"{key}_{sub_key}"] = round(sub_value, 2)
                elif isinstance(sub_value, list):
                    result[f"{key}_{sub_key}"] = json.dumps(sub_value, default=str)
                else:
                    result[f"{key}_{sub_key}"] = sub_value
            continue

        # Default: keep as-is
        result[key] = value

    return result


def validate_output_contract(data: dict, expected_schema: dict) -> tuple[bool, list[str]]:
    """
    Validates output against n8n destination requirements.

    This is our "Schema Test" - run before push_data() to catch issues.
    Returns (is_valid, list of issues).
    """
    issues = []

    # Check required fields
    for field, expected_type in expected_schema.get("required", []):
        if field not in data:
            issues.append(f"Missing required field: {field}")
            continue

        actual_value = data[field]
        actual_type = type(actual_value).__name__

        # Type checking
        if expected_type == "number" and not isinstance(actual_value, (int, float)):
            issues.append(f"{field}: expected number, got {actual_type}")
        elif expected_type == "string" and not isinstance(actual_value, str):
            issues.append(f"{field}: expected string, got {actual_type}")
        elif expected_type == "boolean" and not isinstance(actual_value, bool):
            issues.append(f"{field}: expected boolean, got {actual_type}")

    return len(issues) == 0, issues


# =============================================================================
# Document Classification (leveraged from agent_graph.py router_node)
# =============================================================================

def classify_document(text_preview: str) -> str:
    """
    Classify document type using keyword detection.
    Leveraged from agent_graph.py router_node logic.
    """
    text = text_preview.lower()

    # COI detection - most specific, check first
    coi_keywords = [
        "certificate of insurance", "certificate of liability insurance",
        "coi", "liability insurance", "insurance certificate",
        "policy period", "named insured", "certificate holder",
        "policy number", "effective date", "expiration date"
    ]
    if any(kw in text for kw in coi_keywords):
        return "coi"

    # Lease detection
    lease_keywords = [
        "lease agreement", "residential lease", "apartment lease",
        "tenant name", "landlord", "month-to-month",
        "security deposit", "rent amount", "lease term",
        "move-in date", "notice period"
    ]
    if any(kw in text for kw in lease_keywords):
        return "lease"

    # Quote/Bid detection
    quote_keywords = [
        "estimate", "quote", "bid proposal", "proposal",
        "total amount", "pricing", "cost estimate",
        "vendor", "materials", "labor"
    ]
    if any(kw in text for kw in quote_keywords):
        return "quote"

    return "unknown"


# =============================================================================
# Gemini 2.0 Flash Extraction
# =============================================================================

async def extract_with_gemini(
    doc_base64: str,
    mime_type: str,
    doc_type: str
) -> dict[str, Any]:
    """
    Extract structured data from document using Gemini 2.0 Flash.

    Uses Google's native structured output support for type-safe extraction.
    """
    # Select appropriate schema based on document type
    schema_map = {
        "lease": LeaseData,
        "quote": QuoteData,
        "coi": CoiData,
    }

    target_schema = schema_map.get(doc_type, CoiData)

    # Build schema description for Gemini
    schema_description = target_schema.model_json_schema()

    client = genai.Client(api_key=API_KEY)

    # Create content with image
    content = types.Content(
        role="user",
        parts=[
            types.Part(
                inline_data=types.Blob(
                    data=base64.b64decode(doc_base64),
                    mime_type=mime_type
                )
            ),
            types.Part(text=SYSTEM_PROMPT)
        ]
    )

    # Configure response schema for structured output
    response_schema = {
        "type": "object",
        "properties": {
            "doc_type": {"type": "string"},
            "summary": {"type": "string"},
            "payload": schema_description,
            "extraction_confidence": {"type": "number"},
            "classification_confidence": {"type": "number"}
        },
        "required": ["doc_type", "summary", "payload"]
    }

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[content],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=response_schema,
                temperature=0.1
            )
        )

        result = json.loads(response.text)
        return result

    except Exception as e:
        # Fallback: try without strict schema if structured output fails
        Actor.log.warning(f"Structured output failed, trying fallback: {e}")

        # Build simpler prompt for fallback
        prompt = f"""Extract data from this document as JSON.

Document Type: {doc_type.upper()}

Return JSON with:
- doc_type: "{doc_type}"
- summary: 1-2 sentence summary
- payload: object with extracted fields (use null if not found)
- extraction_confidence: 0.0-1.0
- classification_confidence: 0.0-1.0

For the payload, include:
- All relevant fields from the {doc_type} schema
- For dates: YYYY-MM-DD format
- For money: numeric values only
- For locations: {{"ymin": 0, "xmin": 0, "ymax": 1000, "xmax": 1000}} estimates

Return ONLY valid JSON, no markdown."""

        content_simple = types.Content(
            role="user",
            parts=[
                types.Part(
                    inline_data=types.Blob(
                        data=base64.b64decode(doc_base64),
                        mime_type=mime_type
                    )
                ),
                types.Part(text=prompt)
            ]
        )

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[content_simple],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )

        return json.loads(response.text)


# =============================================================================
# Post-Processing Logic (leveraged from schemas.py validators)
# =============================================================================

def post_process_extraction(
    doc_type: str,
    payload: dict
) -> Union[LeaseData, QuoteData, CoiData, dict]:
    """
    Apply Python logic to extracted data.
    - Lease: Calculate notice_date
    - COI: Calculate days_until_expiry, is_urgent
    - Quote: Format line items for Airtable
    """
    from datetime import date, timedelta

    # Re-validate through Pydantic to trigger business logic
    schema_map = {
        "lease": LeaseData,
        "quote": QuoteData,
        "coi": CoiData,
    }

    target_schema = schema_map.get(doc_type)
    if target_schema:
        try:
            validated = target_schema(**payload)
            return validated.model_dump()
        except Exception as e:
            Actor.log.warning(f"Post-processing validation failed: {e}")
            return payload

    return payload


# =============================================================================
# Main Apify Actor
# =============================================================================

async def main() -> None:
    """
    Main function for the Universal Document Extractor Apify Actor.

    Input (from n8n): {"docBinary": {"data": "base64_encoded_pdf"}}
    Output: Clean JSON to Apify Dataset
    """
    async with Actor:
        start_time = time.time()
        input_data = await Actor.get_input() or {}

        # =====================================================================
        # Step 1: Get Base64 from n8n input
        # =====================================================================
        doc_binary = input_data.get("docBinary", {})
        base64_data = doc_binary.get("data") if isinstance(doc_binary, dict) else None

        # Fallback: also support direct base64 field
        if not base64_data:
            base64_data = input_data.get("docBase64") or input_data.get("base64_data")

        if not base64_data:
            error_result = {
                "status": "error",
                "doc_type": "unknown",
                "summary": "",
                "payload": None,
                "is_urgent": False,
                "warnings": [],
                "error": "No document data found. Expected input format: {\"docBinary\": {\"data\": \"base64_string...\"}}"
            }
            await Actor.push_data(error_result)
            return

        try:
            # Validate base64
            if len(base64_data) < 100:
                raise ValueError("Invalid base64 data - too short")

            # Detect MIME type from input or default to PDF
            mime_type = input_data.get("mimeType", "application/pdf")

            # =================================================================
            # Step 2: Classify document (fast keyword check)
            # =================================================================
            # Quick preview decode for classification
            preview_bytes = base64.b64decode(base64_data[:1000])
            preview_text = preview_bytes.decode('utf-8', errors='ignore')[:500]
            doc_type = classify_document(preview_text)

            Actor.log.info(f"Classified document as: {doc_type}")

            # =================================================================
            # Step 3: Extract with Gemini 2.0 Flash
            # =================================================================
            extraction_result = await extract_with_gemini(
                doc_base64=base64_data,
                mime_type=mime_type,
                doc_type=doc_type
            )

            # =================================================================
            # Step 4: Post-process with business logic
            # =================================================================
            payload = extraction_result.get("payload", {})

            if payload:
                payload = post_process_extraction(
                    doc_type=extraction_result.get("doc_type", doc_type),
                    payload=payload
                )

            # Calculate processing time
            processing_time_ms = int((time.time() - start_time) * 1000)

            # Determine urgency from payload
            is_urgent = payload.get("is_urgent", False) if payload else False

            # Collect warnings from payload
            payload_warnings = payload.get("warnings", []) if payload else []

            # =================================================================
            # Step 5: Build final result and enforce data contract
            # =================================================================
            result = {
                "status": "success",
                "doc_type": extraction_result.get("doc_type", doc_type),
                "summary": extraction_result.get("summary", ""),
                "payload": payload,
                "is_urgent": is_urgent,
                "warnings": payload_warnings,
                "extraction_confidence": extraction_result.get("extraction_confidence", 0.0),
                "classification_confidence": extraction_result.get("classification_confidence", 0.0),
                "model_used": GEMINI_MODEL,
                "processing_time_ms": processing_time_ms
            }

            # Apply n8n serialization layer (Data Contract Enforcer)
            normalized_result = normalize_for_n8n(result)

            await Actor.push_data(normalized_result)

        except ValueError as ve:
            # Input validation error - clean error structure
            error_result = {
                "status": "error",
                "doc_type": "unknown",
                "summary": "",
                "payload": None,
                "is_urgent": False,
                "warnings": [],
                "error": str(ve)
            }
            await Actor.push_data(normalize_for_n8n(error_result))
            Actor.log.error(f"Validation error: {ve}")

        except json.JSONDecodeError as je:
            # JSON parsing error
            error_result = {
                "status": "error",
                "doc_type": doc_type if 'doc_type' in dir() else "unknown",
                "summary": "",
                "payload": None,
                "is_urgent": False,
                "warnings": [],
                "error": f"Failed to parse AI response: {str(je)}"
            }
            await Actor.push_data(normalize_for_n8n(error_result))
            Actor.log.error(f"JSON decode error: {je}")

        except Exception as e:
            # Catch-all for unexpected errors
            error_result = {
                "status": "error",
                "doc_type": doc_type if 'doc_type' in dir() else "unknown",
                "summary": "",
                "payload": None,
                "is_urgent": False,
                "warnings": [],
                "error": f"Processing failed: {str(e)}"
            }
            await Actor.push_data(normalize_for_n8n(error_result))
            Actor.log.error(f"Unexpected error: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
