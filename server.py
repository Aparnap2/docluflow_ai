"""
Local API Server for PropFlow Agent.
Exposes the LangGraph workflow as a REST API for n8n integration.

Output format for n8n:
{
  "status": "success" | "error",
  "doc_type": "lease" | "quote" | "coi" | "unknown",
  "data": { extracted fields... },
  "is_critical": true/false,  // For COI Slack routing
  "error": "error message"    // Only on error
}
"""
import os
import uvicorn
from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from agent_graph import app
import logging
import base64

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("propflow-server")

app_api = FastAPI(title="PropFlow Local API")

# Simple API Key for local security
API_KEY = os.getenv("DOCUFLOW_API_KEY", "dev-key-123")


class ExtractionRequest(BaseModel):
    """Request format matching n8n binary data input."""
    doc_base64: Optional[str] = None  # Base64 encoded PDF
    source_url: Optional[str] = None
    filename: Optional[str] = None


@app_api.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "online", "service": "PropFlow Agent", "version": "1.0.0"}


@app_api.get("/health")
async def health():
    """Detailed health check for n8n monitoring."""
    return {
        "status": "healthy",
        "service": "PropFlow Agent",
        "ocr_engine": "deepseek-ocr",
        "extraction_engine": "lfm2"
    }


@app_api.post("/extract")
async def extract_document(
    request: ExtractionRequest,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    """
    Main extraction endpoint for n8n.

    Expected input from n8n:
    {
      "doc_base64": "{{ $binary.data }}",
      "filename": "{{ $binary.filename }}"
    }

    Output for n8n (compatible with Switch nodes):
    {
      "status": "success",
      "doc_type": "lease",
      "data": { extracted fields... },
      "is_critical": false
    }
    """
    # Basic API Key check
    if x_api_key and x_api_key != API_KEY:
        logger.warning(f"Unauthorized access attempt with key: {x_api_key}")
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Handle Base64 PDF from n8n
    doc_bytes = None
    if request.doc_base64:
        try:
            # Handle both raw base64 and data URI format
            if "," in request.doc_base64:
                request.doc_base64 = request.doc_base64.split(",")[1]
            doc_bytes = base64.b64decode(request.doc_base64)
            logger.info(f"Decoded PDF: {len(doc_bytes)} bytes")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid base64: {str(e)}")

    if not request.source_url and not doc_bytes:
        raise HTTPException(status_code=400, detail="Missing source_url or doc_base64")

    # Prepare initial state for LangGraph
    initial_state = {
        "doc_url": request.source_url,
        "doc_bytes": doc_bytes,
        "text_md": "",
        "doc_type": "",
        "final_data": {}
    }

    try:
        # Run the LangGraph workflow
        logger.info("Starting LangGraph workflow...")
        result = await app.ainvoke(initial_state)

        doc_type = result.get("doc_type", "unknown")
        final_data = result.get("final_data", {})

        # Determine status
        status = "success"
        if final_data.get("status") == "validation_error":
            status = "validation_error"
        elif "error" in final_data:
            status = "error"

        # Build n8n-compatible response
        response = {
            "status": status,
            "doc_type": doc_type,
            "filename": request.filename
        }

        # Add data for n8n actions (Calendar, Airtable, Slack)
        if "data" in final_data:
            response["data"] = final_data["data"]
        else:
            # Flatten final_data for n8n (excluding status)
            response["data"] = {k: v for k, v in final_data.items() if k != "status"}

        # Add is_critical for COI Slack routing
        if doc_type == "coi":
            response["is_critical"] = final_data.get("is_critical", False)
        elif doc_type == "lease":
            # Add calculated_notice_date for Calendar
            response["is_critical"] = False
            if final_data.get("calculated_notice_date"):
                response["notice_date"] = final_data["calculated_notice_date"]

        # Add warnings for manual review
        if final_data.get("warnings"):
            response["warnings"] = final_data["warnings"]

        # Error response
        if status == "error":
            response["error"] = final_data.get("error", "Unknown error")

        logger.info(f"Extraction complete: doc_type={doc_type}, status={status}")
        return response

    except Exception as e:
        logger.error(f"Error processing document: {str(e)}")
        return {
            "status": "error",
            "doc_type": "unknown",
            "error": str(e),
            "filename": request.filename
        }


@app_api.post("/extract/batch")
async def extract_batch(
    request: ExtractionRequest,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    """
    Batch extraction endpoint for multiple documents.
    Processes one document at a time (n8n can loop this).
    """
    return await extract_document(request, x_api_key)


if __name__ == "__main__":
    # Run on all interfaces for Docker/n8n access
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app_api, host="0.0.0.0", port=port, log_level="info")
