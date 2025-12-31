"""Security configuration for production Modal API integration."""

import os
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, validator
from enum import Enum

class Environment(str, Enum):
    """Deployment environments."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"

class SecurityLevel(str, Enum):
    """Security levels for different operations."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class RateLimitTier(str, Enum):
    """Rate limiting tiers for different user types."""
    FREE = "free"
    BASIC = "basic"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"

class SecurityConfig(BaseModel):
    """Comprehensive security configuration for Modal API integration."""
    
    # Environment
    environment: Environment = Field(default=Environment.PRODUCTION)
    
    # API Configuration
    modal_api_key: str = Field(default_factory=lambda: os.getenv("MODAL_API_KEY", ""))
    modal_base_url: str = Field(default="https://api.modal.com/v1")
    api_timeout: int = Field(default=30)
    max_retries: int = Field(default=3)
    
    # Security Settings
    encryption_key: str = Field(default_factory=lambda: os.getenv("ENCRYPTION_KEY", ""))
    jwt_secret: str = Field(default_factory=lambda: os.getenv("JWT_SECRET", ""))
    enable_encryption: bool = Field(default=True)
    security_level: SecurityLevel = Field(default=SecurityLevel.HIGH)
    
    # Rate Limiting
    enable_rate_limiting: bool = Field(default=True)
    redis_url: str = Field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379"))
    max_requests_per_minute: int = Field(default=60)
    max_requests_per_hour: int = Field(default=1000)
    max_concurrent_requests: int = Field(default=10)
    user_tier: RateLimitTier = Field(default=RateLimitTier.BASIC)
    
    # Circuit Breaker
    enable_circuit_breaker: bool = Field(default=True)
    circuit_breaker_threshold: int = Field(default=5)
    circuit_breaker_timeout: int = Field(default=60)
    
    # Monitoring
    enable_monitoring: bool = Field(default=True)
    enable_logging: bool = Field(default=True)
    log_level: str = Field(default="INFO")
    enable_metrics: bool = Field(default=True)
    
    # Caching
    enable_caching: bool = Field(default=True)
    cache_ttl: int = Field(default=3600)  # 1 hour
    max_cache_size: int = Field(default=1000)
    
    # Error Handling
    enable_error_tracking: bool = Field(default=True)
    sentry_dsn: Optional[str] = Field(default_factory=lambda: os.getenv("SENTRY_DSN"))
    
    # Compliance
    enable_audit_logging: bool = Field(default=True)
    data_retention_days: int = Field(default=30)
    enable_data_anonymization: bool = Field(default=True)
    
    @validator('modal_api_key')
    def validate_modal_api_key(cls, v):
        if not v:
            raise ValueError("MODAL_API_KEY is required for production")
        return v
        
    @validator('encryption_key')
    def validate_encryption_key(cls, v):
        if not v and os.getenv("ENABLE_ENCRYPTION", "true").lower() == "true":
            # Generate a secure key if not provided
            from cryptography.fernet import Fernet
            return Fernet.generate_key().decode()
        return v
        
    @validator('jwt_secret')
    def validate_jwt_secret(cls, v):
        if not v:
            # Generate a secure secret if not provided
            import secrets
            return secrets.token_urlsafe(32)
        return v
        
    @validator('redis_url')
    def validate_redis_url(cls, v):
        if not v and os.getenv("ENABLE_RATE_LIMITING", "true").lower() == "true":
            raise ValueError("REDIS_URL is required when rate limiting is enabled")
        return v

class ProductionSecurityConfig(SecurityConfig):
    """Production-specific security configuration with stricter defaults."""
    
    environment: Environment = Field(default=Environment.PRODUCTION)
    security_level: SecurityLevel = Field(default=SecurityLevel.CRITICAL)
    enable_encryption: bool = Field(default=True)
    enable_rate_limiting: bool = Field(default=True)
    enable_circuit_breaker: bool = Field(default=True)
    enable_monitoring: bool = Field(default=True)
    enable_audit_logging: bool = Field(default=True)
    enable_error_tracking: bool = Field(default=True)
    
    max_requests_per_minute: int = Field(default=30)  # Stricter for production
    max_requests_per_hour: int = Field(default=500)
    max_concurrent_requests: int = Field(default=5)
    circuit_breaker_threshold: int = Field(default=3)  # More sensitive
    circuit_breaker_timeout: int = Field(default=120)  # Longer timeout
    
    cache_ttl: int = Field(default=1800)  # 30 minutes
    data_retention_days: int = Field(default=90)  # Longer retention

class DevelopmentSecurityConfig(SecurityConfig):
    """Development-specific security configuration with relaxed defaults."""
    
    environment: Environment = Field(default=Environment.DEVELOPMENT)
    security_level: SecurityLevel = Field(default=SecurityLevel.LOW)
    enable_encryption: bool = Field(default=False)  # Disabled for dev
    enable_rate_limiting: bool = Field(default=False)  # Disabled for dev
    enable_circuit_breaker: bool = Field(default=False)  # Disabled for dev
    enable_monitoring: bool = Field(default=True)
    enable_audit_logging: bool = Field(default=False)  # Disabled for dev
    enable_error_tracking: bool = Field(default=False)  # Disabled for dev
    
    max_requests_per_minute: int = Field(default=1000)  # Very permissive
    max_requests_per_hour: int = Field(default=10000)
    max_concurrent_requests: int = Field(default=50)
    circuit_breaker_threshold: int = Field(default=10)
    circuit_breaker_timeout: int = Field(default=30)
    
    cache_ttl: int = Field(default=300)  # 5 minutes
    data_retention_days: int = Field(default=7)  # Shorter retention

def get_security_config(environment: Optional[str] = None) -> SecurityConfig:
    """Get security configuration based on environment."""
    env = environment or os.getenv("ENVIRONMENT", "production").lower()
    
    if env == "development":
        return DevelopmentSecurityConfig()
    elif env == "staging":
        # Staging uses production config but with some relaxed settings
        config = ProductionSecurityConfig()
        config.max_requests_per_minute = 60
        config.max_requests_per_hour = 1000
        return config
    else:
        return ProductionSecurityConfig()

def validate_security_requirements() -> Dict[str, Any]:
    """Validate that all security requirements are met."""
    config = get_security_config()
    issues = []
    warnings = []
    
    # Check required environment variables
    required_vars = ["MODAL_API_KEY"]
    if config.enable_encryption:
        required_vars.append("ENCRYPTION_KEY")
    if config.enable_rate_limiting:
        required_vars.append("REDIS_URL")
    if config.enable_error_tracking and config.sentry_dsn:
        required_vars.append("SENTRY_DSN")
        
    for var in required_vars:
        if not os.getenv(var):
            if var == "ENCRYPTION_KEY" and not config.enable_encryption:
                continue
            if var == "REDIS_URL" and not config.enable_rate_limiting:
                continue
            if var == "SENTRY_DSN" and not config.enable_error_tracking:
                continue
            issues.append(f"Missing required environment variable: {var}")
    
    # Check security level appropriateness
    if config.environment == Environment.PRODUCTION and config.security_level != SecurityLevel.CRITICAL:
        warnings.append("Production environment should use CRITICAL security level")
        
    # Check rate limiting settings
    if config.enable_rate_limiting:
        if config.max_requests_per_minute > 100:
            warnings.append("High rate limit may impact service stability")
        if config.max_requests_per_hour > 10000:
            warnings.append("Very high hourly rate limit detected")
            
    # Check circuit breaker settings
    if config.enable_circuit_breaker:
        if config.circuit_breaker_threshold > 10:
            warnings.append("High circuit breaker threshold may delay failure detection")
        if config.circuit_breaker_timeout < 30:
            warnings.append("Short circuit breaker timeout may cause premature recovery")
            
    return {
        "config_valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "security_score": max(0, 100 - (len(issues) * 20) - (len(warnings) * 5)),
        "recommendations": [
            "Enable encryption for sensitive data",
            "Use Redis for distributed rate limiting",
            "Configure Sentry for error tracking",
            "Set up audit logging for compliance",
            "Regularly rotate API keys and secrets"
        ]
    }

# Security headers for HTTP responses
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()"
}

# Rate limit configurations by tier
RATE_LIMIT_CONFIGS = {
    RateLimitTier.FREE: {
        "requests_per_minute": 10,
        "requests_per_hour": 100,
        "concurrent_requests": 2,
        "burst_capacity": 5
    },
    RateLimitTier.BASIC: {
        "requests_per_minute": 60,
        "requests_per_hour": 1000,
        "concurrent_requests": 5,
        "burst_capacity": 10
    },
    RateLimitTier.PREMIUM: {
        "requests_per_minute": 300,
        "requests_per_hour": 5000,
        "concurrent_requests": 10,
        "burst_capacity": 20
    },
    RateLimitTier.ENTERPRISE: {
        "requests_per_minute": 1000,
        "requests_per_hour": 50000,
        "concurrent_requests": 50,
        "burst_capacity": 100
    }
}

# Error messages for different scenarios
ERROR_MESSAGES = {
    "RATE_LIMIT_EXCEEDED": "Rate limit exceeded. Please try again later.",
    "CIRCUIT_BREAKER_OPEN": "Service temporarily unavailable. Please try again later.",
    "AUTHENTICATION_FAILED": "Authentication failed. Please check your API key.",
    "INVALID_REQUEST": "Invalid request format. Please check your input.",
    "SERVICE_UNAVAILABLE": "Service temporarily unavailable. Please try again later.",
    "INTERNAL_ERROR": "Internal server error. Please contact support.",
    "TIMEOUT_ERROR": "Request timeout. Please try again with a smaller file.",
    "QUOTA_EXCEEDED": "API quota exceeded. Please upgrade your plan."
}

# Monitoring thresholds
MONITORING_THRESHOLDS = {
    "error_rate_warning": 5.0,  # 5% error rate
    "error_rate_critical": 10.0,  # 10% error rate
    "response_time_warning": 10.0,  # 10 seconds
    "response_time_critical": 30.0,  # 30 seconds
    "circuit_breaker_threshold": 5,  # 5 failures
    "health_check_interval": 30  # 30 seconds
}