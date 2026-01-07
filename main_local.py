#!/usr/bin/env python3
"""
Local Development Server for EntryAI Platform

This module provides a FastAPI server that wraps the extraction logic
for local development and testing with n8n.

Usage:
    python main_local.py

The server will start on http://localhost:8000

n8n Configuration for local testing:
    - URL: http://localhost:8000/run-sync
    - Method: POST
    - Content-Type: application/json

Example n8n JSON input:
    {
        "data": "base64_encoded_pdf_content",
        "task_type": "extract_invoice"
    }
"""
from __future__ import annotations

import base64
import json
import sys
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
import uvicorn

# =============================================================================
# Minimal Schema Imports (No Apify SDK to avoid Pydantic conflicts)
# =============================================================================

from typing import Literal, List, Dict, Any
from datetime import date


class DocumentBinaryInput(BaseModel):
    """Input format from n8n - base64 encoded document."""
    data: str = Field(..., description="Base64 encoded document (PDF/Image)")

    @field_validator("data")
    @classmethod
    def validate_base64(cls, v: str) -> str:
        if len(v) < 10:
            raise ValueError("base64 data too short")
        return v


class ActorInput(BaseModel):
    """Router input schema for EntryAI platform tasks."""
    task_type: Literal[
        "extract_invoice", "extract_lease", "extract_quote",
        "extract_coi", "verify_data", "clean_crm"
    ] = Field(..., description="Type of task to execute")

    doc_binary: Optional[DocumentBinaryInput] = Field(
        None, description="Base64 encoded document for extraction tasks"
    )
    data_file_base64: Optional[str] = Field(None, description="Base64 encoded data file")
    options: Optional[Dict[str, Any]] = Field(None, description="Task-specific options")

    @field_validator("task_type")
    @classmethod
    def validate_task_type(cls, v: str) -> str:
        extraction_tasks = {"extract_invoice", "extract_lease", "extract_quote", "extract_coi"}
        if v in extraction_tasks and not cls.__dict__.get("_doc_binary"):
            pass  # Simplified validation for local dev
        return v


class ExtractionResult(BaseModel):
    """Final output format for n8n consumption."""
    status: Literal["success", "error"] = "success"
    doc_type: str = "unknown"
    summary: str = ""
    payload: Optional[Dict[str, Any]] = None
    is_urgent: bool = False
    warnings: List[str] = Field(default_factory=list)
    error: Optional[str] = None


# =============================================================================
# Classification Logic (Simplified for Local Dev)
# =============================================================================

def classify_document(text_preview: str) -> str:
    """
    Classify document type based on text content.

    Precedence: COI > Invoice > Lease > Quote > Unknown
    """
    text_lower = text_preview.lower()

    # COI keywords (highest priority - insurance is time-sensitive)
    coi_keywords = ["certificate of insurance", "policy number", "insured",
                    "expiration date", "liability", "coverage", "insured name"]
    coi_matches = sum(1 for kw in coi_keywords if kw in text_lower)

    # Invoice keywords
    invoice_keywords = ["invoice", "invoice number", "total amount", "due date",
                        "vendor", "bill to", "subtotal", "tax"]
    invoice_matches = sum(1 for kw in invoice_keywords if kw in text_lower)

    # Lease keywords
    lease_keywords = ["lease", "tenant", "landlord", "monthly rent", "security deposit",
                      "term", "expiration", "rent"]
    lease_matches = sum(1 for kw in lease_keywords if kw in text_lower)

    # Quote keywords (after lease to avoid overlap)
    quote_keywords = ["quote", "bid", "estimate", "pricing", "proposal", "valid until"]
    quote_matches = sum(1 for kw in quote_keywords if kw in text_lower)

    # Classification decision
    if coi_matches >= 2:
        return "coi"
    elif invoice_matches >= 2:
        return "invoice"
    elif lease_matches >= 2:
        return "lease"
    elif quote_matches >= 2:
        return "quote"
    elif "invoice" in text_lower and "quote" not in text_lower:
        return "invoice"
    else:
        return "unknown"


# =============================================================================
# Stub Extraction Functions (For Local Dev Testing)
# =============================================================================

async def extract_invoice_stub(file_bytes: bytes, doc_type: str) -> ExtractionResult:
    """Stub invoice extraction for local testing."""
    return ExtractionResult(
        status="success",
        doc_type="invoice",
        summary="Invoice extracted (stub mode - requires Gemini API for production)",
        payload={
            "invoice_number": "INV-STUB-001",
            "vendor_name": "Acme Corp (Stub)",
            "invoice_date": "2024-01-15",
            "due_date": "2024-02-15",
            "total_amount": 1500.00,
            "tax_amount": 150.00,
            "subtotal": 1350.00,
            "currency": "USD",
            "line_items": [
                {"description": "Consulting Services", "quantity": 10, "unit_price": 100.00, "total": 1000.00},
                {"description": "Software License", "quantity": 1, "unit_price": 350.00, "total": 350.00},
            ],
        },
        is_urgent=False,
        warnings=["This is a stub response - configure Gemini API for real extraction"],
    )


async def extract_lease_stub(file_bytes: bytes, doc_type: str) -> ExtractionResult:
    """Stub lease extraction for local testing."""
    return ExtractionResult(
        status="success",
        doc_type="lease",
        summary="Lease agreement extracted (stub mode)",
        payload={
            "tenant_name": "John Doe (Stub)",
            "landlord_name": "Property Management Inc",
            "property_address": "456 Oak Ave, Los Angeles, CA 90001",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "monthly_rent": 2500.00,
            "security_deposit": 5000.00,
            "notice_period_days": 60,
            "rent_cap_percentage": 5.0,
        },
        is_urgent=False,
        warnings=["This is a stub response - configure Gemini API for production"],
    )


async def extract_coi_stub(file_bytes: bytes, doc_type: str) -> ExtractionResult:
    """Stub COI extraction for local testing."""
    return ExtractionResult(
        status="success",
        doc_type="coi",
        summary="Certificate of Insurance extracted (stub mode)",
        payload={
            "insured_name": "ABC Corporation (Stub)",
            "insurance_company": "XYZ Insurance Co",
            "policy_number": "GL-2024-1234",
            "expiration_date": "2025-12-31",
            "policy_limit": 2000000.00,
            "days_until_expiry": 358,
            "policy_limit_flagged": False,
            "is_urgent": False,
        },
        is_urgent=False,
        warnings=["This is a stub response - configure Gemini API for production"],
    )


async def extract_quote_stub(file_bytes: bytes, doc_type: str) -> ExtractionResult:
    """Stub quote extraction for local testing."""
    return ExtractionResult(
        status="success",
        doc_type="quote",
        summary="Vendor quote extracted (stub mode)",
        payload={
            "vendor_name": "Tech Solutions LLC (Stub)",
            "quote_number": "Q-2024-001",
            "quote_date": "2024-01-10",
            "valid_until": "2024-02-10",
            "subtotal": 5000.00,
            "tax_amount": 500.00,
            "total_amount": 5500.00,
            "currency": "USD",
            "line_items": [
                {"item": "Web Development", "quantity": 40, "unit_price": 100.00, "total": 4000.00},
                {"item": "Hosting (Annual)", "quantity": 1, "unit_price": 1000.00, "total": 1000.00},
            ],
            "true_cost": 5500.00,
        },
        is_urgent=False,
        warnings=["This is a stub response - configure Gemini API for production"],
    )


async def process_extraction_task(actor_input: ActorInput) -> ExtractionResult:
    """
    Process extraction task - main entry point for local dev.

    In production, this would call Google Gemini 2.0 Flash.
    In local dev, returns stub data for testing n8n workflows.
    """
    if not actor_input.doc_binary:
        return ExtractionResult(
            status="error",
            doc_type="unknown",
            summary="No document provided",
            error="doc_binary is required for extraction tasks",
        )

    # Decode document
    try:
        file_bytes = base64.b64decode(actor_input.doc_binary.data)
    except Exception as e:
        return ExtractionResult(
            status="error",
            doc_type="unknown",
            summary="Failed to decode document",
            error=str(e),
        )

    # Get text preview for classification
    text_preview = file_bytes[:2048].decode("utf-8", errors="ignore")

    # Classify document
    doc_type = classify_document(text_preview)

    # Route to appropriate extraction
    if doc_type == "coi" or actor_input.task_type == "extract_coi":
        return await extract_coi_stub(file_bytes, doc_type)
    elif doc_type == "invoice" or actor_input.task_type == "extract_invoice":
        return await extract_invoice_stub(file_bytes, doc_type)
    elif doc_type == "lease" or actor_input.task_type == "extract_lease":
        return await extract_lease_stub(file_bytes, doc_type)
    elif doc_type == "quote" or actor_input.task_type == "extract_quote":
        return await extract_quote_stub(file_bytes, doc_type)
    else:
        return ExtractionResult(
            status="error",
            doc_type="unknown",
            summary="Could not classify document",
            error="Document type not recognized",
        )


def normalize_for_n8n(result: ExtractionResult) -> Dict[str, Any]:
    """Normalize extraction result for n8n consumption."""
    return {
        "status": result.status,
        "doc_type": result.doc_type,
        "summary": result.summary,
        "payload": result.payload,
        "is_urgent": result.is_urgent,
        "warnings": result.warnings,
        "error": result.error,
    }


# =============================================================================
# FastAPI App
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application lifespan events."""
    print("🚀 EntryAI Local Server starting...")
    print("   Server: http://localhost:8000")
    print("   Endpoint: POST /run-sync")
    print("   Health: GET /health")
    print()
    print("📡 Waiting for n8n requests...")
    yield
    print("🛑 EntryAI Local Server shutting down...")


app = FastAPI(
    title="EntryAI Local Server",
    description="Local development server for EntryAI Platform extraction logic",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Health Check
# =============================================================================

@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint for n8n."""
    return {"status": "healthy", "service": "entryai-local"}


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint with usage info."""
    return {
        "service": "EntryAI Local Server",
        "version": "1.0.0",
        "mode": "stub",  # Indicates this returns stub data
        "endpoints": {
            "health": "GET /health",
            "extract": "POST /run-sync",
        },
        "n8n_usage": {
            "url": "http://localhost:8000/run-sync",
            "method": "POST",
            "body": {
                "data": "base64_encoded_pdf",
                "task_type": "extract_invoice",
            },
        },
    }


# =============================================================================
# Main Extraction Endpoint
# =============================================================================

@app.post("/run-sync")
async def local_extraction_endpoint(request: Request) -> dict[str, Any]:
    """
    Main extraction endpoint for n8n integration.

    Expected Input:
    {
        "data": "base64_encoded_document_content",
        "task_type": "extract_invoice|extract_lease|extract_quote|extract_coi"
    }

    Returns:
    {
        "status": "success|error",
        "doc_type": "invoice|lease|quote|coi|unknown",
        "summary": "...",
        "payload": {...}
    }
    """
    try:
        body = await request.json()
        print(f"📥 Received request from n8n")

        # Extract base64 data
        file_b64 = body.get("data")
        if not file_b64:
            raise HTTPException(status_code=400, detail="Missing 'data' field")

        # Validate base64
        try:
            file_bytes = base64.b64decode(file_b64)
            print(f"   Decoded {len(file_bytes)} bytes")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid base64: {e}")

        # Build ActorInput
        task_type = body.get("task_type", "extract_invoice")
        actor_input = ActorInput(
            task_type=task_type,
            doc_binary=DocumentBinaryInput(data=file_b64),
        )

        # Run extraction
        print(f"   Processing {task_type}...")
        result = await process_extraction_task(actor_input)

        # Return n8n-compatible output
        output = normalize_for_n8n(result)
        print(f"   ✅ {result.doc_type}: {result.summary[:50]}...")

        return output

    except HTTPException:
        raise
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "doc_type": "unknown",
                "summary": str(e),
                "payload": None,
                "error": str(e),
            },
        )


# =============================================================================
# Simplified Endpoints
# =============================================================================

@app.post("/extract/invoice")
async def extract_invoice(request: Request) -> dict[str, Any]:
    """Simplified invoice extraction."""
    body = await request.json()
    file_b64 = body.get("data")
    if not file_b64:
        raise HTTPException(status_code=400, detail="Missing 'data'")

    actor_input = ActorInput(
        task_type="extract_invoice",
        doc_binary=DocumentBinaryInput(data=file_b64),
    )
    result = await process_extraction_task(actor_input)
    return normalize_for_n8n(result)


@app.post("/extract/lease")
async def extract_lease(request: Request) -> dict[str, Any]:
    """Simplified lease extraction."""
    body = await request.json()
    file_b64 = body.get("data")
    if not file_b64:
        raise HTTPException(status_code=400, detail="Missing 'data'")

    actor_input = ActorInput(
        task_type="extract_lease",
        doc_binary=DocumentBinaryInput(data=file_b64),
    )
    result = await process_extraction_task(actor_input)
    return normalize_for_n8n(result)


@app.post("/extract/coi")
async def extract_coi(request: Request) -> dict[str, Any]:
    """Simplified COI extraction."""
    body = await request.json()
    file_b64 = body.get("data")
    if not file_b64:
        raise HTTPException(status_code=400, detail="Missing 'data'")

    actor_input = ActorInput(
        task_type="extract_coi",
        doc_binary=DocumentBinaryInput(data=file_b64),
    )
    result = await process_extraction_task(actor_input)
    return normalize_for_n8n(result)


@app.post("/extract/quote")
async def extract_quote(request: Request) -> dict[str, Any]:
    """Simplified quote extraction."""
    body = await request.json()
    file_b64 = body.get("data")
    if not file_b64:
        raise HTTPException(status_code=400, detail="Missing 'data'")

    actor_input = ActorInput(
        task_type="extract_quote",
        doc_binary=DocumentBinaryInput(data=file_b64),
    )
    result = await process_extraction_task(actor_input)
    return normalize_for_n8n(result)


@app.post("/classify")
async def classify_document_endpoint(request: Request) -> dict[str, Any]:
    """Classify document type."""
    body = await request.json()
    file_b64 = body.get("data")

    if not file_b64:
        raise HTTPException(status_code=400, detail="Missing 'data'")

    try:
        file_bytes = base64.b64decode(file_b64)
        text_preview = file_bytes[:1024].decode("utf-8", errors="ignore")
    except Exception:
        text_preview = ""

    doc_type = classify_document(text_preview)

    return {
        "doc_type": doc_type,
        "confidence": 0.9,
        "note": "Stub classification - configure Gemini for production",
    }


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Run the local development server."""
    print("=" * 60)
    print("EntryAI Local Development Server")
    print("=" * 60)
    print()
    print("This server provides stub extraction for n8n workflow testing.")
    print("Configure Gemini API in main.py for production extraction.")
    print()
    print("Endpoints:")
    print("  POST /run-sync          - Full extraction (task_type in body)")
    print("  POST /extract/invoice   - Invoice extraction only")
    print("  POST /extract/lease     - Lease extraction only")
    print("  POST /extract/coi       - COI extraction only")
    print("  POST /extract/quote     - Quote extraction only")
    print("  POST /classify          - Document classification only")
    print()
    print("n8n HTTP Request Configuration:")
    print("  URL:    http://localhost:8000/run-sync")
    print("  Method: POST")
    print("  Body:   JSON with 'data' (base64) and 'task_type'")
    print()
    print("-" * 60)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )


if __name__ == "__main__":
    main()
