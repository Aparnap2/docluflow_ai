"""Secure CPU engine with Modal API integration and comprehensive error handling."""

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

class SecureCPUEngine:
    """Secure CPU engine with Modal API integration and comprehensive monitoring."""
    
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
                max_retries=3,
                timeout=30
            )
            self._initialized = True
            logger.info("Secure CPU engine initialized successfully")
            
        except Exception as e:
            logger.error("Failed to initialize secure CPU engine", error=str(e))
            raise RuntimeError(f"CPU engine initialization failed: {str(e)}")
            
    async def cleanup(self) -> None:
        """Clean up resources."""
        if self.client:
            await self.client.close()
            self._initialized = False
            logger.info("Secure CPU engine cleaned up")
            
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=lambda retry_state: isinstance(retry_state.outcome.exception(), ModalAPIError)
    )
    async def process_document(self, file_url: str, **kwargs) -> Dict[str, Any]:
        """Process document using Modal CPU endpoint with comprehensive security."""
        if not self._initialized:
            await self.initialize()
            
        start_time = time.time()
        request_id = f"cpu_{int(start_time)}_{hash(file_url) % 10000}"
        
        logger.info("Starting secure CPU document processing",
                   request_id=request_id,
                   file_url=file_url,
                   engine="cpu")
        
        try:
            # Validate input
            if not file_url or not isinstance(file_url, str):
                raise ValueError("Invalid file_url provided")
                
            # Call Modal CPU endpoint
            response = await self.client.call_cpu_endpoint(
                file_url=file_url,
                model="granite-docling"
            )
            
            # Process response
            processing_time = time.time() - start_time
            
            # Extract text content
            extracted_text = response.get("text", "")
            confidence = response.get("confidence", 0.0)
            metadata = response.get("metadata", {})
            
            # Validate response quality
            if not extracted_text or len(extracted_text.strip()) < 10:
                logger.warning("Low quality extraction from CPU endpoint",
                             request_id=request_id,
                             text_length=len(extracted_text),
                             confidence=confidence)
                
            result = {
                "success": True,
                "text": extracted_text,
                "confidence": confidence,
                "processing_time": processing_time,
                "request_id": request_id,
                "engine": "cpu",
                "metadata": {
                    **metadata,
                    "processing_method": "cpu_modal",
                    "timestamp": datetime.utcnow().isoformat(),
                    "file_url": file_url
                }
            }
            
            logger.info("Secure CPU processing completed successfully",
                       request_id=request_id,
                       processing_time=processing_time,
                       text_length=len(extracted_text),
                       confidence=confidence)
            
            return result
            
        except ModalAPIError as e:
            logger.error("Modal API error in CPU engine",
                        request_id=request_id,
                        error=str(e),
                        file_url=file_url)
            raise
            
        except Exception as e:
            logger.error("Unexpected error in CPU engine",
                        request_id=request_id,
                        error=str(e),
                        file_url=file_url)
            raise RuntimeError(f"CPU processing failed: {str(e)}")
            
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on CPU engine."""
        if not self._initialized:
            await self.initialize()
            
        try:
            health_status = await self.client.health_check()
            
            # Focus on CPU endpoint health
            cpu_health = health_status.get("cpu_endpoint", {})
            
            return {
                "status": "healthy" if cpu_health.get("status") == "ok" else "unhealthy",
                "engine": "cpu",
                "endpoint_health": cpu_health,
                "client_metrics": self.client.get_metrics() if self.client else {},
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error("CPU engine health check failed", error=str(e))
            return {
                "status": "unhealthy",
                "engine": "cpu",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
            
    def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive metrics for CPU engine."""
        return {
            "engine": "cpu",
            "initialized": self._initialized,
            "monitoring": self.monitoring_manager.get_metrics(),
            "client_status": "connected" if self.client else "disconnected"
        }

# Global CPU engine instance
_cpu_engine: Optional[SecureCPUEngine] = None

async def get_cpu_engine() -> SecureCPUEngine:
    """Get global CPU engine instance."""
    global _cpu_engine
    if _cpu_engine is None:
        _cpu_engine = SecureCPUEngine()
        await _cpu_engine.initialize()
    return _cpu_engine

async def cleanup_cpu_engine():
    """Clean up global CPU engine instance."""
    global _cpu_engine
    if _cpu_engine:
        await _cpu_engine.cleanup()
        _cpu_engine = None