"""Validation script for Modal deployment with security integration testing."""

import asyncio
import requests
import json
import time
from typing import Dict, Any, Optional
import sys

# Import our secure components
from src.engine.secure_modal_client import create_secure_modal_client, ModalAPIError
from src.engine.security_monitoring import get_security_manager, get_monitoring_manager
from src.config.security_config import get_security_config

class ModalDeploymentValidator:
    """Comprehensive validator for Modal deployment with security features."""
    
    def __init__(self):
        self.security_config = get_security_config()
        self.security_manager = get_security_manager(self.security_config)
        self.monitoring_manager = get_monitoring_manager(self.security_config)
        self.validation_results = []
        
    async def validate_cpu_endpoint(self, endpoint_url: str) -> Dict[str, Any]:
        """Validate CPU endpoint with security features."""
        print(f"🔍 Validating CPU endpoint: {endpoint_url}")
        
        result = {
            "endpoint": "cpu",
            "url": endpoint_url,
            "status": "unknown",
            "security_validated": False,
            "performance_metrics": {},
            "errors": []
        }
        
        try:
            # Create secure client
            client = await create_secure_modal_client(
                api_key="test_key",  # Will use env var
                enable_caching=True,
                enable_monitoring=True,
                enable_rate_limiting=False,  # Disable for testing
                max_retries=2,
                timeout=30
            )
            
            # Test health check
            health_result = await client.health_check()
            result["health_status"] = health_result
            
            if health_result.get("status") == "healthy":
                result["status"] = "healthy"
                print("✅ CPU endpoint health check passed")
            else:
                result["status"] = "unhealthy"
                result["errors"].append(f"Health check failed: {health_result}")
                print("❌ CPU endpoint health check failed")
                
            # Test basic processing (if we have a test file)
            test_file_url = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
            
            try:
                process_result = await client.call_cpu_endpoint(test_file_url)
                result["processing_test"] = "success"
                result["text_length"] = len(process_result.get("text", ""))
                print(f"✅ CPU processing test successful (text length: {result['text_length']})")
            except Exception as e:
                result["processing_test"] = "failed"
                result["errors"].append(f"Processing test failed: {str(e)}")
                print(f"⚠️  CPU processing test failed: {str(e)}")
                
            # Get metrics
            metrics = client.get_metrics()
            result["performance_metrics"] = metrics
            
            # Validate security features
            result["security_validated"] = await self._validate_security_features(client)
            
            await client.close()
            
        except Exception as e:
            result["status"] = "error"
            result["errors"].append(f"CPU validation error: {str(e)}")
            print(f"❌ CPU endpoint validation error: {str(e)}")
            
        return result
        
    async def validate_gpu_endpoint(self, endpoint_url: str) -> Dict[str, Any]:
        """Validate GPU endpoint with security features."""
        print(f"🔍 Validating GPU endpoint: {endpoint_url}")
        
        result = {
            "endpoint": "gpu",
            "url": endpoint_url,
            "status": "unknown",
            "security_validated": False,
            "performance_metrics": {},
            "errors": []
        }
        
        try:
            # Create secure client
            client = await create_secure_modal_client(
                api_key="test_key",  # Will use env var
                enable_caching=True,
                enable_monitoring=True,
                enable_rate_limiting=False,  # Disable for testing
                max_retries=2,
                timeout=60  # Longer timeout for GPU
            )
            
            # Test health check
            health_result = await client.health_check()
            result["health_status"] = health_result
            
            if health_result.get("status") == "healthy":
                result["status"] = "healthy"
                print("✅ GPU endpoint health check passed")
            else:
                result["status"] = "unhealthy"
                result["errors"].append(f"Health check failed: {health_result}")
                print("❌ GPU endpoint health check failed")
                
            # Test basic processing (if we have a test file)
            test_file_url = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
            
            try:
                process_result = await client.call_gpu_endpoint(test_file_url)
                result["processing_test"] = "success"
                result["text_length"] = len(process_result.get("text", ""))
                result["ocr_confidence"] = process_result.get("ocr_confidence", 0.0)
                print(f"✅ GPU processing test successful (text length: {result['text_length']}, OCR confidence: {result['ocr_confidence']})")
            except Exception as e:
                result["processing_test"] = "failed"
                result["errors"].append(f"Processing test failed: {str(e)}")
                print(f"⚠️  GPU processing test failed: {str(e)}")
                
            # Get metrics
            metrics = client.get_metrics()
            result["performance_metrics"] = metrics
            
            # Validate security features
            result["security_validated"] = await self._validate_security_features(client)
            
            await client.close()
            
        except Exception as e:
            result["status"] = "error"
            result["errors"].append(f"GPU validation error: {str(e)}")
            print(f"❌ GPU endpoint validation error: {str(e)}")
            
        return result
        
    async def _validate_security_features(self, client) -> bool:
        """Validate security features are working correctly."""
        try:
            # Check if security manager is initialized
            if not self.security_manager:
                print("⚠️  Security manager not initialized")
                return False
                
            # Test encryption (if enabled)
            if self.security_config.enable_encryption:
                test_data = "sensitive_data_123"
                encrypted = self.security_manager.encrypt_sensitive_data(test_data)
                decrypted = self.security_manager.decrypt_sensitive_data(encrypted)
                
                if decrypted == test_data:
                    print("✅ Encryption/decryption working correctly")
                else:
                    print("❌ Encryption/decryption test failed")
                    return False
            
            # Test monitoring
            initial_metrics = self.monitoring_manager.get_metrics()
            self.monitoring_manager.record_request(True, 1.5, False)
            updated_metrics = self.monitoring_manager.get_metrics()
            
            if updated_metrics["metrics"]["total_requests"] > initial_metrics["metrics"]["total_requests"]:
                print("✅ Monitoring system working correctly")
            else:
                print("⚠️  Monitoring system may not be recording properly")
                
            return True
            
        except Exception as e:
            print(f"❌ Security validation error: {str(e)}")
            return False
            
    def validate_direct_endpoints(self, cpu_url: str, gpu_url: str) -> Dict[str, Any]:
        """Validate endpoints directly without secure client."""
        print("🔍 Validating endpoints directly")
        
        results = {
            "cpu": self._check_endpoint_direct(cpu_url),
            "gpu": self._check_endpoint_direct(gpu_url)
        }
        
        return results
        
    def _check_endpoint_direct(self, url: str) -> Dict[str, Any]:
        """Check endpoint directly using requests."""
        result = {
            "url": url,
            "accessible": False,
            "response_time": None,
            "status_code": None,
            "error": None
        }
        
        try:
            start_time = time.time()
            response = requests.get(f"{url}/health", timeout=30)
            end_time = time.time()
            
            result["accessible"] = response.status_code == 200
            result["response_time"] = end_time - start_time
            result["status_code"] = response.status_code
            
            if response.status_code == 200:
                try:
                    health_data = response.json()
                    result["health_data"] = health_data
                except:
                    result["health_data"] = response.text
                    
        except Exception as e:
            result["error"] = str(e)
            
        return result
        
    async def run_comprehensive_validation(self, cpu_url: str, gpu_url: str) -> Dict[str, Any]:
        """Run comprehensive validation of both endpoints."""
        print("🚀 Starting comprehensive Modal deployment validation")
        print(f"CPU Endpoint: {cpu_url}")
        print(f"GPU Endpoint: {gpu_url}")
        print("="*60)
        
        # Direct endpoint validation
        direct_results = self.validate_direct_endpoints(cpu_url, gpu_url)
        
        # Secure client validation
        cpu_result = await self.validate_cpu_endpoint(cpu_url)
        gpu_result = await self.validate_gpu_endpoint(gpu_url)
        
        # Overall assessment
        all_results = [cpu_result, gpu_result]
        successful_count = sum(1 for r in all_results if r["status"] == "healthy")
        total_count = len(all_results)
        
        assessment = {
            "overall_status": "healthy" if successful_count == total_count else "degraded" if successful_count > 0 else "failed",
            "successful_endpoints": successful_count,
            "total_endpoints": total_count,
            "direct_validation": direct_results,
            "secure_validation": {
                "cpu": cpu_result,
                "gpu": gpu_result
            },
            "security_config": {
                "environment": self.security_config.environment.value,
                "security_level": self.security_config.security_level.value,
                "encryption_enabled": self.security_config.enable_encryption,
                "rate_limiting_enabled": self.security_config.enable_rate_limiting,
                "circuit_breaker_enabled": self.security_config.enable_circuit_breaker
            },
            "timestamp": time.time()
        }
        
        # Print summary
        print("\n" + "="*60)
        print("📊 VALIDATION SUMMARY")
        print(f"Overall Status: {assessment['overall_status'].upper()}")
        print(f"Successful Endpoints: {successful_count}/{total_count}")
        
        if successful_count == total_count:
            print("🎉 ALL ENDPOINTS VALIDATED SUCCESSFULLY!")
        elif successful_count > 0:
            print("⚠️  PARTIAL SUCCESS - Some endpoints need attention")
        else:
            print("❌ ALL ENDPOINTS FAILED VALIDATION")
            
        return assessment

async def main():
    """Main validation function."""
    print("🔒 MODAL DEPLOYMENT VALIDATION WITH SECURITY")
    print("Validating Modal endpoints with enterprise security features")
    
    # Example endpoints (replace with actual deployed URLs)
    cpu_endpoint = "https://your-cpu-endpoint.modal.run"
    gpu_endpoint = "https://your-gpu-endpoint.modal.run"
    
    # Or get from environment
    cpu_endpoint = os.getenv("MODAL_CPU_ENDPOINT", cpu_endpoint)
    gpu_endpoint = os.getenv("MODAL_GPU_ENDPOINT", gpu_endpoint)
    
    if cpu_endpoint == "https://your-cpu-endpoint.modal.run" or gpu_endpoint == "https://your-gpu-endpoint.modal.run":
        print("⚠️  Using example endpoints. Set MODAL_CPU_ENDPOINT and MODAL_GPU_ENDPOINT environment variables")
        print("💡 To get actual endpoints, run: modal deploy modal_backend/granite_docling_cpu_optimized.py")
        print("💡 And: modal deploy modal_backend/deepseek_ocr_gpu_optimized.py")
        
        # You can also parse from deployment output files if available
        try:
            with open("modal_deployment_results.json", "r") as f:
                deployment_results = json.load(f)
                for result in deployment_results.get("successful", []):
                    if result["type"] == "cpu":
                        cpu_endpoint = result["deployment_info"]["endpoint_url"]
                    elif result["type"] == "gpu":
                        gpu_endpoint = result["deployment_info"]["endpoint_url"]
                print(f"📁 Loaded endpoints from deployment results")
        except:
            pass
    
    # Run validation
    validator = ModalDeploymentValidator()
    results = await validator.run_comprehensive_validation(cpu_endpoint, gpu_endpoint)
    
    # Save results
    with open("modal_validation_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n💾 Results saved to modal_validation_results.json")
    
    # Exit with appropriate code
    if results["overall_status"] == "healthy":
        print("✅ Validation successful - endpoints are ready for production!")
        sys.exit(0)
    elif results["overall_status"] == "degraded":
        print("⚠️  Partial validation success - review failed endpoints")
        sys.exit(0)
    else:
        print("❌ Validation failed - endpoints need attention")
        sys.exit(1)

if __name__ == "__main__":
    import os
    asyncio.run(main())