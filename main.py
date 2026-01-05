"""
PropFlow Agent - AI Clerk for Property Managers

This Apify Actor processes property documents (leases, quotes, COIs) using:
- Docling for OCR and document conversion
- LangGraph for routing and state management
- Pydantic schemas with business logic validation
- Ollama/DeepSeek for structured extraction
- Outputs actionable data for n8n automation
"""
import os
import json
import asyncio
from typing import Dict, Any
from apify import Actor
from agent_graph import app


# Configuration - using Ollama for local development
# In production, this would be configured for DeepInfra
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434").rstrip("/")


async def main() -> None:
    """Main function for the PropFlow Agent Apify Actor."""
    async with Actor:
        # Get input from Apify platform
        input_data = await Actor.get_input() or {}

        # Support both PRD format (docUrl) and backward compatibility (docUrls)
        doc_url = input_data.get("docUrl")
        doc_urls = input_data.get("docUrls", [])
        
        # Normalize to list format
        if doc_url:
            doc_urls = [doc_url] if not doc_urls else doc_urls
        elif not doc_urls:
            raise ValueError("Input must include either 'docUrl' (single) or 'docUrls' (array) parameter with document URL(s)")

        # Process each document using LangGraph
        for doc_url in doc_urls:
            try:
                # Run the LangGraph workflow
                initial_state = {
                    "doc_url": doc_url,
                    "text_md": "",
                    "doc_type": "",
                    "final_data": {}
                }
                result = await app.ainvoke(initial_state)
                
                # Check if result has validation errors (partial success)
                final_data = result.get("final_data", {})
                if final_data.get("status") == "validation_error":
                    # Partial success - return with warnings
                    result["status"] = "partial_success"
                    result["warnings"] = final_data.get("errors", [])
                    await Actor.push_data(result)
                elif "error" in final_data:
                    # Full error
                    error_result = {
                        "doc_url": doc_url,
                        "status": "error",
                        "error": final_data.get("error"),
                        "error_type": final_data.get("error_type", "unknown"),
                        "final_data": final_data
                    }
                    await Actor.push_data(error_result)
                else:
                    # Success
                    result["status"] = "success"
                    await Actor.push_data(result)
                    
            except Exception as e:
                # Catch-all for unexpected errors
                error_result = {
                    "doc_url": doc_url,
                    "status": "error",
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "final_data": {"error": str(e), "error_type": type(e).__name__}
                }
                await Actor.push_data(error_result)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())