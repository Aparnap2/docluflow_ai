"""Secure GPU engine with Modal API integration and comprehensive error handling."""

import asyncio
import time
import os
from typing import Dict, Any, Optional, List
from datetime import datetime
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from .secure_modal_client import SecureModalClient, create_secure_modal_client, ModalAPIError
from .security_monitoring import get_monitoring_manager

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

class SecureGPUEngine:
    """Secure GPU engine with Modal API integration and comprehensive monitoring."""
    
    def __init__(self):
        self.client: Optional[SecureModalClient] = None
        self.monitoring_manager = get_monitoring_manager()
        self._initialized = False
        
    async def initialize(self) -> None:
        """Initialize the secure Modal client."""
        if self._initialized:
            return
            
        try:
            self.client = await create_secure_modal_client(
                api_key=os.getenv("MODAL_API_KEY"),
                enable_caching=True,
                enable_monitoring=True,
                enable_rate_limiting=True,
                max_retries=5,  # More retries for GPU due to higher cost
                timeout=60  # Longer timeout for GPU processing
            )
            self._initialized = True
            logger.info("Secure GPU engine initialized successfully")
            
        except Exception as e:
            logger.error("Failed to initialize secure GPU engine", error=str(e))
            raise RuntimeError(f"GPU engine initialization failed: {str(e)}")
            
    async def cleanup(self) -> None:
        """Clean up resources."""
        if self.client:
            await self.client.close()
            self._initialized = False
            logger.info("Secure GPU engine cleaned up")
            
    @retry(
        stop=stop_after_attempt(5),  # More retries for GPU due to cost
        wait=wait_exponential(multiplier=2, min=2, max=30),  # Longer delays
        retry=lambda retry_state: isinstance(retry_state.outcome.exception(), ModalAPIError)
    )
    async def process_document(self, file_url: str, **kwargs) -> Dict[str, Any]:
        """Process document using Modal GPU endpoint with comprehensive security."""
        if not self._initialized:
            await self.initialize()
            
        start_time = time.time()
        request_id = f"gpu_{int(start_time)}_{hash(file_url) % 10000}"
        
        logger.info("Starting secure GPU document processing",
                   request_id=request_id,
                   file_url=file_url,
                   engine="gpu")
        
        try:
            # Validate input
            if not file_url or not isinstance(file_url, str):
                raise ValueError("Invalid file_url provided")
                
            # Call Modal GPU endpoint
            response = await self.client.call_gpu_endpoint(
                file_url=file_url,
                model="deepseek-ocr"
            )
            
            # Process response
            processing_time = time.time() - start_time
            
            # Extract text content
            extracted_text = response.get("text", "")
            confidence = response.get("confidence", 0.0)
            ocr_confidence = response.get("ocr_confidence", 0.0)
            metadata = response.get("metadata", {})
            
            # Validate response quality
            if not extracted_text or len(extracted_text.strip()) < 10:
                logger.warning("Low quality extraction from GPU endpoint",
                             request_id=request_id,
                             text_length=len(extracted_text),
                             confidence=confidence,
                             ocr_confidence=ocr_confidence)
                
            result = {
                "success": True,
                "text": extracted_text,
                "confidence": confidence,
                "ocr_confidence": ocr_confidence,
                "processing_time": processing_time,
                "request_id": request_id,
                "engine": "gpu",
                "metadata": {
                    **metadata,
                    "processing_method": "gpu_modal",
                    "timestamp": datetime.utcnow().isoformat(),
                    "file_url": file_url,
                    "ocr_enabled": True
                }
            }
            
            logger.info("Secure GPU processing completed successfully",
                       request_id=request_id,
                       processing_time=processing_time,
                       text_length=len(extracted_text),
                       confidence=confidence,
                       ocr_confidence=ocr_confidence)
            
            return result
            
        except ModalAPIError as e:
            logger.error("Modal API error in GPU engine",
                        request_id=request_id,
                        error=str(e),
                        file_url=file_url)
            raise
            
        except Exception as e:
            logger.error("Unexpected error in GPU engine",
                        request_id=request_id,
                        error=str(e),
                        file_url=file_url)
            raise RuntimeError(f"GPU processing failed: {str(e)}")
            
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on GPU engine."""
        if not self._initialized:
            await self.initialize()
            
        try:
            health_status = await self.client.health_check()
            
            # Focus on GPU endpoint health
            gpu_health = health_status.get("gpu_endpoint", {})
            
            return {
                "status": "healthy" if gpu_health.get("status") == "ok" else "unhealthy",
                "engine": "gpu",
                "endpoint_health": gpu_health,
                "client_metrics": self.client.get_metrics() if self.client else {},
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error("GPU engine health check failed", error=str(e))
            return {
                "status": "unhealthy",
                "engine": "gpu",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
            
    def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive metrics for GPU engine."""
        return {
            "engine": "gpu",
            "initialized": self._initialized,
            "monitoring": self.monitoring_manager.get_metrics(),
            "client_status": "connected" if self.client else "disconnected"
        }

# Global GPU engine instance
_gpu_engine: Optional[SecureGPUEngine] = None

async def get_gpu_engine() -> SecureGPUEngine:
    """Get global GPU engine instance."""
    global _gpu_engine
    if _gpu_engine is None:
        _gpu_engine = SecureGPUEngine()
        await _gpu_engine.initialize()
    return _gpu_engine

async def cleanup_gpu_engine():
    """Clean up global GPU engine instance."""
    global _gpu_engine
    if _gpu_engine:
        await _gpu_engine.cleanup()
        _gpu_engine = None