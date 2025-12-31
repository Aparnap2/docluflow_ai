"""Secure Apify entrypoint for DocuFlow Headless with enterprise-grade security, monitoring, and error handling."""

import asyncio
import os
import json
import sys
from typing import Dict, Any, Optional
from dotenv import load_dotenv
import structlog
from datetime import datetime

# Load environment variables
load_dotenv()

# Configure structured logging with security context
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

# Import secure components
from .engine.secure_orchestrator import get_orchestrator, cleanup_orchestrator
from .engine.security_monitoring import get_security_manager, get_monitoring_manager
from .config.security_config import get_security_config, validate_security_requirements
from .engine.intelligent_ingest import process_file_intelligently

class SecureDocuFlowActor:
    """Secure Apify Actor for DocuFlow Headless with enterprise-grade protections."""
    
    def __init__(self):
        self.security_manager = None
        self.monitoring_manager = None
        self.orchestrator = None
        self.security_config = None
        self._initialized = False
        
    async def initialize(self):
        """Initialize secure components."""
        if self._initialized:
            return
            
        try:
            # Load security configuration
            self.security_config = get_security_config()
            
            # Validate security requirements
            validation_result = validate_security_requirements()
            if not validation_result["config_valid"]:
                raise ValueError(f"Security validation failed: {validation_result['issues']}")
            
            # Initialize security and monitoring managers
            self.security_manager = get_security_manager(self.security_config)
            self.monitoring_manager = get_monitoring_manager(self.security_config)
            
            # Initialize secure orchestrator
            self.orchestrator = await get_orchestrator()
            
            self._initialized = True
            
            logger.info("Secure DocuFlow Actor initialized successfully",
                       environment=self.security_config.environment.value,
                       security_level=self.security_config.security_level.value,
                       validation_score=validation_result["security_score"])
            
        except Exception as e:
            logger.error("Failed to initialize secure actor", error=str(e))
            raise RuntimeError(f"Secure actor initialization failed: {str(e)}")
            
    async def cleanup(self):
        """Clean up secure components."""
        if self.orchestrator:
            await cleanup_orchestrator()
            
        logger.info("Secure DocuFlow Actor cleaned up")
        self._initialized = False
        
    def validate_environment(self):
        """Validate required environment variables with security checks."""
        required_vars = ["MODAL_API_KEY", "GROQ_API_KEY"]
        
        # Check for encrypted variables if encryption is enabled
        if self.security_config and self.security_config.enable_encryption:
            encrypted_vars = ["ENCRYPTION_KEY", "JWT_SECRET"]
            required_vars.extend(encrypted_vars)
            
        # Check for Redis if rate limiting is enabled
        if self.security_config and self.security_config.enable_rate_limiting:
            required_vars.append("REDIS_URL")
            
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {missing_vars}")
            
        logger.info("Environment validation passed with security checks",
                   encryption_enabled=self.security_config.enable_encryption if self.security_config else False,
                   rate_limiting_enabled=self.security_config.enable_rate_limiting if self.security_config else False)
        
    async def process_input_secure(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process v2 input with comprehensive security, monitoring, and error handling.
        
        Args:
            input_data: Input data containing files, schema, filter_keywords, etc.
            
        Returns:
            Secure processing result with full audit trail
        """
        start_time = datetime.utcnow()
        request_id = f"secure_{int(start_time.timestamp())}_{hash(str(input_data)) % 10000}"
        
        # Add security context to logs
        logger = structlog.get_logger(__name__).bind(
            request_id=request_id,
            security_level=self.security_config.security_level.value if self.security_config else "unknown"
        )
        
        try:
            # Initialize if not already done
            if not self._initialized:
                await self.initialize()
                
            # Validate environment
            self.validate_environment()
            
            # Validate v2 input with security checks
            if not input_data.get("files"):
                raise ValueError("files array is required")
            
            if not input_data.get("schema"):
                raise ValueError("schema is required")
                
            # Rate limiting check
            if self.security_config.enable_rate_limiting:
                allowed = await self.security_manager.check_rate_limit(
                    identifier=request_id,
                    tier=getattr(self.security_config, 'user_tier', 'basic')
                )
                if not allowed:
                    self.monitoring_manager.record_request(False, 0, True)
                    raise RateLimitError("Rate limit exceeded for this request")
                
            # Circuit breaker check
            if self.security_config.enable_circuit_breaker:
                if not self.security_manager.check_circuit_breaker():
                    self.monitoring_manager.record_request(False, 0, False)
                    raise CircuitBreakerError("Circuit breaker is open")
                
            files = input_data["files"]
            target_schema = input_data["schema"]
            filter_keywords = input_data.get("filter_keywords", [])
            use_gpu_ocr = input_data.get("use_gpu_ocr", False)
            confidence_threshold = input_data.get("confidence_threshold", 0.7)
            proxy_configuration = input_data.get("proxy_configuration", {"useApifyProxy": True})
            
            logger.info("Starting secure v2 extraction",
                       file_count=len(files),
                       schema_keys=list(target_schema.keys()) if isinstance(target_schema, dict) else [],
                       filter_keywords=filter_keywords,
                       use_gpu_ocr=use_gpu_ocr,
                       security_enabled=True)
            
            # Process each file with security monitoring
            results = []
            security_metadata = {
                "request_id": request_id,
                "security_level": self.security_config.security_level.value,
                "encryption_enabled": self.security_config.enable_encryption,
                "rate_limiting_enabled": self.security_config.enable_rate_limiting,
                "circuit_breaker_enabled": self.security_config.enable_circuit_breaker,
                "audit_trail": []
            }
            
            for i, file_info in enumerate(files):
                file_start_time = datetime.utcnow()
                file_request_id = f"{request_id}_file_{i}"
                
                try:
                    logger.info("Processing file with security",
                               file_index=i,
                               filename=file_info.get("filename", "unknown"))
                    
                    # Security audit entry
                    audit_entry = {
                        "timestamp": file_start_time.isoformat(),
                        "file_index": i,
                        "filename": file_info.get("filename", "unknown"),
                        "action": "processing_started",
                        "security_checks": []
                    }
                    
                    # Validate file info security
                    if not file_info.get("url") and not file_info.get("base64"):
                        raise ValueError(f"File {i} missing URL or base64 data")
                        
                    # Add security check
                    audit_entry["security_checks"].append("file_data_validation")
                    
                    # Intelligent ingestion with security
                    ingestion_result = await process_file_intelligently(file_info, filter_keywords)
                    audit_entry["security_checks"].append("ingestion_completed")
                    
                    if ingestion_result.get("skipped"):
                        logger.info("File skipped",
                                   filename=file_info.get("filename"),
                                   reason=ingestion_result.get("reason", "Unknown"))
                        results.append({
                            "file_index": i,
                            "filename": file_info.get("filename"),
                            "status": "skipped",
                            "skip_reason": ingestion_result.get("reason", "Filtered out"),
                            "extracted_data": None,
                            "security_metadata": audit_entry
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
                            "extracted_data": None,
                            "security_metadata": audit_entry
                        })
                        continue
                    
                    # Use secure orchestrator for extraction
                    file_path = ingestion_result.get("file_path")
                    file_url = ingestion_result.get("url")
                    
                    if not file_path or not file_url:
                        raise ValueError(f"Missing file path or URL for file {i}")
                        
                    # Process with secure orchestrator
                    secure_result = await self.orchestrator.process_document(
                        file_path=file_path,
                        file_url=file_url
                    )
                    
                    # Record success
                    self.security_manager.record_success()
                    self.monitoring_manager.record_request(True, secure_result.processing_time, False)
                    
                    # Add security metadata
                    secure_result.metadata["security"] = audit_entry
                    secure_result.metadata["request_id"] = file_request_id
                    
                    results.append({
                        "file_index": i,
                        "filename": file_info.get("filename"),
                        "status": "success" if secure_result.success else "failed",
                        "final_data": secure_result.text if secure_result.success else None,
                        "confidence": secure_result.confidence,
                        "processing_time": secure_result.processing_time,
                        "route": secure_result.engine,
                        "security_metadata": secure_result.metadata,
                        "routing_decision": secure_result.routing_decision.dict() if secure_result.routing_decision else None,
                        "fallback_used": secure_result.fallback_used
                    })
                    
                    audit_entry["action"] = "processing_completed"
                    audit_entry["engine_used"] = secure_result.engine
                    audit_entry["success"] = secure_result.success
                    
                except Exception as e:
                    logger.error("Secure file processing failed",
                               file_index=i,
                               filename=file_info.get("filename"),
                               error=str(e))
                    
                    # Record failure
                    self.security_manager.record_failure()
                    self.monitoring_manager.record_request(False, 0, False)
                    
                    results.append({
                        "file_index": i,
                        "filename": file_info.get("filename"),
                        "status": "failed",
                        "error": str(e),
                        "extracted_data": None,
                        "security_metadata": {
                            "timestamp": datetime.utcnow().isoformat(),
                            "file_index": i,
                            "filename": file_info.get("filename", "unknown"),
                            "action": "processing_failed",
                            "error": str(e)
                        }
                    })
            
            # Calculate overall processing time
            total_processing_time = (datetime.utcnow() - start_time).total_seconds()
            
            # Format secure result for Apify
            apify_result = self._format_secure_apify_result(results, input_data, {
                "request_id": request_id,
                "total_processing_time": total_processing_time,
                "security_metadata": security_metadata,
                "monitoring_metrics": self.monitoring_manager.get_metrics()
            })
            
            # Record overall success
            successful_count = sum(1 for r in results if r.get("status") == "success")
            self.monitoring_manager.record_request(successful_count > 0, total_processing_time, False)
            
            logger.info("Secure v2 extraction completed",
                       total_files=len(files),
                       successful_files=successful_count,
                       skipped_files=sum(1 for r in results if r.get("status") == "skipped"),
                       failed_files=sum(1 for r in results if r.get("status") == "failed"),
                       total_processing_time=total_processing_time,
                       request_id=request_id)
            
            return apify_result
            
        except Exception as e:
            logger.error("Secure v2 processing failed", 
                        error=str(e), 
                        error_type=type(e).__name__,
                        request_id=request_id)
            
            # Record failure
            if self.monitoring_manager:
                self.monitoring_manager.record_request(False, 0, False)
            
            return {
                "status": "failed",
                "error": str(e),
                "error_type": type(e).__name__,
                "data": None,
                "input": input_data,
                "security_metadata": {
                    "request_id": request_id,
                    "failed_at": datetime.utcnow().isoformat(),
                    "security_level": self.security_config.security_level.value if self.security_config else "unknown"
                }
            }

    def _format_secure_apify_result(self, results: list, input_data: Dict[str, Any], security_info: Dict[str, Any]) -> Dict[str, Any]:
        """Format secure extraction results for Apify output with full audit trail."""
        successful_results = [r for r in results if r.get("status") == "success"]
        failed_results = [r for r in results if r.get("status") == "failed"]
        skipped_results = [r for r in results if r.get("status") == "skipped"]
        
        # Security summary
        security_summary = {
            "request_id": security_info["request_id"],
            "security_level": security_info["security_metadata"]["security_level"],
            "encryption_enabled": security_info["security_metadata"]["encryption_enabled"],
            "rate_limiting_enabled": security_info["security_metadata"]["rate_limiting_enabled"],
            "circuit_breaker_enabled": security_info["security_metadata"]["circuit_breaker_enabled"],
            "audit_trail": security_info["security_metadata"]["audit_trail"],
            "monitoring_metrics": security_info["monitoring_metrics"]
        }
        
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
                    # Add security metadata
                    n8n_data["_security"] = {
                        "request_id": result.get("security_metadata", {}).get("request_id"),
                        "engine_used": result.get("route"),
                        "routing_decision": result.get("routing_decision"),
                        "fallback_used": result.get("fallback_used", False),
                        "processing_time": result.get("processing_time")
                    }
                    formatted_results.append(n8n_data)
                
                return {
                    "status": "success",
                    "data": formatted_results,
                    "security_summary": security_summary,
                    "metadata": {
                        "total_files": len(results),
                        "successful": len(successful_results),
                        "failed": len(failed_results),
                        "skipped": len(skipped_results),
                        "output_format": "n8n_compatible",
                        "total_processing_time": security_info["total_processing_time"],
                        "timestamp": datetime.utcnow().isoformat()
                    },
                    "input": {
                        "files": input_data.get("files", []),
                        "schema": input_data.get("schema", {}),
                        "filter_keywords": input_data.get("filter_keywords", [])
                    }
                }
            else:
                # Standard JSON output with security metadata
                return {
                    "status": "success",
                    "data": [r.get("final_data", {}) for r in successful_results],
                    "security_summary": security_summary,
                    "metadata": {
                        "total_files": len(results),
                        "successful": len(successful_results),
                        "failed": len(failed_results),
                        "skipped": len(skipped_results),
                        "total_processing_time": security_info["total_processing_time"],
                        "timestamp": datetime.utcnow().isoformat()
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
                "security_summary": security_summary,
                "metadata": {
                    "total_files": len(results),
                    "successful": 0,
                    "failed": len(failed_results),
                    "skipped": len(skipped_results),
                    "total_processing_time": security_info["total_processing_time"],
                    "timestamp": datetime.utcnow().isoformat()
                },
                "input": {
                    "files": input_data.get("files", []),
                    "schema": input_data.get("schema", {}),
                    "filter_keywords": input_data.get("filter_keywords", [])
                }
            }

    async def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check with security status."""
        try:
            if not self._initialized:
                await self.initialize()
                
            # Check orchestrator health
            orchestrator_health = await self.orchestrator.health_check()
            
            # Get monitoring metrics
            monitoring_metrics = self.monitoring_manager.get_health_status()
            
            # Security status
            security_status = {
                "initialized": self._initialized,
                "security_level": self.security_config.security_level.value,
                "encryption_enabled": self.security_config.enable_encryption,
                "rate_limiting_enabled": self.security_config.enable_rate_limiting,
                "circuit_breaker_enabled": self.security_config.enable_circuit_breaker,
                "audit_logging_enabled": self.security_config.enable_audit_logging
            }
            
            # Overall health
            components = [
                orchestrator_health.get("status") == "healthy",
                monitoring_metrics.get("status") == "healthy",
                security_status["initialized"]
            ]
            
            overall_health = "healthy" if all(components) else "degraded" if any(components) else "unhealthy"
            
            return {
                "status": overall_health,
                "timestamp": datetime.utcnow().isoformat(),
                "security": security_status,
                "orchestrator": orchestrator_health,
                "monitoring": monitoring_metrics,
                "uptime": "N/A"  # Could implement uptime tracking
            }
            
        except Exception as e:
            logger.error("Health check failed", error=str(e))
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }

async def main():
    """Main entrypoint for the secure Apify Actor."""
    actor = None
    try:
        logger.info("Starting Secure DocuFlow Headless Actor")
        
        # Initialize secure actor
        actor = SecureDocuFlowActor()
        await actor.initialize()
        
        # Example secure input for testing
        secure_test_input = {
            "files": [
                {
                    "url": "https://example.com/document.pdf",
                    "filename": "test_document.pdf"
                }
            ],
            "schema": {
                "title": "string",
                "author": "string", 
                "date": "string",
                "summary": "string"
            },
            "filter_keywords": ["invoice", "receipt"],
            "output_format": "n8n_compatible",
            "confidence_threshold": 0.8
        }
        
        # Check if we're running in Apify environment
        if os.getenv("APIFY_ACTOR_RUN_ID"):
            logger.info("Running in Apify environment with security enabled")
            input_data = secure_test_input  # In real Apify, this comes from the platform
        else:
            logger.info("Running in secure development mode")
            input_data = secure_test_input
        
        # Perform health check first
        health_status = await actor.health_check()
        logger.info("System health check completed", health_status=health_status["status"])
        
        if health_status["status"] != "healthy":
            logger.warning("System health is degraded", health_status=health_status)
        
        # Process input securely
        result = await actor.process_input_secure(input_data)
        
        # Output secure result
        print(json.dumps(result, indent=2, default=str))
        
        # Return result for Apify
        return result
        
    except Exception as e:
        logger.error("Secure actor failed", error=str(e), error_type=type(e).__name__)
        
        error_result = {
            "status": "failed",
            "error": str(e),
            "error_type": type(e).__name__,
            "data": None,
            "security_metadata": {
                "failed_at": datetime.utcnow().isoformat(),
                "security_level": "unknown"
            }
        }
        
        print(json.dumps(error_result, indent=2))
        return error_result
        
    finally:
        # Clean up resources
        if actor:
            await actor.cleanup()

if __name__ == "__main__":
    # Run the secure actor
    result = asyncio.run(main())
    
    # Exit with appropriate code
    if result.get("status") == "success":
        sys.exit(0)
    else:
        sys.exit(1)