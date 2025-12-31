"""Comprehensive test suite for security, monitoring, rate limiting, and error handling features."""

import asyncio
import pytest
import os
import time
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta
import json

from src.engine.security_monitoring import (
    SecurityManager, MonitoringManager, SecurityConfig, 
    RateLimitTier, SecurityError, get_security_manager, get_monitoring_manager
)
from src.engine.secure_modal_client import (
    SecureModalClient, create_secure_modal_client, ModalAPIError, 
    RateLimitError, CircuitBreakerError, AuthenticationError
)
from src.engine.secure_engine_cpu import SecureCPUEngine, get_cpu_engine
from src.engine.secure_engine_gpu import SecureGPUEngine, get_gpu_engine
from src.engine.secure_orchestrator import SecureOrchestrator, get_orchestrator
from src.config.security_config import get_security_config, validate_security_requirements

# Test configuration
TEST_MODAL_API_KEY = "test_modal_api_key_12345"
TEST_ENCRYPTION_KEY = "test_encryption_key_1234567890123456"
TEST_JWT_SECRET = "test_jwt_secret_12345678901234567890123456789012"

@pytest.fixture
def security_config():
    """Create test security configuration."""
    return SecurityConfig(
        modal_api_key=TEST_MODAL_API_KEY,
        encryption_key=TEST_ENCRYPTION_KEY,
        jwt_secret=TEST_JWT_SECRET,
        enable_rate_limiting=False,  # Disabled for tests
        enable_circuit_breaker=False,  # Disabled for tests
        environment="development"
    )

@pytest.fixture
async def security_manager(security_config):
    """Create security manager for testing."""
    return SecurityManager(security_config)

@pytest.fixture
async def monitoring_manager(security_config):
    """Create monitoring manager for testing."""
    return MonitoringManager(security_config)

@pytest.fixture
async def secure_modal_client(security_config):
    """Create secure Modal client for testing."""
    with patch('aiohttp.ClientSession') as mock_session:
        mock_session.return_value = AsyncMock()
        client = await create_secure_modal_client(
            api_key=TEST_MODAL_API_KEY,
            enable_caching=True,
            enable_monitoring=True,
            enable_rate_limiting=False,  # Disabled for tests
            max_retries=2,
            timeout=10
        )
        yield client
        await client.close()

class TestSecurityManager:
    """Test security manager functionality."""
    
    @pytest.mark.asyncio
    async def test_encryption_decryption(self, security_manager):
        """Test data encryption and decryption."""
        test_data = "sensitive_api_key_12345"
        
        # Encrypt data
        encrypted = security_manager.encrypt_sensitive_data(test_data)
        assert encrypted != test_data
        assert len(encrypted) > 0
        
        # Decrypt data
        decrypted = security_manager.decrypt_sensitive_data(encrypted)
        assert decrypted == test_data
        
    @pytest.mark.asyncio
    async def test_jwt_token_generation(self, security_manager):
        """Test JWT token generation and verification."""
        payload = {"user_id": "test_user", "tier": "premium"}
        
        # Generate token
        token = security_manager.generate_secure_token(payload, expires_in=3600)
        assert token is not None
        assert len(token) > 0
        
        # Verify token
        decoded_payload = security_manager.verify_token(token)
        assert decoded_payload["user_id"] == payload["user_id"]
        assert decoded_payload["tier"] == payload["tier"]
        
    @pytest.mark.asyncio
    async def test_jwt_token_expiration(self, security_manager):
        """Test JWT token expiration handling."""
        payload = {"user_id": "test_user"}
        
        # Generate token with short expiration
        token = security_manager.generate_secure_token(payload, expires_in=1)
        
        # Wait for expiration
        await asyncio.sleep(2)
        
        # Verify token should fail
        with pytest.raises(SecurityError):
            security_manager.verify_token(token)
            
    @pytest.mark.asyncio
    async def test_rate_limiting_disabled(self, security_manager):
        """Test rate limiting when disabled."""
        # Should always return True when disabled
        result = await security_manager.check_rate_limit("test_user")
        assert result is True
        
    @pytest.mark.asyncio
    async def test_circuit_breaker_initial_state(self, security_manager):
        """Test circuit breaker initial state."""
        assert security_manager.check_circuit_breaker() is True
        assert security_manager.circuit_breaker_state == "closed"
        
    @pytest.mark.asyncio
    async def test_circuit_breaker_failure_recording(self, security_manager):
        """Test circuit breaker failure recording."""
        # Record failures
        for i in range(security_manager.config.circuit_breaker_threshold):
            security_manager.record_failure()
            
        # Circuit breaker should open
        assert security_manager.circuit_breaker_state == "open"
        assert security_manager.check_circuit_breaker() is False
        
    @pytest.mark.asyncio
    async def test_circuit_breaker_success_recording(self, security_manager):
        """Test circuit breaker success recording."""
        # Open circuit breaker first
        for i in range(security_manager.config.circuit_breaker_threshold):
            security_manager.record_failure()
            
        assert security_manager.circuit_breaker_state == "open"
        
        # Record success in half-open state
        security_manager.circuit_breaker_state = "half-open"
        security_manager.record_success()
        
        # Should close the circuit breaker
        assert security_manager.circuit_breaker_state == "closed"
        assert security_manager.circuit_breaker_failures == 0

class TestMonitoringManager:
    """Test monitoring manager functionality."""
    
    @pytest.mark.asyncio
    async def test_request_metrics_recording(self, monitoring_manager):
        """Test request metrics recording."""
        # Record successful request
        monitoring_manager.record_request(True, 1.5, False)
        
        metrics = monitoring_manager.get_metrics()
        assert metrics["metrics"]["total_requests"] == 1
        assert metrics["metrics"]["successful_requests"] == 1
        assert metrics["metrics"]["failed_requests"] == 0
        assert metrics["metrics"]["average_response_time"] == 1.5
        
    @pytest.mark.asyncio
    async def test_error_rate_calculation(self, monitoring_manager):
        """Test error rate calculation."""
        # Record mixed requests
        for i in range(8):
            monitoring_manager.record_request(True, 1.0, False)
        for i in range(2):
            monitoring_manager.record_request(False, 1.0, False)
            
        metrics = monitoring_manager.get_metrics()
        assert metrics["metrics"]["error_rate"] == 20.0  # 2 out of 10
        
    @pytest.mark.asyncio
    async def test_alert_generation(self, monitoring_manager):
        """Test alert generation for high error rate."""
        # Generate high error rate
        for i in range(10):
            monitoring_manager.record_request(False, 1.0, False)
            
        metrics = monitoring_manager.get_metrics()
        assert len(metrics["recent_alerts"]) > 0
        
        # Check for critical alert
        critical_alerts = [alert for alert in metrics["recent_alerts"] if alert["level"] == "critical"]
        assert len(critical_alerts) > 0
        
    @pytest.mark.asyncio
    async def test_health_status_calculation(self, monitoring_manager):
        """Test health status calculation."""
        # Record healthy requests
        for i in range(10):
            monitoring_manager.record_request(True, 1.0, False)
            
        health_status = monitoring_manager.get_health_status()
        assert health_status["health_score"] > 80
        assert health_status["status"] == "healthy"

class TestSecureModalClient:
    """Test secure Modal client functionality."""
    
    @pytest.mark.asyncio
    async def test_client_initialization(self, secure_modal_client):
        """Test client initialization."""
        assert secure_modal_client.config.api_key == TEST_MODAL_API_KEY
        assert secure_modal_client.config.enable_caching is True
        assert secure_modal_client.config.enable_monitoring is True
        
    @pytest.mark.asyncio
    async def test_request_id_generation(self, secure_modal_client):
        """Test unique request ID generation."""
        request_id1 = secure_modal_client._generate_request_id()
        request_id2 = secure_modal_client._generate_request_id()
        
        assert request_id1 != request_id2
        assert len(request_id1) > 0
        assert request_id2.startswith("modal_")
        
    @pytest.mark.asyncio
    async def test_cache_key_generation(self, secure_modal_client):
        """Test cache key generation."""
        endpoint = "/test"
        payload = {"key": "value", "number": 123}
        
        cache_key1 = secure_modal_client._generate_cache_key(endpoint, payload)
        cache_key2 = secure_modal_client._generate_cache_key(endpoint, payload)
        
        # Same inputs should generate same cache key
        assert cache_key1 == cache_key2
        assert len(cache_key1) == 64  # SHA256 hex length
        
    @pytest.mark.asyncio
    async def test_health_check_format(self, secure_modal_client):
        """Test health check response format."""
        with patch.object(secure_modal_client, '_make_request_with_retry') as mock_request:
            mock_request.return_value = {"status": "ok"}
            
            health_status = await secure_modal_client.health_check()
            
            assert "status" in health_status
            assert "cpu_endpoint" in health_status
            assert "gpu_endpoint" in health_status
            assert "timestamp" in health_status
            
    @pytest.mark.asyncio
    async def test_metrics_format(self, secure_modal_client):
        """Test metrics response format."""
        metrics = secure_modal_client.get_metrics()
        
        assert "security" in metrics
        assert "performance" in metrics
        assert "cache" in metrics
        assert "configuration" in metrics
        
        assert metrics["security"]["encryption_enabled"] is True
        assert metrics["cache"]["enabled"] is True

class TestSecureEngines:
    """Test secure CPU and GPU engines."""
    
    @pytest.mark.asyncio
    async def test_cpu_engine_initialization(self):
        """Test CPU engine initialization."""
        engine = SecureCPUEngine()
        await engine.initialize()
        
        assert engine._initialized is True
        assert engine.client is not None
        
        await engine.cleanup()
        
    @pytest.mark.asyncio
    async def test_gpu_engine_initialization(self):
        """Test GPU engine initialization."""
        engine = SecureGPUEngine()
        await engine.initialize()
        
        assert engine._initialized is True
        assert engine.client is not None
        
        await engine.cleanup()
        
    @pytest.mark.asyncio
    async def test_engine_health_check_format(self):
        """Test engine health check format."""
        engine = SecureCPUEngine()
        await engine.initialize()
        
        health_status = await engine.health_check()
        
        assert "status" in health_status
        assert "engine" in health_status
        assert health_status["engine"] == "cpu"
        assert "timestamp" in health_status
        
        await engine.cleanup()

class TestSecureOrchestrator:
    """Test secure orchestrator functionality."""
    
    @pytest.mark.asyncio
    async def test_orchestrator_initialization(self):
        """Test orchestrator initialization."""
        orchestrator = SecureOrchestrator()
        await orchestrator.initialize()
        
        assert orchestrator._initialized is True
        assert orchestrator.cpu_engine is not None
        assert orchestrator.gpu_engine is not None
        
        await orchestrator.cleanup()
        
    def test_text_density_calculation(self):
        """Test text density calculation."""
        orchestrator = SecureOrchestrator()
        
        # Create a mock PDF file for testing
        # This would normally be a real PDF file
        with patch('fitz.open') as mock_fitz:
            mock_doc = Mock()
            mock_doc.page_count = 3
            
            mock_page = Mock()
            mock_page.get_text.return_value = "This is sample text for testing. " * 20  # ~400 chars
            
            mock_doc.load_page.return_value = mock_page
            mock_fitz.return_value = mock_doc
            
            density_info = orchestrator.calculate_text_density("test.pdf")
            
            assert "text_density" in density_info
            assert "has_text_layer" in density_info
            assert "sampled_pages" in density_info
            
    def test_routing_decision_cpu(self):
        """Test routing decision for CPU engine."""
        orchestrator = SecureOrchestrator()
        
        density_info = {
            "text_density": 100,
            "has_text_layer": True
        }
        
        decision = orchestrator.make_routing_decision(density_info)
        
        assert decision.engine == "cpu"
        assert decision.confidence > 0.8
        assert "text layer" in decision.reasoning.lower()
        
    def test_routing_decision_gpu(self):
        """Test routing decision for GPU engine."""
        orchestrator = SecureOrchestrator()
        
        density_info = {
            "text_density": 10,
            "has_text_layer": False
        }
        
        decision = orchestrator.make_routing_decision(density_info)
        
        assert decision.engine == "gpu"
        assert decision.confidence > 0.7
        assert "ocr" in decision.reasoning.lower()

class TestSecurityConfiguration:
    """Test security configuration validation."""
    
    def test_production_config_validation(self):
        """Test production configuration validation."""
        with patch.dict(os.environ, {"MODAL_API_KEY": TEST_MODAL_API_KEY}):
            config = get_security_config("production")
            
            assert config.environment.value == "production"
            assert config.security_level.value == "critical"
            assert config.enable_encryption is True
            assert config.enable_rate_limiting is True
            
    def test_development_config_validation(self):
        """Test development configuration validation."""
        config = get_security_config("development")
        
        assert config.environment.value == "development"
        assert config.security_level.value == "low"
        assert config.enable_encryption is False
        assert config.enable_rate_limiting is False
        
    def test_security_requirements_validation(self):
        """Test security requirements validation."""
        with patch.dict(os.environ, {"MODAL_API_KEY": TEST_MODAL_API_KEY}):
            validation_result = validate_security_requirements()
            
            assert "config_valid" in validation_result
            assert "issues" in validation_result
            assert "warnings" in validation_result
            assert "security_score" in validation_result
            
    def test_missing_api_key_validation(self):
        """Test validation with missing API key."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError):
                get_security_config("production")

class TestIntegration:
    """Integration tests for the complete security system."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_secure_processing(self):
        """Test end-to-end secure document processing."""
        orchestrator = SecureOrchestrator()
        await orchestrator.initialize()
        
        # Mock file processing
        with patch.object(orchestrator, 'calculate_text_density') as mock_density:
            mock_density.return_value = {
                "text_density": 100,
                "has_text_layer": True
            }
            
            with patch.object(orchestrator.cpu_engine, 'process_document') as mock_process:
                mock_process.return_value = {
                    "success": True,
                    "text": "Extracted text content",
                    "confidence": 0.95,
                    "processing_time": 2.5,
                    "request_id": "test_123",
                    "engine": "cpu",
                    "metadata": {}
                }
                
                result = await orchestrator.process_document(
                    file_path="test.pdf",
                    file_url="https://example.com/test.pdf"
                )
                
                assert result.success is True
                assert result.engine == "cpu"
                assert result.text == "Extracted text content"
                assert result.routing_decision is not None
                assert result.routing_decision.engine == "cpu"
                
        await orchestrator.cleanup()
        
    @pytest.mark.asyncio
    async def test_fallback_mechanism(self):
        """Test fallback mechanism when primary engine fails."""
        orchestrator = SecureOrchestrator()
        await orchestrator.initialize()
        
        # Mock primary engine failure
        with patch.object(orchestrator, 'calculate_text_density') as mock_density:
            mock_density.return_value = {
                "text_density": 100,
                "has_text_layer": True
            }
            
            # Mock CPU engine failure
            with patch.object(orchestrator.cpu_engine, 'process_document') as mock_cpu:
                mock_cpu.side_effect = Exception("CPU engine failed")
                
                # Mock GPU engine success (fallback)
                with patch.object(orchestrator.gpu_engine, 'process_document') as mock_gpu:
                    mock_gpu.return_value = {
                        "success": True,
                        "text": "Fallback extracted text",
                        "confidence": 0.85,
                        "processing_time": 5.0,
                        "request_id": "test_fallback_123",
                        "engine": "gpu",
                        "metadata": {}
                    }
                    
                    result = await orchestrator.process_document(
                        file_path="test.pdf",
                        file_url="https://example.com/test.pdf"
                    )
                    
                    assert result.success is True
                    assert result.engine == "gpu"  # Fallback engine used
                    assert result.fallback_used is True
                    assert result.text == "Fallback extracted text"
                    
        await orchestrator.cleanup()

@pytest.mark.asyncio
async def test_performance_benchmark():
    """Performance benchmark for security features."""
    import time
    
    # Test encryption performance
    security_manager = SecurityManager(SecurityConfig(
        modal_api_key=TEST_MODAL_API_KEY,
        encryption_key=TEST_ENCRYPTION_KEY,
        enable_rate_limiting=False
    ))
    
    test_data = "x" * 1000  # 1KB of data
    
    start_time = time.time()
    for i in range(100):
        encrypted = security_manager.encrypt_sensitive_data(test_data)
        decrypted = security_manager.decrypt_sensitive_data(encrypted)
    encryption_time = time.time() - start_time
    
    # Test rate limiting performance
    monitoring_manager = MonitoringManager(SecurityConfig())
    
    start_time = time.time()
    for i in range(1000):
        monitoring_manager.record_request(True, 1.0, False)
    monitoring_time = time.time() - start_time
    
    print(f"\nPerformance Benchmark Results:")
    print(f"Encryption/Decryption (100 ops): {encryption_time:.3f}s")
    print(f"Monitoring recording (1000 ops): {monitoring_time:.3f}s")
    print(f"Encryption throughput: {100/encryption_time:.1f} ops/sec")
    print(f"Monitoring throughput: {1000/monitoring_time:.1f} ops/sec")

if __name__ == "__main__":
    # Run performance benchmark
    asyncio.run(test_performance_benchmark())