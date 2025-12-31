"""Secure orchestrator for managing CPU/GPU engines with intelligent routing and comprehensive monitoring."""

import asyncio
import time
import os
from typing import Dict, Any, Optional, List
from datetime import datetime
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from .secure_engine_cpu import SecureCPUEngine, get_cpu_engine
from .secure_engine_gpu import SecureGPUEngine, get_gpu_engine
from .security_monitoring import get_monitoring_manager, SecurityError

# Configure logging
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

class RoutingDecision(BaseModel):
    """Routing decision with reasoning."""
    engine: str = Field(..., description="Selected engine: cpu or gpu")
    confidence: float = Field(..., description="Confidence in routing decision")
    reasoning: str = Field(..., description="Reasoning for engine selection")
    text_density: float = Field(..., description="Calculated text density")
    has_text_layer: bool = Field(..., description="Whether document has text layer")
    fallback_available: bool = Field(..., description="Whether fallback engine is available")

class ProcessingResult(BaseModel):
    """Result of document processing."""
    success: bool
    text: str
    confidence: float
    processing_time: float
    request_id: str
    engine: str
    metadata: Dict[str, Any]
    routing_decision: Optional[RoutingDecision] = None
    fallback_used: bool = False
    error_message: Optional[str] = None

class SecureOrchestrator:
    """Secure orchestrator for managing CPU/GPU engines with intelligent routing."""
    
    def __init__(self):
        self.cpu_engine: Optional[SecureCPUEngine] = None
        self.gpu_engine: Optional[SecureGPUEngine] = None
        self.monitoring_manager = get_monitoring_manager()
        self._initialized = False
        self._fallback_enabled = True
        
    async def initialize(self) -> None:
        """Initialize both engines."""
        if self._initialized:
            return
            
        try:
            # Initialize CPU engine
            self.cpu_engine = await get_cpu_engine()
            
            # Initialize GPU engine
            self.gpu_engine = await get_gpu_engine()
            
            self._initialized = True
            logger.info("Secure orchestrator initialized successfully")
            
        except Exception as e:
            logger.error("Failed to initialize secure orchestrator", error=str(e))
            raise RuntimeError(f"Orchestrator initialization failed: {str(e)}")
            
    async def cleanup(self) -> None:
        """Clean up all engines."""
        if self.cpu_engine:
            await self.cpu_engine.cleanup()
        if self.gpu_engine:
            await self.gpu_engine.cleanup()
        self._initialized = False
        logger.info("Secure orchestrator cleaned up")
        
    def calculate_text_density(self, file_path: str, sample_pages: int = 2) -> Dict[str, Any]:
        """Calculate text density and determine if document has text layer."""
        try:
            import fitz  # PyMuPDF
            
            doc = fitz.open(file_path)
            total_chars = 0
            total_pages = min(sample_pages, doc.page_count)
            has_text_layer = False
            
            for page_num in range(total_pages):
                page = doc.load_page(page_num)
                
                # Check for text layer
                text = page.get_text()
                if text and len(text.strip()) > 10:
                    has_text_layer = True
                    total_chars += len(text.strip())
                    
            doc.close()
            
            text_density = total_chars / total_pages if total_pages > 0 else 0
            
            return {
                "text_density": text_density,
                "has_text_layer": has_text_layer,
                "sampled_pages": total_pages,
                "total_chars": total_chars
            }
            
        except Exception as e:
            logger.error("Failed to calculate text density", file_path=file_path, error=str(e))
            return {
                "text_density": 0,
                "has_text_layer": False,
                "sampled_pages": 0,
                "total_chars": 0,
                "error": str(e)
            }
            
    def make_routing_decision(self, text_density_info: Dict[str, Any]) -> RoutingDecision:
        """Make intelligent routing decision based on document characteristics."""
        text_density = text_density_info.get("text_density", 0)
        has_text_layer = text_density_info.get("has_text_layer", False)
        
        # Routing logic based on master checklist
        if has_text_layer and text_density > 50:
            # Document has good text layer and sufficient content - use CPU
            return RoutingDecision(
                engine="cpu",
                confidence=0.9,
                reasoning=f"Document has text layer with {text_density:.1f} chars/page density",
                text_density=text_density,
                has_text_layer=has_text_layer,
                fallback_available=self._fallback_enabled and self.gpu_engine is not None
            )
        else:
            # Document needs OCR or has low text density - use GPU
            return RoutingDecision(
                engine="gpu",
                confidence=0.8,
                reasoning=f"Document requires OCR (no text layer, density: {text_density:.1f})",
                text_density=text_density,
                has_text_layer=has_text_layer,
                fallback_available=self._fallback_enabled and self.cpu_engine is not None
            )
            
    async def process_document(self, file_path: str, file_url: str, **kwargs) -> ProcessingResult:
        """Process document with intelligent routing and comprehensive error handling."""
        if not self._initialized:
            await self.initialize()
            
        start_time = time.time()
        request_id = f"orch_{int(start_time)}_{hash(file_url) % 10000}"
        
        logger.info("Starting secure document processing",
                   request_id=request_id,
                   file_path=file_path,
                   file_url=file_url)
        
        try:
            # Calculate text density for routing decision
            text_density_info = self.calculate_text_density(file_path)
            routing_decision = self.make_routing_decision(text_density_info)
            
            logger.info("Routing decision made",
                       request_id=request_id,
                       engine=routing_decision.engine,
                       confidence=routing_decision.confidence,
                       reasoning=routing_decision.reasoning)
            
            # Process with selected engine
            primary_result = None
            fallback_used = False
            
            try:
                if routing_decision.engine == "cpu":
                    primary_result = await self.cpu_engine.process_document(file_url)
                else:
                    primary_result = await self.gpu_engine.process_document(file_url)
                    
            except Exception as primary_error:
                logger.error(f"Primary {routing_decision.engine} engine failed",
                           request_id=request_id,
                           error=str(primary_error))
                
                # Try fallback if available
                if routing_decision.fallback_available and self._fallback_enabled:
                    fallback_engine = "gpu" if routing_decision.engine == "cpu" else "cpu"
                    logger.warning(f"Attempting fallback to {fallback_engine} engine",
                                 request_id=request_id)
                    
                    try:
                        if fallback_engine == "cpu":
                            primary_result = await self.cpu_engine.process_document(file_url)
                        else:
                            primary_result = await self.gpu_engine.process_document(file_url)
                            
                        fallback_used = True
                        logger.info(f"Fallback to {fallback_engine} engine successful",
                                  request_id=request_id)
                        
                    except Exception as fallback_error:
                        logger.error(f"Fallback {fallback_engine} engine also failed",
                                   request_id=request_id,
                                   error=str(fallback_error))
                        raise RuntimeError(f"Both primary and fallback engines failed: {str(primary_error)}")
                else:
                    raise primary_error
                    
            # Create final result
            processing_time = time.time() - start_time
            
            final_result = ProcessingResult(
                success=primary_result.get("success", False),
                text=primary_result.get("text", ""),
                confidence=primary_result.get("confidence", 0.0),
                processing_time=processing_time,
                request_id=request_id,
                engine=primary_result.get("engine", routing_decision.engine),
                metadata={
                    **primary_result.get("metadata", {}),
                    "routing_decision": routing_decision.dict(),
                    "fallback_used": fallback_used,
                    "text_density_info": text_density_info
                },
                routing_decision=routing_decision,
                fallback_used=fallback_used
            )
            
            logger.info("Secure orchestration completed successfully",
                       request_id=request_id,
                       engine=final_result.engine,
                       processing_time=processing_time,
                       fallback_used=fallback_used,
                       text_length=len(final_result.text))
            
            return final_result
            
        except Exception as e:
            logger.error("Secure orchestration failed",
                        request_id=request_id,
                        error=str(e),
                        file_path=file_path)
            
            processing_time = time.time() - start_time
            
            return ProcessingResult(
                success=False,
                text="",
                confidence=0.0,
                processing_time=processing_time,
                request_id=request_id,
                engine="unknown",
                metadata={
                    "error_time": datetime.utcnow().isoformat(),
                    "file_path": file_path,
                    "file_url": file_url
                },
                error_message=str(e)
            )
            
    async def process_batch(self, files: List[Dict[str, str]], **kwargs) -> List[ProcessingResult]:
        """Process multiple documents with intelligent batching."""
        if not self._initialized:
            await self.initialize()
            
        logger.info("Starting batch processing", file_count=len(files))
        
        # Process files concurrently with controlled parallelism
        semaphore = asyncio.Semaphore(3)  # Max 3 concurrent processing
        
        async def process_single(file_info: Dict[str, str]) -> ProcessingResult:
            async with semaphore:
                return await self.process_document(
                    file_path=file_info["file_path"],
                    file_url=file_info["file_url"],
                    **kwargs
                )
                
        # Process all files
        results = await asyncio.gather(
            *[process_single(file_info) for file_info in files],
            return_exceptions=True
        )
        
        # Handle any exceptions
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Batch processing failed for file {i}", error=str(result))
                final_results.append(ProcessingResult(
                    success=False,
                    text="",
                    confidence=0.0,
                    processing_time=0,
                    request_id=f"batch_error_{i}",
                    engine="unknown",
                    error_message=str(result)
                ))
            else:
                final_results.append(result)
                
        logger.info("Batch processing completed", 
                   total_files=len(files),
                   successful=sum(1 for r in final_results if r.success),
                   failed=sum(1 for r in final_results if not r.success))
        
        return final_results
        
    async def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check on all engines."""
        if not self._initialized:
            await self.initialize()
            
        try:
            # Check CPU engine health
            cpu_health = await self.cpu_engine.health_check() if self.cpu_engine else {"status": "unavailable"}
            
            # Check GPU engine health
            gpu_health = await self.gpu_engine.health_check() if self.gpu_engine else {"status": "unavailable"}
            
            # Overall health status
            overall_status = "healthy"
            if cpu_health.get("status") != "healthy" and gpu_health.get("status") != "healthy":
                overall_status = "unhealthy"
            elif cpu_health.get("status") != "healthy" or gpu_health.get("status") != "healthy":
                overall_status = "degraded"
                
            return {
                "status": overall_status,
                "orchestrator": {
                    "initialized": self._initialized,
                    "fallback_enabled": self._fallback_enabled
                },
                "cpu_engine": cpu_health,
                "gpu_engine": gpu_health,
                "monitoring": self.monitoring_manager.get_health_status(),
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error("Orchestrator health check failed", error=str(e))
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
            
    def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive metrics for orchestrator."""
        return {
            "orchestrator": {
                "initialized": self._initialized,
                "fallback_enabled": self._fallback_enabled
            },
            "cpu_engine": self.cpu_engine.get_metrics() if self.cpu_engine else {},
            "gpu_engine": self.gpu_engine.get_metrics() if self.gpu_engine else {},
            "monitoring": self.monitoring_manager.get_metrics()
        }
        
    def enable_fallback(self, enabled: bool = True):
        """Enable or disable fallback mechanism."""
        self._fallback_enabled = enabled
        logger.info(f"Fallback mechanism {'enabled' if enabled else 'disabled'}")

# Global orchestrator instance
_orchestrator: Optional[SecureOrchestrator] = None

async def get_orchestrator() -> SecureOrchestrator:
    """Get global orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = SecureOrchestrator()
        await _orchestrator.initialize()
    return _orchestrator

async def cleanup_orchestrator():
    """Clean up global orchestrator instance."""
    global _orchestrator
    if _orchestrator:
        await _orchestrator.cleanup()
        _orchestrator = None