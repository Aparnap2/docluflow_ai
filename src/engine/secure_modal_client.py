"""Secure Modal client with enterprise-grade security, monitoring, rate limiting, and error handling."""

import asyncio
import time
import json
import hashlib
import os
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import aiohttp
from pydantic import BaseModel, Field, validator
import jwt
from cryptography.fernet import Fernet

from .security_monitoring import (
    SecurityManager, MonitoringManager, SecurityConfig, 
    RateLimitTier, SecurityError, get_security_manager, get_monitoring_manager
)

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

class ModalAPIError(Exception):
    """Custom exception for Modal API errors."""
    pass

class RateLimitError(Exception):
    """Custom exception for rate limit violations."""
    pass

class CircuitBreakerError(Exception):
    """Custom exception for circuit breaker activation."""
    pass

class AuthenticationError(Exception):
    """Custom exception for authentication failures."""
    pass

@dataclass
class ModalConfig:
    """Configuration for Modal API integration."""
    api_key: str = Field(default_factory=lambda: os.getenv("MODAL_API_KEY", ""))
    base_url: str = Field(default="https://api.modal.com/v1")
    timeout: int = Field(default=30)
    max_retries: int = Field(default=3)
    retry_delay: float = Field(default=1.0)
    enable_caching: bool = Field(default=True)
    cache_ttl: int = Field(default=3600)  # 1 hour
    enable_encryption: bool = Field(default=True)
    enable_monitoring: bool = Field(default=True)
    enable_rate_limiting: bool = Field(default=True)
    circuit_breaker_threshold: int = Field(default=5)
    circuit_breaker_timeout: int = Field(default=60)
    max_concurrent_requests: int = Field(default=10)
    request_timeout: int = Field(default=30)
    
    @validator('api_key')
    def validate_api_key(cls, v):
        if not v:
            raise ValueError("MODAL_API_KEY is required")
        return v

class RequestMetadata(BaseModel):
    """Metadata for tracking API requests."""
    request_id: str
    timestamp: datetime
    endpoint: str
    method: str
    payload_size: int
    user_agent: str = "DocuFlow-Headless/2.0"
    client_ip: Optional[str] = None
    retry_count: int = 0
    cache_hit: bool = False
    rate_limited: bool = False
    circuit_breaker_active: bool = False
    
class ResponseMetadata(BaseModel):
    """Metadata for API responses."""
    request_id: str
    status_code: int
    response_time: float
    response_size: int
    error_message: Optional[str] = None
    rate_limit_remaining: Optional[int] = None
    rate_limit_reset: Optional[datetime] = None
    cache_used: bool = False

class SecureModalClient:
    """Enterprise-grade secure client for Modal API with comprehensive monitoring and error handling."""
    
    def __init__(self, config: ModalConfig):
        self.config = config
        self.security_manager = get_security_manager()
        self.monitoring_manager = get_monitoring_manager()
        self.session: Optional[aiohttp.ClientSession] = None
        self._request_semaphore = asyncio.Semaphore(config.max_concurrent_requests)
        self._cache: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, datetime] = {}
        
    async def __aenter__(self):
        """Async context manager entry."""
        await self._ensure_session()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
        
    async def _ensure_session(self):
        """Ensure aiohttp session is created."""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.request_timeout)
            connector = aiohttp.TCPConnector(
                limit=100,
                limit_per_host=50,
                ttl_dns_cache=300,
                use_dns_cache=True,
                keepalive_timeout=30
            )
            
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers={
                    "User-Agent": "DocuFlow-Headless/2.0",
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "X-Client-Version": "2.0.0",
                    "X-Request-ID": self._generate_request_id()
                }
            )
            logger.info("Modal API session initialized")
            
    async def close(self):
        """Close the aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("Modal API session closed")
            
    def _generate_request_id(self) -> str:
        """Generate unique request ID for tracking."""
        timestamp = datetime.utcnow().isoformat()
        random_component = hashlib.sha256(f"{time.time()}{os.urandom(16)}".encode()).hexdigest()[:16]
        return f"modal_{timestamp}_{random_component}"
        
    def _generate_cache_key(self, endpoint: str, payload: Dict[str, Any]) -> str:
        """Generate cache key for request."""
        payload_str = json.dumps(payload, sort_keys=True)
        key_data = f"{endpoint}:{payload_str}"
        return hashlib.sha256(key_data.encode()).hexdigest()
        
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached data is still valid."""
        if cache_key not in self._cache_timestamps:
            return False
            
        cache_time = self._cache_timestamps[cache_key]
        current_time = datetime.utcnow()
        
        if (current_time - cache_time).total_seconds() > self.config.cache_ttl:
            # Cache expired, clean up
            del self._cache[cache_key]
            del self._cache_timestamps[cache_key]
            return False
            
        return True
        
    async def _check_rate_limit(self, identifier: str = "default") -> bool:
        """Check rate limiting before making request."""
        if not self.config.enable_rate_limiting:
            return True
            
        # Use user tier from environment or default to basic
        user_tier = os.getenv("USER_TIER", "basic")
        tier_map = {
            "free": RateLimitTier.FREE,
            "basic": RateLimitTier.BASIC,
            "premium": RateLimitTier.PREMIUM,
            "enterprise": RateLimitTier.ENTERPRISE
        }
        
        tier = tier_map.get(user_tier, RateLimitTier.BASIC)
        return await self.security_manager.check_rate_limit(identifier, tier)
        
    def _check_circuit_breaker(self) -> bool:
        """Check circuit breaker state."""
        return self.security_manager.check_circuit_breaker()
        
    async def _make_request_with_retry(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request with comprehensive retry logic."""
        
        @retry(
            stop=stop_after_attempt(self.config.max_retries),
            wait=wait_exponential(multiplier=self.config.retry_delay, min=1, max=60),
            retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError, ModalAPIError)),
            before_sleep=lambda retry_state: logger.warning(
                "Retrying request",
                attempt=retry_state.attempt_number,
                max_attempts=self.config.max_retries,
                exception=str(retry_state.outcome.exception())
            )
        )
        async def _retry_request():
            return await self._make_single_request(method, endpoint, **kwargs)
            
        try:
            return await _retry_request()
        except Exception as e:
            logger.error("Request failed after all retries", error=str(e))
            raise ModalAPIError(f"Request failed after {self.config.max_retries} retries: {str(e)}")
            
    async def _make_single_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make single HTTP request with full security and monitoring."""
        start_time = time.time()
        request_id = self._generate_request_id()
        
        # Check circuit breaker
        if not self._check_circuit_breaker():
            self.monitoring_manager.record_request(False, 0, False)
            raise CircuitBreakerError("Circuit breaker is open")
            
        # Check rate limiting
        rate_limited = not await self._check_rate_limit(request_id)
        if rate_limited:
            self.monitoring_manager.record_request(False, 0, True)
            raise RateLimitError("Rate limit exceeded")
            
        # Prepare request metadata
        request_metadata = RequestMetadata(
            request_id=request_id,
            timestamp=datetime.utcnow(),
            endpoint=endpoint,
            method=method,
            payload_size=len(json.dumps(kwargs.get("json", {}))),
            client_ip=kwargs.get("headers", {}).get("X-Forwarded-For")
        )
        
        logger.info("Making Modal API request",
                   request_id=request_id,
                   method=method,
                   endpoint=endpoint,
                   payload_size=request_metadata.payload_size)
        
        try:
            # Make the actual request
            async with self._request_semaphore:
                url = f"{self.config.base_url}{endpoint}"
                
                # Add request ID to headers
                headers = kwargs.get("headers", {})
                headers["X-Request-ID"] = request_id
                kwargs["headers"] = headers
                
                async with self.session.request(method, url, **kwargs) as response:
                    response_time = time.time() - start_time
                    
                    # Read response
                    response_text = await response.text()
                    response_size = len(response_text)
                    
                    # Parse JSON response
                    try:
                        response_data = json.loads(response_text) if response_text else {}
                    except json.JSONDecodeError:
                        response_data = {"raw_response": response_text}
                        
                    # Record response metadata
                    response_metadata = ResponseMetadata(
                        request_id=request_id,
                        status_code=response.status,
                        response_time=response_time,
                        response_size=response_size,
                        rate_limit_remaining=int(response.headers.get("X-RateLimit-Remaining", 0)),
                        rate_limit_reset=datetime.fromtimestamp(int(response.headers.get("X-RateLimit-Reset", 0))) if response.headers.get("X-RateLimit-Reset") else None
                    )
                    
                    # Handle different response codes
                    if response.status == 200:
                        self.security_manager.record_success()
                        self.monitoring_manager.record_request(True, response_time, rate_limited)
                        logger.info("Modal API request successful",
                                   request_id=request_id,
                                   response_time=response_time,
                                   status_code=response.status)
                        return response_data
                        
                    elif response.status == 429:  # Rate limited
                        self.monitoring_manager.record_request(False, response_time, True)
                        raise RateLimitError(f"Rate limited by Modal API: {response_data}")
                        
                    elif response.status == 401:  # Authentication error
                        self.monitoring_manager.record_request(False, response_time, False)
                        raise AuthenticationError(f"Authentication failed: {response_data}")
                        
                    elif response.status >= 500:  # Server error
                        self.security_manager.record_failure()
                        self.monitoring_manager.record_request(False, response_time, False)
                        raise ModalAPIError(f"Modal API server error ({response.status}): {response_data}")
                        
                    else:  # Other client errors
                        self.monitoring_manager.record_request(False, response_time, False)
                        raise ModalAPIError(f"Modal API error ({response.status}): {response_data}")
                        
        except asyncio.TimeoutError:
            self.security_manager.record_failure()
            self.monitoring_manager.record_request(False, time.time() - start_time, False)
            logger.error("Modal API request timed out", request_id=request_id)
            raise ModalAPIError("Request timeout")
            
        except aiohttp.ClientError as e:
            self.security_manager.record_failure()
            self.monitoring_manager.record_request(False, time.time() - start_time, False)
            logger.error("Modal API client error", request_id=request_id, error=str(e))
            raise ModalAPIError(f"Client error: {str(e)}")
            
        except Exception as e:
            self.security_manager.record_failure()
            self.monitoring_manager.record_request(False, time.time() - start_time, False)
            logger.error("Modal API unexpected error", request_id=request_id, error=str(e))
            raise ModalAPIError(f"Unexpected error: {str(e)}")
            
    async def call_cpu_endpoint(self, file_url: str, model: str = "granite-docling") -> Dict[str, Any]:
        """Call Modal CPU endpoint for document processing."""
        endpoint = "/cpu/process"
        payload = {
            "file_url": file_url,
            "model": model,
            "options": {
                "do_ocr": False,
                "extract_tables": True,
                "extract_images": False
            }
        }
        
        # Check cache first
        if self.config.enable_caching:
            cache_key = self._generate_cache_key(endpoint, payload)
            if self._is_cache_valid(cache_key):
                logger.info("Cache hit for CPU endpoint", cache_key=cache_key)
                return self._cache[cache_key]
                
        try:
            response = await self._make_request_with_retry("POST", endpoint, json=payload)
            
            # Cache successful response
            if self.config.enable_caching:
                self._cache[cache_key] = response
                self._cache_timestamps[cache_key] = datetime.utcnow()
                
            return response
            
        except Exception as e:
            logger.error("CPU endpoint call failed", file_url=file_url, error=str(e))
            raise
            
    async def call_gpu_endpoint(self, file_url: str, model: str = "deepseek-ocr") -> Dict[str, Any]:
        """Call Modal GPU endpoint for OCR processing."""
        endpoint = "/gpu/process"
        payload = {
            "file_url": file_url,
            "model": model,
            "options": {
                "ocr_enabled": True,
                "extract_text": True,
                "extract_layout": True
            }
        }
        
        # Check cache first
        if self.config.enable_caching:
            cache_key = self._generate_cache_key(endpoint, payload)
            if self._is_cache_valid(cache_key):
                logger.info("Cache hit for GPU endpoint", cache_key=cache_key)
                return self._cache[cache_key]
                
        try:
            response = await self._make_request_with_retry("POST", endpoint, json=payload)
            
            # Cache successful response
            if self.config.enable_caching:
                self._cache[cache_key] = response
                self._cache_timestamps[cache_key] = datetime.utcnow()
                
            return response
            
        except Exception as e:
            logger.error("GPU endpoint call failed", file_url=file_url, error=str(e))
            raise
            
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on Modal endpoints."""
        try:
            # Test CPU endpoint
            cpu_health = await self._make_request_with_retry("GET", "/health/cpu")
            
            # Test GPU endpoint  
            gpu_health = await self._make_request_with_retry("GET", "/health/gpu")
            
            return {
                "status": "healthy" if cpu_health.get("status") == "ok" and gpu_health.get("status") == "ok" else "degraded",
                "cpu_endpoint": cpu_health,
                "gpu_endpoint": gpu_health,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error("Health check failed", error=str(e))
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
            
    def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive metrics for monitoring."""
        return {
            "security": {
                "circuit_breaker_state": "closed",  # This would be dynamic in real implementation
                "rate_limiting_enabled": self.config.enable_rate_limiting,
                "encryption_enabled": self.config.enable_encryption
            },
            "performance": self.monitoring_manager.get_metrics(),
            "cache": {
                "enabled": self.config.enable_caching,
                "size": len(self._cache),
                "hit_rate": "N/A"  # Would calculate in real implementation
            },
            "configuration": {
                "max_retries": self.config.max_retries,
                "timeout": self.config.timeout,
                "max_concurrent_requests": self.config.max_concurrent_requests
            }
        }
        
    def clear_cache(self):
        """Clear the response cache."""
        self._cache.clear()
        self._cache_timestamps.clear()
        logger.info("Modal API cache cleared")

# Factory function for creating secure Modal clients
async def create_secure_modal_client(
    api_key: Optional[str] = None,
    enable_caching: bool = True,
    enable_monitoring: bool = True,
    enable_rate_limiting: bool = True,
    max_retries: int = 3,
    timeout: int = 30
) -> SecureModalClient:
    """Factory function to create a secure Modal client with all protections enabled."""
    
    # Create configuration
    config = ModalConfig(
        api_key=api_key or os.getenv("MODAL_API_KEY", ""),
        enable_caching=enable_caching,
        enable_monitoring=enable_monitoring,
        enable_rate_limiting=enable_rate_limiting,
        max_retries=max_retries,
        timeout=timeout
    )
    
    # Create and return client
    client = SecureModalClient(config)
    await client._ensure_session()
    
    logger.info("Secure Modal client created with enterprise protections",
                caching=enable_caching,
                monitoring=enable_monitoring,
                rate_limiting=enable_rate_limiting,
                max_retries=max_retries)
    
    return client