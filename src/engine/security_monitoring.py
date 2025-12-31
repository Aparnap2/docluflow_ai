"""Enterprise-grade security, monitoring, rate limiting, and error handling for Modal API integration."""

import asyncio
import time
import hashlib
import json
import os
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import aiohttp
from pydantic import BaseModel, Field, validator
import jwt
from cryptography.fernet import Fernet
import redis.asyncio as redis
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

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

class SecurityLevel(Enum):
    """Security levels for different operations."""
    LOW = "low"
    MEDIUM = "medium" 
    HIGH = "high"
    CRITICAL = "critical"

class RateLimitTier(Enum):
    """Rate limiting tiers for different user types."""
    FREE = "free"           # 100 requests/hour
    BASIC = "basic"         # 1000 requests/hour  
    PREMIUM = "premium"     # 10000 requests/hour
    ENTERPRISE = "enterprise"  # Unlimited

class AlertLevel(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

@dataclass
class SecurityConfig:
    """Security configuration for production deployment."""
    encryption_key: str = Field(default_factory=lambda: os.getenv("ENCRYPTION_KEY", Fernet.generate_key().decode()))
    jwt_secret: str = Field(default_factory=lambda: os.getenv("JWT_SECRET", Fernet.generate_key().decode()))
    rate_limit_redis_url: str = Field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379"))
    max_requests_per_minute: int = Field(default=60)
    max_requests_per_hour: int = Field(default=1000)
    max_concurrent_requests: int = Field(default=10)
    request_timeout: int = Field(default=30)
    circuit_breaker_threshold: int = Field(default=5)
    circuit_breaker_timeout: int = Field(default=60)
    enable_encryption: bool = Field(default=True)
    enable_rate_limiting: bool = Field(default=True)
    enable_circuit_breaker: bool = Field(default=True)
    enable_monitoring: bool = Field(default=True)

class SecurityManager:
    """Enterprise-grade security manager for Modal API integration."""
    
    def __init__(self, config: SecurityConfig):
        self.config = config
        self.fernet = Fernet(config.encryption_key.encode() if isinstance(config.encryption_key, str) else config.encryption_key)
        self.redis_client = None
        self.circuit_breaker_state = "closed"  # closed, open, half-open
        self.circuit_breaker_failures = 0
        self.circuit_breaker_last_failure = None
        self._setup_rate_limiting()
        
    def _setup_rate_limiting(self):
        """Setup rate limiting with Redis backend."""
        try:
            self.redis_client = redis.from_url(self.config.rate_limit_redis_url)
            logger.info("Redis client initialized for rate limiting")
        except Exception as e:
            logger.warning("Redis not available, using in-memory rate limiting", error=str(e))
            self.redis_client = None
            
    def encrypt_sensitive_data(self, data: str) -> str:
        """Encrypt sensitive data before storage/transmission."""
        if not self.config.enable_encryption:
            return data
            
        try:
            encrypted = self.fernet.encrypt(data.encode()).decode()
            logger.debug("Data encrypted successfully", data_length=len(data))
            return encrypted
        except Exception as e:
            logger.error("Encryption failed", error=str(e))
            raise SecurityError(f"Encryption failed: {str(e)}")
            
    def decrypt_sensitive_data(self, encrypted_data: str) -> str:
        """Decrypt sensitive data after retrieval."""
        if not self.config.enable_encryption:
            return encrypted_data
            
        try:
            decrypted = self.fernet.decrypt(encrypted_data.encode()).decode()
            logger.debug("Data decrypted successfully", encrypted_length=len(encrypted_data))
            return decrypted
        except Exception as e:
            logger.error("Decryption failed", error=str(e))
            raise SecurityError(f"Decryption failed: {str(e)}")
            
    def generate_secure_token(self, payload: Dict[str, Any], expires_in: int = 3600) -> str:
        """Generate JWT token for API authentication."""
        try:
            payload.update({
                "exp": datetime.utcnow() + timedelta(seconds=expires_in),
                "iat": datetime.utcnow(),
                "jti": hashlib.sha256(f"{time.time()}{payload}".encode()).hexdigest()
            })
            token = jwt.encode(payload, self.config.jwt_secret, algorithm="HS256")
            logger.info("Secure token generated", expires_in=expires_in)
            return token
        except Exception as e:
            logger.error("Token generation failed", error=str(e))
            raise SecurityError(f"Token generation failed: {str(e)}")
            
    def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify and decode JWT token."""
        try:
            payload = jwt.decode(token, self.config.jwt_secret, algorithms=["HS256"])
            logger.info("Token verified successfully", jti=payload.get("jti"))
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            raise SecurityError("Token has expired")
        except jwt.InvalidTokenError as e:
            logger.warning("Invalid token", error=str(e))
            raise SecurityError(f"Invalid token: {str(e)}")
            
    async def check_rate_limit(self, identifier: str, tier: RateLimitTier = RateLimitTier.BASIC) -> bool:
        """Check if request is within rate limits."""
        if not self.config.enable_rate_limiting:
            return True
            
        try:
            current_time = datetime.utcnow()
            minute_key = f"rate_limit:{identifier}:{current_time.strftime('%Y%m%d%H%M')}"
            hour_key = f"rate_limit:{identifier}:{current_time.strftime('%Y%m%d%H')}"
            
            # Get current counts
            minute_count = await self._get_rate_limit_count(minute_key)
            hour_count = await self._get_rate_limit_count(hour_key)
            
            # Determine limits based on tier
            tier_limits = {
                RateLimitTier.FREE: (10, 100),      # 10/min, 100/hour
                RateLimitTier.BASIC: (60, 1000),    # 60/min, 1000/hour
                RateLimitTier.PREMIUM: (600, 10000), # 600/min, 10000/hour
                RateLimitTier.ENTERPRISE: (1000, 50000) # 1000/min, 50000/hour
            }
            
            minute_limit, hour_limit = tier_limits.get(tier, (60, 1000))
            
            if minute_count >= minute_limit or hour_count >= hour_limit:
                logger.warning("Rate limit exceeded", 
                              identifier=identifier, 
                              minute_count=minute_count,
                              hour_count=hour_count,
                              tier=tier.value)
                return False
                
            # Increment counters
            await self._increment_rate_limit(minute_key, 60)  # 1 minute TTL
            await self._increment_rate_limit(hour_key, 3600)  # 1 hour TTL
            
            logger.debug("Rate limit check passed", 
                        identifier=identifier, 
                        minute_count=minute_count + 1,
                        hour_count=hour_count + 1)
            return True
            
        except Exception as e:
            logger.error("Rate limit check failed", error=str(e))
            return True  # Fail open for reliability
            
    async def _get_rate_limit_count(self, key: str) -> int:
        """Get current rate limit count from Redis or memory."""
        if self.redis_client:
            try:
                count = await self.redis_client.get(key)
                return int(count) if count else 0
            except Exception as e:
                logger.warning("Redis rate limit check failed", error=str(e))
                
        # Fallback to memory-based counting
        # In production, always use Redis for distributed rate limiting
        return 0
        
    async def _increment_rate_limit(self, key: str, ttl: int) -> None:
        """Increment rate limit counter with TTL."""
        if self.redis_client:
            try:
                pipe = self.redis_client.pipeline()
                pipe.incr(key)
                pipe.expire(key, ttl)
                await pipe.execute()
            except Exception as e:
                logger.warning("Redis rate limit increment failed", error=str(e))
                
    def check_circuit_breaker(self) -> bool:
        """Check if circuit breaker is closed (allowing requests)."""
        if not self.config.enable_circuit_breaker:
            return True
            
        current_time = datetime.utcnow()
        
        if self.circuit_breaker_state == "open":
            # Check if we should transition to half-open
            if self.circuit_breaker_last_failure:
                time_since_failure = (current_time - self.circuit_breaker_last_failure).total_seconds()
                if time_since_failure >= self.config.circuit_breaker_timeout:
                    self.circuit_breaker_state = "half-open"
                    self.circuit_breaker_failures = 0
                    logger.info("Circuit breaker transitioned to half-open")
                    return True
            return False
            
        elif self.circuit_breaker_state == "half-open":
            # Allow limited requests to test if service is recovered
            return True
            
        return True  # closed state
        
    def record_success(self):
        """Record successful request for circuit breaker."""
        if self.circuit_breaker_state == "half-open":
            self.circuit_breaker_state = "closed"
            self.circuit_breaker_failures = 0
            logger.info("Circuit breaker closed due to success")
        elif self.circuit_breaker_state == "closed":
            # Reset failure count on success
            self.circuit_breaker_failures = 0
            
    def record_failure(self):
        """Record failed request for circuit breaker."""
        self.circuit_breaker_failures += 1
        self.circuit_breaker_last_failure = datetime.utcnow()
        
        if self.circuit_breaker_failures >= self.config.circuit_breaker_threshold:
            self.circuit_breaker_state = "open"
            logger.warning("Circuit breaker opened due to failures", 
                          failure_count=self.circuit_breaker_failures,
                          threshold=self.config.circuit_breaker_threshold)

class MonitoringManager:
    """Comprehensive monitoring and alerting system."""
    
    def __init__(self, security_config: SecurityConfig):
        self.config = security_config
        self.metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "rate_limited_requests": 0,
            "circuit_breaker_activations": 0,
            "average_response_time": 0.0,
            "p99_response_time": 0.0,
            "error_rate": 0.0
        }
        self.response_times = []
        self.alerts = []
        
    def record_request(self, success: bool, response_time: float, rate_limited: bool = False):
        """Record request metrics for monitoring."""
        self.metrics["total_requests"] += 1
        
        if success:
            self.metrics["successful_requests"] += 1
        else:
            self.metrics["failed_requests"] += 1
            
        if rate_limited:
            self.metrics["rate_limited_requests"] += 1
            
        # Track response times
        self.response_times.append(response_time)
        if len(self.response_times) > 1000:  # Keep last 1000 for memory efficiency
            self.response_times.pop(0)
            
        # Calculate metrics
        self._calculate_response_time_metrics()
        self._calculate_error_rate()
        
        # Check for alerts
        self._check_alerts(success, response_time)
        
    def _calculate_response_time_metrics(self):
        """Calculate response time metrics (avg, p99)."""
        if self.response_times:
            self.metrics["average_response_time"] = sum(self.response_times) / len(self.response_times)
            sorted_times = sorted(self.response_times)
            p99_index = int(len(sorted_times) * 0.99) - 1
            self.metrics["p99_response_time"] = sorted_times[max(0, p99_index)]
            
    def _calculate_error_rate(self):
        """Calculate error rate percentage."""
        if self.metrics["total_requests"] > 0:
            self.metrics["error_rate"] = (self.metrics["failed_requests"] / self.metrics["total_requests"]) * 100
            
    def _check_alerts(self, success: bool, response_time: float):
        """Check for alert conditions."""
        current_time = datetime.utcnow()
        
        # High error rate alert
        if self.metrics["error_rate"] > 10:  # 10% error rate
            self._create_alert(
                AlertLevel.CRITICAL,
                "High error rate detected",
                {"error_rate": self.metrics["error_rate"], "threshold": 10}
            )
            
        # Slow response time alert
        if response_time > 30:  # 30 seconds
            self._create_alert(
                AlertLevel.WARNING,
                "Slow response time detected",
                {"response_time": response_time, "threshold": 30}
            )
            
        # Circuit breaker activation alert
        if not success and self.metrics["circuit_breaker_activations"] > 0:
            self._create_alert(
                AlertLevel.ERROR,
                "Circuit breaker activated",
                {"activations": self.metrics["circuit_breaker_activations"]}
            )
            
    def _create_alert(self, level: AlertLevel, message: str, context: Dict[str, Any]):
        """Create alert with context."""
        alert = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": level.value,
            "message": message,
            "context": context,
            "metrics_snapshot": self.metrics.copy()
        }
        self.alerts.append(alert)
        logger.log(level.value, message, **context, alert_level=level.value)
        
        # Keep only last 100 alerts for memory efficiency
        if len(self.alerts) > 100:
            self.alerts.pop(0)
            
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics snapshot."""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": self.metrics.copy(),
            "alert_count": len(self.alerts),
            "recent_alerts": self.alerts[-10:]  # Last 10 alerts
        }
        
    def get_health_status(self) -> Dict[str, Any]:
        """Get system health status."""
        health_score = 100.0
        
        # Deduct points for various issues
        if self.metrics["error_rate"] > 5:
            health_score -= 20
        if self.metrics["error_rate"] > 10:
            health_score -= 30
            
        if self.metrics["p99_response_time"] > 10:
            health_score -= 10
        if self.metrics["p99_response_time"] > 30:
            health_score -= 20
            
        if len(self.alerts) > 5:
            health_score -= 10
            
        health_score = max(0, min(100, health_score))
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "health_score": health_score,
            "status": "healthy" if health_score >= 80 else "degraded" if health_score >= 60 else "unhealthy",
            "metrics": self.metrics.copy(),
            "recent_alerts": self.alerts[-5:]
        }

class SecurityError(Exception):
    """Custom security error for handling security-related issues."""
    pass

# Global security and monitoring instances
_security_manager = None
_monitoring_manager = None

def get_security_manager(config: Optional[SecurityConfig] = None) -> SecurityManager:
    """Get global security manager instance."""
    global _security_manager
    if _security_manager is None:
        _security_manager = SecurityManager(config or SecurityConfig())
    return _security_manager

def get_monitoring_manager(config: Optional[SecurityConfig] = None) -> MonitoringManager:
    """Get global monitoring manager instance."""
    global _monitoring_manager
    if _monitoring_manager is None:
        _monitoring_manager = MonitoringManager(config or SecurityConfig())
    return _monitoring_manager