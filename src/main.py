"""Main Apify entrypoint for DocuFlow Headless."""

import asyncio
import os
import json
import sys
from typing import Dict, Any
from dotenv import load_dotenv
import structlog

# Load environment variables
load_dotenv()

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

# Import our modules
from .graph import run_extraction

class DocuFlowActor:
    """Apify Actor for DocuFlow Headless extraction."""
    
    def __init__(self):
        self.validate_environment()
        
    def validate_environment(self):
        """Validate required environment variables."""
        required_vars = ["GROQ_API_KEY"]
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {missing_vars}")
        
        logger.info("Environment validation passed")

    async def process_input(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a single input item.
        
        Args:
            input_data: Input data containing source_url, target_schema, etc.
            
        Returns:
            Processing result
        """
        try:
            # Validate input
            if not input_data.get("source_url"):
                raise ValueError("source_url is required")
            
            if not input_data.get("target_schema"):
                raise ValueError("target_schema is required")
            
            source_url = input_data["source_url"]
            target_schema = input_data["target_schema"]
            use_gpu_ocr = input_data.get("use_gpu_ocr", False)
            proxy_configuration = input_data.get("proxy_configuration", {"useApifyProxy": True})
            
            logger.info("Starting extraction", 
                       url=source_url,
                       schema_keys=list(target_schema.keys()),
                       use_gpu_ocr=use_gpu_ocr)
            
            # Run the extraction workflow
            result = await run_extraction(
                source_url=source_url,
                target_schema=target_schema,
                use_gpu_ocr=use_gpu_ocr,
                proxy_configuration=proxy_configuration
            )
            
            # Format the result for Apify
            apify_result = self._format_apify_result(result, input_data)
            
            logger.info("Extraction completed", 
                       url=source_url,
                       status=apify_result["status"],
                       has_data=bool(apify_result.get("data")))
            
            return apify_result
            
        except Exception as e:
            logger.error("Processing failed", error=str(e), input=input_data)
            
            return {
                "status": "failed",
                "error": str(e),
                "data": None,
                "input": input_data
            }

    def _format_apify_result(self, result: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format the extraction result for Apify output."""
        status = result.get("status", "unknown")
        
        if status == "success":
            final_data = result.get("final_data", {})
            validation_result = result.get("validation_result", {})
            
            return {
                "status": "success",
                "data": final_data,
                "confidence": result.get("extraction_confidence", 0.0),
                "validation_passed": validation_result.get("is_valid", False),
                "errors": result.get("errors", []),
                "warnings": result.get("warnings", []),
                "suggestions": result.get("suggestions", []),
                "input": {
                    "source_url": input_data["source_url"],
                    "target_schema": input_data["target_schema"],
                    "use_gpu_ocr": input_data.get("use_gpu_ocr", False)
                }
            }
        else:
            return {
                "status": "failed",
                "error": "; ".join(result.get("errors", ["Unknown error"])),
                "data": None,
                "input": {
                    "source_url": input_data["source_url"],
                    "target_schema": input_data["target_schema"]
                }
            }

async def main():
    """Main entrypoint for the Apify Actor."""
    try:
        logger.info("Starting DocuFlow Headless Actor")
        
        # Initialize actor
        actor = DocuFlowActor()
        
        # For Apify, input comes from the Actor context
        # In development/testing, you can provide input directly
        
        # Example input for testing (can be overridden by Apify input)
        test_input = {
            "source_url": "https://example.com/document.pdf",
            "target_schema": {
                "title": "string",
                "author": "string",
                "date": "string",
                "summary": "string"
            },
            "use_gpu_ocr": False,
            "proxy_configuration": {"useApifyProxy": True}
        }
        
        # Check if we're running in Apify environment
        if os.getenv("APIFY_ACTOR_RUN_ID"):
            # In Apify environment, input will be provided by the platform
            # For now, we'll use the test input
            input_data = test_input
            logger.info("Running in Apify environment")
        else:
            # Local development/testing
            input_data = test_input
            logger.info("Running in development mode")
        
        # Process the input
        result = await actor.process_input(input_data)
        
        # Output result (Apify will handle this)
        print(json.dumps(result, indent=2, default=str))
        
        # Return result for Apify
        return result
        
    except Exception as e:
        logger.error("Actor failed", error=str(e))
        
        error_result = {
            "status": "failed",
            "error": str(e),
            "data": None
        }
        
        print(json.dumps(error_result, indent=2))
        return error_result

if __name__ == "__main__":
    # Run the actor
    result = asyncio.run(main())
    
    # Exit with appropriate code
    if result.get("status") == "success":
        sys.exit(0)
    else:
        sys.exit(1)