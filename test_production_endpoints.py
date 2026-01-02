#!/usr/bin/env python3
"""
Production testing script for DocuFlow Headless v2 with deployed Modal endpoints.
Tests both Granite-Docling CPU and DeepSeek-OCR GPU endpoints with real files.
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
import aiohttp
import base64
import requests
from PIL import Image
import io
from datetime import datetime
import structlog

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
        structlog.dev.ConsoleRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

# Modal endpoint URLs
GRANITE_CPU_URL = "https://ap3617180--granite-docling-cpu-final-serve.modal.run"
DEEPSEEK_GPU_URL = "https://ap3617180--deepseek-ocr-gpu-final-serve.modal.run"

# Test files directory
TEST_FILES_DIR = Path("test_files")
TEST_FILES_DIR.mkdir(exist_ok=True)

class ProductionEndpointTester:
    """Comprehensive tester for production Modal endpoints."""
    
    def __init__(self):
        self.session = None
        self.test_results = []
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def create_test_pdf(self) -> bytes:
        """Create a simple test PDF with text content."""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.warning("PyMuPDF not available, creating base64 PDF")
            # Simple PDF content as base64
            pdf_content = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
/Resources <<
/Font <<
/F1 5 0 R
>>
>>
>>
endobj
4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
100 700 Td
(Test Invoice for DocuFlow) Tj
ET
endstream
endobj
5 0 obj
<<
/Type /Font
/Subtype /Type1
/BaseFont /Helvetica
>>
endobj
xref
0 6
0000000000 65535 f 
0000000010 00000 n 
0000000053 00000 n 
0000000100 00000 n 
0000000200 00000 n 
0000000300 00000 n 
trailer
<<
/Size 6
/Root 1 0 R
>>
startxref
400
%%EOF"""
            return pdf_content
        
        # Create PDF with PyMuPDF
        doc = fitz.open()
        page = doc.new_page()
        
        # Add test content
        text_content = """INVOICE
Date: 2024-01-15
Invoice Number: INV-2024-001
Vendor: TechCorp Solutions
Amount: $1,250.00

This is a test invoice for DocuFlow Headless v2 production testing.
The system should extract vendor information, dates, and amounts.

Payment Terms: Net 30
Due Date: 2024-02-14"""
        
        page.insert_text((50, 100), text_content, fontsize=12)
        pdf_bytes = doc.tobytes()
        doc.close()
        
        return pdf_bytes
    
    def create_test_image(self) -> bytes:
        """Create a test image with text content."""
        # Create a simple test image
        img = Image.new('RGB', (800, 600), color='white')
        
        # This would normally add text, but for now just return a simple image
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        return img_buffer.getvalue()
    
    async def test_health_check(self, endpoint_url: str, endpoint_name: str) -> bool:
        """Test health check endpoint."""
        try:
            logger.info(f"Testing health check for {endpoint_name}", url=endpoint_url)
            
            async with self.session.get(f"{endpoint_url}/health", timeout=30) as response:
                if response.status == 200:
                    health_data = await response.json()
                    logger.info(f"Health check passed for {endpoint_name}", health=health_data)
                    return True
                else:
                    logger.error(f"Health check failed for {endpoint_name}", status=response.status)
                    return False
                    
        except Exception as e:
            logger.error(f"Health check error for {endpoint_name}", error=str(e))
            return False
    
    async def test_granite_cpu_endpoint(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """Test Granite-Docling CPU endpoint."""
        try:
            logger.info("Testing Granite-Docling CPU endpoint", filename=filename)
            
            # Prepare request payload
            files = {
                "file": (filename, file_content, "application/pdf" if filename.endswith(".pdf") else "image/png")
            }
            
            data = {
                "model": "llm",
                "messages": [
                    {
                        "role": "user",
                        "content": "Extract text and layout information from this document"
                    }
                ],
                "stream": False
            }
            
            start_time = time.time()
            
            async with self.session.post(
                f"{GRANITE_CPU_URL}/v1/chat/completions",
                data=data,
                files=files,
                timeout=120
            ) as response:
                elapsed_time = time.time() - start_time
                
                if response.status == 200:
                    result = await response.json()
                    logger.info(
                        "Granite-Docling CPU test successful",
                        response_time=elapsed_time,
                        status=response.status
                    )
                    return {
                        "success": True,
                        "endpoint": "granite_cpu",
                        "response_time": elapsed_time,
                        "result": result,
                        "status_code": response.status
                    }
                else:
                    error_text = await response.text()
                    logger.error(
                        "Granite-Docling CPU test failed",
                        status=response.status,
                        error=error_text
                    )
                    return {
                        "success": False,
                        "endpoint": "granite_cpu",
                        "status_code": response.status,
                        "error": error_text
                    }
                    
        except Exception as e:
            logger.error("Granite-Docling CPU test error", error=str(e))
            return {
                "success": False,
                "endpoint": "granite_cpu",
                "error": str(e)
            }
    
    async def test_deepseek_gpu_endpoint(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """Test DeepSeek-OCR GPU endpoint."""
        try:
            logger.info("Testing DeepSeek-OCR GPU endpoint", filename=filename)
            
            # Prepare request payload
            files = {
                "file": (filename, file_content, "application/pdf" if filename.endswith(".pdf") else "image/png")
            }
            
            data = {
                "model": "llm",
                "messages": [
                    {
                        "role": "user",
                        "content": "Perform OCR on this document and extract all text"
                    }
                ],
                "stream": False
            }
            
            start_time = time.time()
            
            async with self.session.post(
                f"{DEEPSEEK_GPU_URL}/v1/chat/completions",
                data=data,
                files=files,
                timeout=120
            ) as response:
                elapsed_time = time.time() - start_time
                
                if response.status == 200:
                    result = await response.json()
                    logger.info(
                        "DeepSeek-OCR GPU test successful",
                        response_time=elapsed_time,
                        status=response.status
                    )
                    return {
                        "success": True,
                        "endpoint": "deepseek_gpu",
                        "response_time": elapsed_time,
                        "result": result,
                        "status_code": response.status
                    }
                else:
                    error_text = await response.text()
                    logger.error(
                        "DeepSeek-OCR GPU test failed",
                        status=response.status,
                        error=error_text
                    )
                    return {
                        "success": False,
                        "endpoint": "deepseek_gpu",
                        "status_code": response.status,
                        "error": error_text
                    }
                    
        except Exception as e:
            logger.error("DeepSeek-OCR GPU test error", error=str(e))
            return {
                "success": False,
                "endpoint": "deepseek_gpu",
                "error": str(e)
            }
    
    async def test_universal_openai_sdk(self) -> Dict[str, Any]:
        """Test Universal OpenAI SDK integration."""
        try:
            logger.info("Testing Universal OpenAI SDK integration")
            
            # Import the SDK from our codebase
            sys.path.insert(0, str(Path(__file__).parent / "src"))
            from engine.universal_llm import UniversalOpenAIClient
            
            client = UniversalOpenAIClient()
            
            # Test with both endpoints
            test_results = []
            
            # Test CPU endpoint
            try:
                cpu_result = await client.call_model(
                    model="granite-docling",
                    messages=[{"role": "user", "content": "Test CPU endpoint"}],
                    max_tokens=100
                )
                test_results.append({
                    "endpoint": "cpu",
                    "success": True,
                    "result": cpu_result
                })
            except Exception as e:
                test_results.append({
                    "endpoint": "cpu",
                    "success": False,
                    "error": str(e)
                })
            
            # Test GPU endpoint
            try:
                gpu_result = await client.call_model(
                    model="deepseek-ocr",
                    messages=[{"role": "user", "content": "Test GPU endpoint"}],
                    max_tokens=100
                )
                test_results.append({
                    "endpoint": "gpu",
                    "success": True,
                    "result": gpu_result
                })
            except Exception as e:
                test_results.append({
                    "endpoint": "gpu",
                    "success": False,
                    "error": str(e)
                })
            
            return {
                "success": all(result["success"] for result in test_results),
                "results": test_results
            }
            
        except Exception as e:
            logger.error("Universal OpenAI SDK test error", error=str(e))
            return {
                "success": False,
                "error": str(e)
            }
    
    async def run_comprehensive_tests(self) -> Dict[str, Any]:
        """Run comprehensive production tests."""
        logger.info("Starting comprehensive production endpoint testing")
        
        test_results = {
            "timestamp": datetime.now().isoformat(),
            "tests": []
        }
        
        # Test 1: Health checks
        logger.info("=== Test 1: Health Checks ===")
        cpu_health = await self.test_health_check(GRANITE_CPU_URL, "Granite-Docling CPU")
        gpu_health = await self.test_health_check(DEEPSEEK_GPU_URL, "DeepSeek-OCR GPU")
        
        test_results["tests"].append({
            "test": "health_checks",
            "cpu_health": cpu_health,
            "gpu_health": gpu_health,
            "overall_health": cpu_health and gpu_health
        })
        
        # Test 2: Create test files
        logger.info("=== Test 2: Creating Test Files ===")
        try:
            test_pdf = self.create_test_pdf()
            test_image = self.create_test_image()
            
            # Save test files for reference
            pdf_path = TEST_FILES_DIR / "test_invoice.pdf"
            image_path = TEST_FILES_DIR / "test_image.png"
            
            with open(pdf_path, "wb") as f:
                f.write(test_pdf)
            
            with open(image_path, "wb") as f:
                f.write(test_image)
            
            logger.info("Test files created successfully", pdf_size=len(test_pdf), image_size=len(test_image))
            
        except Exception as e:
            logger.error("Failed to create test files", error=str(e))
            test_results["tests"].append({
                "test": "file_creation",
                "success": False,
                "error": str(e)
            })
            return test_results
        
        # Test 3: Endpoint functionality
        logger.info("=== Test 3: Endpoint Functionality ===")
        
        # Test CPU endpoint with PDF
        cpu_pdf_result = await self.test_granite_cpu_endpoint(test_pdf, "test_invoice.pdf")
        test_results["tests"].append({
            "test": "cpu_pdf_extraction",
            "result": cpu_pdf_result
        })
        
        # Test GPU endpoint with image
        gpu_image_result = await self.test_deepseek_gpu_endpoint(test_image, "test_image.png")
        test_results["tests"].append({
            "test": "gpu_image_ocr",
            "result": gpu_image_result
        })
        
        # Test 4: Universal OpenAI SDK
        logger.info("=== Test 4: Universal OpenAI SDK ===")
        sdk_result = await self.test_universal_openai_sdk()
        test_results["tests"].append({
            "test": "universal_sdk",
            "result": sdk_result
        })
        
        # Calculate overall success
        successful_tests = sum(
            1 for test in test_results["tests"] 
            if test.get("result", {}).get("success", False) or 
               test.get("overall_health", False) or
               test.get("success", False)
        )
        total_tests = len(test_results["tests"])
        
        test_results["summary"] = {
            "total_tests": total_tests,
            "successful_tests": successful_tests,
            "success_rate": successful_tests / total_tests if total_tests > 0 else 0,
            "overall_success": successful_tests == total_tests
        }
        
        logger.info(
            "Production testing completed",
            total_tests=total_tests,
            successful_tests=successful_tests,
            success_rate=test_results["summary"]["success_rate"]
        )
        
        return test_results

async def main():
    """Main testing function."""
    logger.info("=== DocuFlow Headless v2 Production Testing Started ===")
    
    async with ProductionEndpointTester() as tester:
        results = await tester.run_comprehensive_tests()
        
        # Save results to file
        results_file = Path("test_results_production.json")
        with open(results_file, "w") as f:
            json.dump(results, f, indent=2, default=str)
        
        logger.info("Test results saved", file=str(results_file))
        
        # Print summary
        print("\n" + "="*60)
        print("PRODUCTION TESTING SUMMARY")
        print("="*60)
        print(f"Overall Success: {'✅ PASSED' if results['summary']['overall_success'] else '❌ FAILED'}")
        print(f"Success Rate: {results['summary']['success_rate']:.1%}")
        print(f"Total Tests: {results['summary']['total_tests']}")
        print(f"Successful Tests: {results['summary']['successful_tests']}")
        print("="*60)
        
        return results['summary']['overall_success']

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)