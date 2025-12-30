"""LangGraph workflow for DocuFlow Headless extraction pipeline with smart routing."""

import asyncio
from typing import Dict, Any, List, Optional, TypedDict
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel, Field
import structlog

from engine.ingest import determine_input_type, is_garbage
from engine.crawler import crawl_url, crawl_with_retry
from engine.ocr import process_document, is_ocr_recommended
from engine.llm import extract_structured_data, ExtractionResult
from engine.validator import validate_extraction, ValidationResult

logger = structlog.get_logger(__name__)

class AgentState(TypedDict):
    """State for the extraction agent."""
    source_url: str
    target_schema: Dict[str, Any]
    use_gpu_ocr: bool
    proxy_configuration: Dict[str, Any]
    dev_mode: bool  # Development mode flag
    
    # Processing state
    input_type: Optional[str]
    markdown: Optional[str]
    extraction_result: Optional[ExtractionResult]
    validation_result: Optional[ValidationResult]
    
    # Error handling
    errors: List[str]
    warnings: List[str]
    retries: int
    max_retries: int
    
    # Smart routing
    confidence_threshold: float
    gpu_ocr_attempted: bool
    
    # Final output
    final_data: Optional[Dict[str, Any]]
    status: str  # "pending", "processing", "success", "failed"

class ExtractionWorkflow:
    """LangGraph workflow for document extraction with smart routing."""
    
    def __init__(self):
        self.graph = self._build_graph()
        
    def _build_graph(self) -> StateGraph:
        """Build the extraction workflow graph with smart routing."""
        
        # Define the workflow
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("ingest", self.ingest_node)
        workflow.add_node("extract_content", self.extract_content_node)
        workflow.add_node("extract_structure", self.extract_structure_node)
        workflow.add_node("validate", self.validate_node)
        workflow.add_node("retry_gpu_ocr", self.retry_gpu_ocr_node)
        workflow.add_node("finalize", self.finalize_node)
        workflow.add_node("error_handler", self.error_handler_node)
        
        # Add edges
        workflow.add_edge("ingest", "extract_content")
        workflow.add_edge("extract_content", "extract_structure")
        workflow.add_edge("extract_structure", "validate")
        workflow.add_edge("validate", "finalize")
        workflow.add_edge("error_handler", END)
        
        # Conditional edges for smart routing
        workflow.add_conditional_edges(
            "ingest",
            self.should_continue,
            {
                "continue": "extract_content",
                "error": "error_handler",
                "retry": "ingest"
            }
        )
        
        workflow.add_conditional_edges(
            "extract_structure",
            self.should_retry_gpu_ocr,
            {
                "retry_gpu": "retry_gpu_ocr",
                "continue": "validate"
            }
        )
        
        workflow.add_conditional_edges(
            "retry_gpu_ocr",
            self.gpu_ocr_result,
            {
                "success": "validate",
                "failed": "validate"  # Continue with validation even if GPU OCR failed
            }
        )
        
        workflow.add_conditional_edges(
            "finalize",
            self.is_complete,
            {
                "success": END,
                "retry": "ingest"
            }
        )
        
        # Set entry point
        workflow.set_entry_point("ingest")
        
        return workflow.compile()

    async def ingest_node(self, state: AgentState) -> Dict[str, Any]:
        """
        Robust ingestion node with comprehensive defense logic and smart routing.
        Implements the exact logic from the PRD specification.
        """
        logger.info("Starting ingestion node", url=state["source_url"])
        
        url = state["source_url"]
        
        try:
            # 1. Robust Type Detection
            logger.debug("Determining input type", url=url)
            itype = determine_input_type(url)
            
            if itype == "error":
                error_msg = "URL inaccessible or too large"
                logger.error(error_msg, url=url)
                return {
                    "errors": [error_msg],
                    "status": "failed",
                    "retries": 99  # Fatal error, no retry
                }
            
            # Update state with detected type
            state["input_type"] = itype
            logger.info("Input type detected", url=url, input_type=itype)
            
            # 2. Content Extraction based on type with smart routing
            logger.debug("Extracting content based on type", input_type=itype)
            
            if itype == "web":
                # Use crawler with document detection and proxy configuration
                use_proxy = state.get("proxy_configuration", {}).get("useApifyProxy", True)
                md = await crawl_with_retry(url, use_proxy=use_proxy, process_documents=True)
            else:
                # Process document (PDF/Image) with hybrid OCR
                use_gpu_ocr = state.get("use_gpu_ocr", False) or is_ocr_recommended(url, itype)
                ocr_result = await process_document(url, use_gpu_ocr=use_gpu_ocr)
                md = ocr_result.get("markdown", "")
                
                # Log OCR engine used
                logger.info("Document processed with OCR", 
                           url=url, 
                           engine=ocr_result.get("engine", "unknown"),
                           confidence=ocr_result.get("confidence", 0))
            
            # 3. Garbage Check (Critical defense against poor content)
            logger.debug("Performing garbage check", content_length=len(md) if md else 0)
            
            if is_garbage(md):
                error_msg = "Content appears to be a Login Wall or Empty"
                logger.error(error_msg, url=url, preview=md[:200] if md else "empty")
                return {
                    "errors": [error_msg],
                    "status": "failed",
                    "retries": 99  # Fatal error, no retry
                }
            
            logger.info("Ingestion completed successfully", 
                       url=url, 
                       input_type=itype,
                       content_length=len(md))
            
            return {
                "markdown": md,
                "input_type": itype,
                "errors": [],
                "retries": state.get("retries", 0)  # Preserve retry count
            }
            
        except Exception as e:
            error_msg = f"Ingest Failed: {str(e)}"
            logger.error(error_msg, url=url, error=str(e), error_type=type(e).__name__)
            
            return {
                "errors": [error_msg],
                "status": "failed",
                "retries": 99  # Fatal error, no retry
            }

    async def extract_content_node(self, state: AgentState) -> Dict[str, Any]:
        """Content extraction node (placeholder for additional processing)."""
        logger.debug("Content extraction node", 
                    url=state["source_url"],
                    content_length=len(state.get("markdown", "")))
        
        # Additional content processing can be added here
        # For now, just pass through the markdown
        
        return {}  # No state changes needed

    async def extract_structure_node(self, state: AgentState) -> Dict[str, Any]:
        """Structured data extraction using LLM with confidence assessment."""
        logger.info("Starting structured extraction",
                   url=state["source_url"],
                   schema_keys=list(state["target_schema"].keys()),
                   dev_mode=state.get("dev_mode", False))
        
        try:
            markdown = state.get("markdown", "")
            target_schema = state["target_schema"]
            
            if not markdown:
                raise ValueError("No markdown content available for extraction")
            
            if not target_schema:
                raise ValueError("No target schema provided")
            
            # Extract structured data using LLM with dev mode support
            extraction_result = await extract_structured_data(
                markdown,
                target_schema,
                dev_mode=state.get("dev_mode", False)
            )
            
            logger.info("Structured extraction completed",
                       success=extraction_result.success,
                       confidence=extraction_result.confidence,
                       needs_gpu_ocr=extraction_result.needs_gpu_ocr,
                       error_count=len(extraction_result.errors))
            
            return {
                "extraction_result": extraction_result
            }
            
        except Exception as e:
            logger.error("Structured extraction failed", 
                        error=str(e),
                        url=state["source_url"])
            
            return {
                "errors": [f"Extraction failed: {str(e)}"],
                "status": "failed",
                "retries": state.get("retries", 0) + 1
            }

    async def validate_node(self, state: AgentState) -> Dict[str, Any]:
        """Validation node with self-healing capabilities."""
        logger.info("Starting validation", url=state["source_url"])
        
        try:
            extraction_result = state.get("extraction_result")
            
            if not extraction_result or not extraction_result.success:
                # Skip validation if extraction failed
                return {
                    "validation_result": ValidationResult(
                        is_valid=False,
                        errors=["Extraction failed, skipping validation"],
                        warnings=[],
                        suggestions=[]
                    )
                }
            
            # Validate extracted data
            validation_result = validate_extraction(
                extraction_result.data,
                state["target_schema"]
            )
            
            logger.info("Validation completed",
                       is_valid=validation_result.is_valid,
                       error_count=len(validation_result.errors),
                       warning_count=len(validation_result.warnings))
            
            return {
                "validation_result": validation_result
            }
            
        except Exception as e:
            logger.error("Validation failed", error=str(e))
            
            return {
                "errors": [f"Validation failed: {str(e)}"],
                "status": "failed",
                "retries": state.get("retries", 0) + 1
            }

    async def retry_gpu_ocr_node(self, state: AgentState) -> Dict[str, Any]:
        """
        Retry with GPU OCR when confidence is low or extraction quality is poor.
        """
        logger.info("Retrying with GPU OCR", url=state["source_url"])
        
        try:
            # Check if we already tried GPU OCR
            if state.get("gpu_ocr_attempted", False):
                logger.info("GPU OCR already attempted, skipping retry")
                return {}  # No state changes needed
            
            # Get current extraction result
            current_result = state.get("extraction_result")
            
            if not current_result:
                logger.warning("No extraction result for GPU OCR retry")
                return {}  # No state changes needed
            
            # Check if retry is needed
            if (current_result.confidence < state.get("confidence_threshold", 0.7) or 
                current_result.needs_gpu_ocr):
                
                logger.info("Retrying extraction with GPU OCR",
                           current_confidence=current_result.confidence,
                           needs_gpu_ocr=current_result.needs_gpu_ocr)
                
                # Get the original content
                markdown = state.get("markdown", "")
                
                if not markdown:
                    logger.warning("No content available for GPU OCR retry")
                    return {"status": "processing"}
                
                # Check if this is a document that can benefit from GPU OCR
                input_type = state.get("input_type")
                if input_type in ["pdf", "image"]:
                    # Re-process with GPU OCR
                    ocr_result = await process_document(
                        state["source_url"], 
                        use_gpu_ocr=True,
                        confidence_threshold=0.0  # Force GPU OCR
                    )
                    
                    # Re-extract with new content
                    new_markdown = ocr_result.get("markdown", "")
                    
                    if new_markdown and new_markdown != markdown:
                        logger.info("GPU OCR produced different content, re-extracting")
                        
                        # Re-extract structured data with GPU OCR content
                        new_extraction_result = await extract_structured_data(
                            new_markdown,
                            state["target_schema"],
                            dev_mode=state.get("dev_mode", False)
                        )
                        
                        # Update state with new results
                        return {
                            "markdown": new_markdown,
                            "extraction_result": new_extraction_result,
                            "gpu_ocr_attempted": True
                        }
                    else:
                        logger.info("GPU OCR produced similar content, keeping original")
                
                else:
                    logger.info("Content type not suitable for GPU OCR retry", input_type=input_type)
            
            return {"gpu_ocr_attempted": True}
            
        except Exception as e:
            logger.error("GPU OCR retry failed", error=str(e))
            # Continue with original result even if GPU OCR failed
            return {"gpu_ocr_attempted": True}

    async def finalize_node(self, state: AgentState) -> Dict[str, Any]:
        """Finalization node that prepares the output."""
        logger.info("Finalizing extraction", url=state["source_url"])
        
        try:
            extraction_result = state.get("extraction_result")
            validation_result = state.get("validation_result")
            
            if not extraction_result:
                raise ValueError("No extraction result available")
            
            # Determine final data
            if validation_result and validation_result.corrected_data:
                final_data = validation_result.corrected_data
                logger.info("Using corrected data from validation")
            else:
                final_data = extraction_result.data
            
            # Build final result
            result = {
                "final_data": final_data,
                "extraction_confidence": extraction_result.confidence,
                "validation_passed": validation_result.is_valid if validation_result else False,
                "gpu_ocr_used": state.get("gpu_ocr_attempted", False),
                "errors": extraction_result.errors + (validation_result.errors if validation_result else []),
                "warnings": extraction_result.errors + (validation_result.warnings if validation_result else []),
                "suggestions": validation_result.suggestions if validation_result else [],
                "status": "success"
            }
            
            logger.info("Finalization completed successfully",
                       url=state["source_url"],
                       data_keys=list(final_data.keys()) if final_data else [],
                       confidence=extraction_result.confidence,
                       gpu_ocr_used=state.get("gpu_ocr_attempted", False))
            
            return result
            
        except Exception as e:
            logger.error("Finalization failed", error=str(e))
            
            return {
                "errors": [f"Finalization failed: {str(e)}"],
                "status": "failed",
                "retries": state.get("retries", 0) + 1
            }

    async def error_handler_node(self, state: AgentState) -> Dict[str, Any]:
        """Error handler node for failed extractions."""
        logger.error("Processing failed, entering error handler", 
                    url=state["source_url"],
                    errors=state.get("errors", []))
        
        # Log detailed error information
        for error in state.get("errors", []):
            logger.error("Processing error", url=state["source_url"], error=error)
        
        return {
            "final_data": None
        }

    def should_continue(self, state: AgentState) -> str:
        """Determine if processing should continue."""
        if state.get("status") == "failed":
            if state.get("retries", 0) >= state.get("max_retries", 3):
                return "error"
            else:
                return "retry"
        
        return "continue"

    def should_retry_gpu_ocr(self, state: AgentState) -> str:
        """Determine if GPU OCR retry is needed."""
        extraction_result = state.get("extraction_result")
        
        if not extraction_result:
            return "continue"
        
        # Don't retry if we already attempted GPU OCR
        if state.get("gpu_ocr_attempted", False):
            return "continue"
        
        # Check if retry is needed based on confidence or explicit request
        confidence_threshold = state.get("confidence_threshold", 0.7)
        
        if (extraction_result.confidence < confidence_threshold or 
            extraction_result.needs_gpu_ocr):
            return "retry_gpu"
        
        return "continue"

    def gpu_ocr_result(self, state: AgentState) -> str:
        """Determine the result of GPU OCR retry."""
        # Always continue to validation after GPU OCR attempt
        return "success"

    def is_complete(self, state: AgentState) -> str:
        """Determine if processing is complete."""
        if state.get("status") == "success":
            return "success"
        elif state.get("status") == "failed":
            if state.get("retries", 0) >= state.get("max_retries", 3):
                return "success"  # Return failed result
            else:
                return "retry"
        
        return "success"  # Default to success

    async def run(self, source_url: str, target_schema: Dict[str, Any],
                  use_gpu_ocr: bool = False,
                  proxy_configuration: Optional[Dict[str, Any]] = None,
                  confidence_threshold: float = 0.7,
                  dev_mode: bool = False) -> Dict[str, Any]:
        """
        Run the extraction workflow with smart routing.
        
        Args:
            source_url: URL to extract from
            target_schema: Schema defining what to extract
            use_gpu_ocr: Whether to force GPU OCR
            proxy_configuration: Proxy configuration for crawling
            confidence_threshold: Minimum confidence before trying GPU OCR
            
        Returns:
            Extraction result with data or errors
        """
        logger.info("Starting extraction workflow with smart routing", 
                   url=source_url,
                   schema_keys=list(target_schema.keys()),
                   confidence_threshold=confidence_threshold)
        
        # Initialize state
        initial_state = {
            "source_url": source_url,
            "target_schema": target_schema,
            "use_gpu_ocr": use_gpu_ocr,
            "proxy_configuration": proxy_configuration or {"useApifyProxy": True},
            "confidence_threshold": confidence_threshold,
            "dev_mode": dev_mode,
            "gpu_ocr_attempted": False,
            "errors": [],
            "warnings": [],
            "retries": 0,
            "max_retries": 3,
            "status": "pending"
        }
        
        # Run the workflow
        try:
            result = await self.graph.ainvoke(initial_state)
            
            logger.info("Workflow completed", 
                       url=source_url,
                       status=result.get("status"),
                       has_data=bool(result.get("final_data")),
                       gpu_ocr_used=result.get("gpu_ocr_used", False))
            
            return result
            
        except Exception as e:
            logger.error("Workflow failed with exception", 
                        url=source_url,
                        error=str(e))
            
            return {
                "status": "failed",
                "errors": [f"Workflow failed: {str(e)}"],
                "final_data": None
            }

# Global workflow instance
_workflow = None

async def run_extraction(source_url: str, target_schema: Dict[str, Any],
                        use_gpu_ocr: bool = False,
                        proxy_configuration: Optional[Dict[str, Any]] = None,
                        confidence_threshold: float = 0.7,
                        dev_mode: bool = False) -> Dict[str, Any]:
    """
    Run the extraction workflow (convenience function).
    
    Args:
        source_url: URL to extract from
        target_schema: Schema defining what to extract
        use_gpu_ocr: Whether to force GPU OCR
        proxy_configuration: Proxy configuration for crawling
        confidence_threshold: Minimum confidence before trying GPU OCR
        
    Returns:
        Extraction result with data or errors
    """
    global _workflow
    
    if _workflow is None:
        _workflow = ExtractionWorkflow()
    
    return await _workflow.run(
        source_url=source_url,
        target_schema=target_schema,
        use_gpu_ocr=use_gpu_ocr,
        proxy_configuration=proxy_configuration,
        confidence_threshold=confidence_threshold,
        dev_mode=dev_mode
    )