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
        Process v2 input with multiple files and intelligent routing.
        
        Args:
            input_data: Input data containing files, schema, filter_keywords, etc.
            
        Returns:
            Processing result
        """
        try:
            # Validate v2 input
            if not input_data.get("files"):
                raise ValueError("files array is required")
            
            if not input_data.get("schema"):
                raise ValueError("schema is required")
            
            files = input_data["files"]
            target_schema = input_data["schema"]
            filter_keywords = input_data.get("filter_keywords", [])
            use_gpu_ocr = input_data.get("use_gpu_ocr", False)
            confidence_threshold = input_data.get("confidence_threshold", 0.7)
            proxy_configuration = input_data.get("proxy_configuration", {"useApifyProxy": True})
            
            logger.info("Starting v2 extraction",
                       file_count=len(files),
                       schema_keys=list(target_schema.keys()) if isinstance(target_schema, dict) else [],
                       filter_keywords=filter_keywords,
                       use_gpu_ocr=use_gpu_ocr)
            
            # Import intelligent processing
            from .engine.ingest import process_file_intelligently
            
            # Process each file intelligently
            results = []
            for i, file_info in enumerate(files):
                try:
                    logger.info("Processing file", file_index=i, filename=file_info.get("filename", "unknown"))
                    
                    # Intelligent ingestion with AGB filtering and routing
                    ingestion_result = await process_file_intelligently(file_info, filter_keywords)
                    
                    if ingestion_result.get("skipped"):
                        logger.info("File skipped",
                                   filename=file_info.get("filename"),
                                   reason=ingestion_result.get("reason", "Unknown"))
                        results.append({
                            "file_index": i,
                            "filename": file_info.get("filename"),
                            "status": "skipped",
                            "skip_reason": ingestion_result.get("reason", "Filtered out"),
                            "extracted_data": None
                        })
                        continue
                    
                    if ingestion_result.get("error"):
                        logger.error("File processing failed",
                                   filename=file_info.get("filename"),
                                   error=ingestion_result.get("error"))
                        results.append({
                            "file_index": i,
                            "filename": file_info.get("filename"),
                            "status": "failed",
                            "error": ingestion_result.get("error"),
                            "extracted_data": None
                        })
                        continue
                    
                    # Extract with intelligent routing
                    route = ingestion_result.get("route", "CPU_FAST")
                    url = ingestion_result.get("url")
                    
                    if not url:
                        raise ValueError("No URL available for extraction")
                    
                    # Run the extraction workflow with routing
                    result = await run_extraction(
                        source_url=url,
                        target_schema=target_schema,
                        use_gpu_ocr=use_gpu_ocr or route == "GPU_VISION",
                        proxy_configuration=proxy_configuration,
                        route=route,
                        confidence_threshold=confidence_threshold
                    )
                    
                    # Add routing metadata to result
                    result["route"] = route
                    result["file_index"] = i
                    result["filename"] = file_info.get("filename")
                    
                    results.append(result)
                    
                except Exception as e:
                    logger.error("File processing failed",
                               file_index=i,
                               filename=file_info.get("filename"),
                               error=str(e))
                    results.append({
                        "file_index": i,
                        "filename": file_info.get("filename"),
                        "status": "failed",
                        "error": str(e),
                        "extracted_data": None
                    })
            
            # Format the combined result for Apify
            apify_result = self._format_apify_v2_result(results, input_data)
            
            logger.info("V2 extraction completed",
                       total_files=len(files),
                       successful_files=sum(1 for r in results if r.get("status") == "success"),
                       skipped_files=sum(1 for r in results if r.get("status") == "skipped"))
            
            return apify_result
            
        except Exception as e:
            logger.error("V2 processing failed", error=str(e), input=input_data)
            
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

    def _format_apify_v2_result(self, results: list, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format v2 extraction results for Apify output."""
        successful_results = [r for r in results if r.get("status") == "success"]
        failed_results = [r for r in results if r.get("status") == "failed"]
        skipped_results = [r for r in results if r.get("status") == "skipped"]
        
        if successful_results:
            # Format n8n-compatible output if requested
            output_format = input_data.get("output_format", "n8n_compatible")
            if output_format == "n8n_compatible":
                from .models import format_n8n_output
                
                # Format each successful result for n8n
                formatted_results = []
                for result in successful_results:
                    n8n_data = format_n8n_output(
                        result.get("final_data", {}),
                        result.get("filename", "unknown"),
                        result.get("route", "CPU_FAST")
                    )
                    formatted_results.append(n8n_data)
                
                return {
                    "status": "success",
                    "data": formatted_results,
                    "metadata": {
                        "total_files": len(results),
                        "successful": len(successful_results),
                        "failed": len(failed_results),
                        "skipped": len(skipped_results),
                        "output_format": "n8n_compatible"
                    },
                    "input": {
                        "files": input_data.get("files", []),
                        "schema": input_data.get("schema", {}),
                        "filter_keywords": input_data.get("filter_keywords", [])
                    }
                }
            else:
                # Standard JSON output
                return {
                    "status": "success",
                    "data": [r.get("final_data", {}) for r in successful_results],
                    "metadata": {
                        "total_files": len(results),
                        "successful": len(successful_results),
                        "failed": len(failed_results),
                        "skipped": len(skipped_results)
                    },
                    "input": {
                        "files": input_data.get("files", []),
                        "schema": input_data.get("schema", {}),
                        "filter_keywords": input_data.get("filter_keywords", [])
                    }
                }
        else:
            # All files failed or were skipped
            return {
                "status": "failed" if failed_results else "skipped",
                "error": "All files failed processing" if failed_results else "All files were filtered out",
                "data": None,
                "metadata": {
                    "total_files": len(results),
                    "successful": 0,
                    "failed": len(failed_results),
                    "skipped": len(skipped_results)
                },
                "input": {
                    "files": input_data.get("files", []),
                    "schema": input_data.get("schema", {}),
                    "filter_keywords": input_data.get("filter_keywords", [])
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