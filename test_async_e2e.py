#!/usr/bin/env python3
"""Comprehensive async E2E test for DocuFlow Headless - handles long-running operations properly."""

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Dict, Any, List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from graph import run_extraction
import structlog

# Configure structured logging
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

class AsyncE2ETester:
    """Comprehensive async E2E tester for DocuFlow Headless."""
    
    def __init__(self):
        self.test_results = []
        self.start_time = None
    
    async def run_single_test(self, name: str, url: str, schema: Dict[str, Any], 
                            use_gpu_ocr: bool = False, confidence_threshold: float = 0.5,
                            timeout: int = 300) -> Dict[str, Any]:
        """Run a single test with proper timeout handling."""
        test_start = time.time()
        
        try:
            logger.info(f"Starting test: {name}", url=url, schema_keys=list(schema.keys()))
            
            # Run extraction with timeout
            result = await asyncio.wait_for(
                run_extraction(
                    source_url=url,
                    target_schema=schema,
                    use_gpu_ocr=use_gpu_ocr,
                    confidence_threshold=confidence_threshold,
                    dev_mode=True
                ),
                timeout=timeout
            )
            
            test_duration = time.time() - test_start
            
            # Analyze result
            success = result.get("status") == "success" and result.get("final_data") is not None
            has_data = bool(result.get("final_data"))
            errors = result.get("errors", [])
            warnings = result.get("warnings", [])
            
            test_result = {
                "name": name,
                "url": url,
                "success": success,
                "has_data": has_data,
                "status": result.get("status"),
                "errors": errors,
                "warnings": warnings,
                "duration": test_duration,
                "gpu_ocr_used": result.get("gpu_ocr_used", False),
                "extraction_confidence": result.get("extraction_confidence", 0.0),
                "validation_passed": result.get("validation_passed", False),
                "data_keys": list(result.get("final_data", {}).keys()) if has_data else []
            }
            
            logger.info(f"Test completed: {name}", 
                       success=success,
                       duration=test_duration,
                       has_data=has_data,
                       status=result.get("status"))
            
            return test_result
            
        except asyncio.TimeoutError:
            logger.error(f"Test timed out: {name}", url=url, timeout=timeout)
            return {
                "name": name,
                "url": url,
                "success": False,
                "has_data": False,
                "status": "timeout",
                "errors": [f"Test timed out after {timeout} seconds"],
                "warnings": [],
                "duration": timeout,
                "gpu_ocr_used": False,
                "extraction_confidence": 0.0,
                "validation_passed": False,
                "data_keys": []
            }
            
        except Exception as e:
            test_duration = time.time() - test_start
            logger.error(f"Test failed with exception: {name}", 
                        url=url, 
                        error=str(e),
                        error_type=type(e).__name__)
            
            return {
                "name": name,
                "url": url,
                "success": False,
                "has_data": False,
                "status": "error",
                "errors": [f"Exception: {str(e)}"],
                "warnings": [],
                "duration": test_duration,
                "gpu_ocr_used": False,
                "extraction_confidence": 0.0,
                "validation_passed": False,
                "data_keys": []
            }
    
    async def run_all_tests(self) -> List[Dict[str, Any]]:
        """Run all E2E tests with proper async handling."""
        self.start_time = time.time()
        
        # Define test cases
        test_cases = [
            {
                "name": "Web Page Extraction",
                "url": "https://httpbin.org/html",
                "schema": {
                    "title": "string",
                    "h1_text": "string",
                    "paragraphs": "string"
                },
                "use_gpu_ocr": False,
                "confidence_threshold": 0.5
            },
            {
                "name": "Error Handling - Private URL",
                "url": "http://httpstat.us/403",
                "schema": {"test": "string"},
                "use_gpu_ocr": False,
                "confidence_threshold": 0.7,
                "expected_failure": True
            },
            {
                "name": "Document Processing - PDF",
                "url": "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf",
                "schema": {
                    "title": "string",
                    "content_type": "string"
                },
                "use_gpu_ocr": True,
                "confidence_threshold": 0.6
            },
            {
                "name": "Large Document Test",
                "url": "https://www.w3.org/TR/2021/REC-html52-20211221/",
                "schema": {
                    "title": "string",
                    "sections": "string",
                    "specification_version": "string"
                },
                "use_gpu_ocr": False,
                "confidence_threshold": 0.5,
                "timeout": 600  # Longer timeout for large documents
            }
        ]
        
        logger.info("Starting comprehensive E2E tests", test_count=len(test_cases))
        
        # Run tests sequentially to avoid overwhelming the system
        results = []
        for i, test_case in enumerate(test_cases, 1):
            logger.info(f"Running test {i}/{len(test_cases)}: {test_case['name']}")
            
            result = await self.run_single_test(
                name=test_case["name"],
                url=test_case["url"],
                schema=test_case["schema"],
                use_gpu_ocr=test_case.get("use_gpu_ocr", False),
                confidence_threshold=test_case.get("confidence_threshold", 0.5),
                timeout=test_case.get("timeout", 300)
            )
            
            results.append(result)
            
            # Add small delay between tests to avoid rate limiting
            if i < len(test_cases):
                logger.info(f"Waiting before next test...")
                await asyncio.sleep(2)
        
        total_duration = time.time() - self.start_time
        logger.info("All tests completed", 
                   total_duration=total_duration,
                   test_count=len(results))
        
        return results
    
    def generate_report(self, results: List[Dict[str, Any]]) -> str:
        """Generate a comprehensive test report."""
        total_tests = len(results)
        successful_tests = sum(1 for r in results if r["success"])
        failed_tests = total_tests - successful_tests
        total_duration = sum(r["duration"] for r in results)
        
        report = []
        report.append("=" * 80)
        report.append("🧪 DOCUFLOW HEADLESS - COMPREHENSIVE E2E TEST REPORT")
        report.append("=" * 80)
        report.append(f"Total Tests: {total_tests}")
        report.append(f"Successful: {successful_tests}")
        report.append(f"Failed: {failed_tests}")
        report.append(f"Success Rate: {(successful_tests/total_tests)*100:.1f}%")
        report.append(f"Total Duration: {total_duration:.1f}s")
        report.append("")
        
        # Individual test results
        report.append("📊 INDIVIDUAL TEST RESULTS:")
        report.append("-" * 80)
        
        for result in results:
            status_icon = "✅" if result["success"] else "❌"
            data_icon = "📄" if result["has_data"] else "📭"
            
            report.append(f"{status_icon} {result['name']}")
            report.append(f"   URL: {result['url']}")
            report.append(f"   Status: {result['status']}")
            report.append(f"   Duration: {result['duration']:.1f}s")
            report.append(f"   Has Data: {result['has_data']} {data_icon}")
            report.append(f"   GPU OCR Used: {result['gpu_ocr_used']}")
            report.append(f"   Confidence: {result['extraction_confidence']:.2f}")
            report.append(f"   Validation: {'✅' if result['validation_passed'] else '❌'}")
            
            if result["data_keys"]:
                report.append(f"   Data Keys: {', '.join(result['data_keys'])}")
            
            if result["errors"]:
                report.append(f"   Errors: {len(result['errors'])}")
                for error in result["errors"][:3]:  # Show first 3 errors
                    report.append(f"     - {error}")
                if len(result["errors"]) > 3:
                    report.append(f"     ... and {len(result['errors']) - 3} more")
            
            if result["warnings"]:
                report.append(f"   Warnings: {len(result['warnings'])}")
                for warning in result["warnings"][:3]:
                    report.append(f"     - {warning}")
            
            report.append("")
        
        # Summary by status
        status_summary = {}
        for result in results:
            status = result["status"]
            status_summary[status] = status_summary.get(status, 0) + 1
        
        report.append("📈 STATUS SUMMARY:")
        report.append("-" * 40)
        for status, count in status_summary.items():
            report.append(f"   {status}: {count}")
        
        report.append("")
        report.append("=" * 80)
        
        return "\n".join(report)

async def main():
    """Run comprehensive async E2E tests."""
    print("🚀 Starting Comprehensive Async E2E Tests")
    print("=" * 80)
    
    tester = AsyncE2ETester()
    
    try:
        # Run all tests
        results = await tester.run_all_tests()
        
        # Generate and display report
        report = tester.generate_report(results)
        print(report)
        
        # Save report to file
        report_file = "test_results_async_e2e.txt"
        with open(report_file, "w") as f:
            f.write(report)
        
        print(f"📄 Full report saved to: {report_file}")
        
        # Return appropriate exit code
        successful_tests = sum(1 for r in results if r["success"])
        total_tests = len(results)
        
        if successful_tests == total_tests:
            print("🎉 All tests passed!")
            return 0
        else:
            print(f"⚠️  {total_tests - successful_tests} out of {total_tests} tests failed")
            return 1
            
    except KeyboardInterrupt:
        print("\n⏹️  Tests interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Test runner failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    # Run with proper async handling
    exit_code = asyncio.run(main())
    sys.exit(exit_code)