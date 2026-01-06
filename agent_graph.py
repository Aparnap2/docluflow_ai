"""
PropFlow Agent - LangGraph Workflow for Document Extraction
Uses Docling or DeepSeek OCR, then LFM2 for JSON extraction.
"""
from langgraph.graph import StateGraph, END
from typing import TypedDict, Any, Optional
from schemas import LeaseSchema, QuoteSchema, CoiSchema
from utils_ocr import run_docling, run_deepseek_ocr, run_ocr
from pydantic import ValidationError
import json
import re

class AgentState(TypedDict):
    doc_url: Optional[str]
    doc_bytes: Optional[bytes]
    text_md: str
    doc_type: str
    final_data: dict

async def ocr_node(state):
    """
    OCR node using DeepSeek OCR (default) with Docling fallback.
    DeepSeek OCR handles scanned PDFs better.
    """
    use_deepseek = True  # Default to DeepSeek OCR
    if state.get("doc_bytes"):
        text_md = await run_ocr(None, doc_bytes=state["doc_bytes"], use_deepseek=use_deepseek)
    else:
        text_md = await run_ocr(state['doc_url'], use_deepseek=use_deepseek)
    return {"text_md": text_md}

def router_node(state):
    """
    Router node using keyword detection (Fast).
    Uses multiple keywords for reliable document classification.
    """
    from utils_security import truncate_text

    text = truncate_text(state['text_md'], max_length=2000).lower()

    # COI detection - check first (most specific)
    coi_keywords = [
        "certificate of insurance", "certificate of liability insurance",
        "coi", "liability insurance", "insurance certificate",
        "policy period", "named insured", "certificate holder"
    ]
    if any(kw in text for kw in coi_keywords):
        return {"doc_type": "coi"}

    # Lease detection
    lease_keywords = [
        "lease agreement", "residential lease", "apartment lease",
        "tenant name", "landlord", "month-to-month",
        "security deposit", "rent amount", "lease term"
    ]
    if any(kw in text for kw in lease_keywords):
        return {"doc_type": "lease"}

    # Quote/Bid detection
    quote_keywords = [
        "estimate", "quote", "bid proposal", "proposal",
        "total amount", "pricing", "cost estimate",
        "pacifc flooring", "vendor"
    ]
    if any(kw in text for kw in quote_keywords):
        return {"doc_type": "quote"}

    return {"doc_type": "unknown"}

def extraction_node(state):
    """
    Extraction node using Ministral-3B for structured JSON output.
    LFM2 has issues - using Ministral as reliable fallback.
    """
    # Use ministral-3:3b (proven working)
    model_name = "ministral-3:3b"

    schema_map = {"lease": LeaseSchema, "quote": QuoteSchema, "coi": CoiSchema}
    target_schema = schema_map.get(state['doc_type'])

    if not target_schema:
        return {"final_data": {"error": f"Unknown document type: {state['doc_type']}"}}

    from langchain_ollama import OllamaLLM
    from utils_security import truncate_text

    llm = OllamaLLM(model=model_name, temperature=0)
    truncated_text = truncate_text(state['text_md'], max_length=40000)

    schema_json = json.dumps(target_schema.model_json_schema(), indent=2)

    prompt = f"""Extract JSON data from this document.

SCHEMA:
{schema_json}

INSTRUCTIONS:
1. Extract ALL fields in the schema
2. For dates, use YYYY-MM-DD format
3. For money values, use numbers
4. If a field is not found, return null
5. Output ONLY valid JSON, no markdown

DOCUMENT:
{truncated_text}

JSON:"""

    try:
        response = llm.invoke(prompt)

        # Clean response
        cleaned = response.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()
        elif "{" in cleaned:
            cleaned = cleaned[cleaned.find("{"):cleaned.rfind("}")+1]

        if not cleaned or cleaned == "null":
            raise ValueError("Empty response from LLM")

        data = json.loads(cleaned)

        try:
            validated = target_schema(**data)
            result = {**validated.model_dump(mode='json'), "status": "success"}
            return {"final_data": result}
        except ValidationError as e:
            return {
                "final_data": {
                    "status": "validation_error",
                    "doc_type": state['doc_type'],
                    "errors": e.errors(),
                    "partial_data": data
                }
            }

    except Exception as e:
        return {"final_data": {"error": f"Extraction failed: {str(e)}"}}

# Build Graph
workflow = StateGraph(AgentState)
workflow.add_node("ocr", ocr_node)
workflow.add_node("router", router_node)
workflow.add_node("extract", extraction_node)
workflow.set_entry_point("ocr")
workflow.add_edge("ocr", "router")
workflow.add_edge("router", "extract")
workflow.add_edge("extract", END)
app = workflow.compile()