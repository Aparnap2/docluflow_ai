#!/usr/bin/env python3
"""Comprehensive test with real URLs and longer timeouts for CPU processing."""

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Dict, Any

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

async def test_real_extraction():
    """Test with real URLs and longer timeouts for CPU processing."""
    print("🧪 Comprehensive Test with Real URLs (CPU-Optimized)")
    print("=" * 70)
    print("⚠️  This test will take several minutes due to CPU processing")
    print("=" * 70)
    
    # Real test cases with different document types
    test_cases = [
        {
            "name": "Simple Web Page",
            "url": "https://httpbin.org/html",
            "schema": {
                "title": "string",
                "h1_text": "string",
                "has_moby_dick": "boolean"
            },
            "timeout": 300,  # 5 minutes for CPU processing
            "description": "Basic HTML page extraction"
        },
        {
            "name": "Public PDF Document",
            "url": "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf",
            "schema": {
                "title": "string",
                "content_type": "string",
                "page_count": "number"
            },
            "timeout": 600,  # 10 minutes for PDF processing
            "description": "PDF document with OCR processing"
        },
        {
            "name": "API Documentation",
            "url": "https://raw.githubusercontent.com/apify/apify-docs/master/introduction/index.md",
            "schema": {
                "title": "string",
                "sections": "number",
                "has_introduction": "boolean"
            },
            "timeout": 300,  # 5 minutes
            "description": "Markdown content extraction"
        }
    ]
    
    results = []
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{i}. Testing: {test_case['name']}")
        print(f"   URL: {test_case['url']}")
        print(f"   Description: {test_case['description']}")
        print(f"   Timeout: {test_case['timeout']}s")
        print("   Status: 🔄 Starting...")
        
        start_time = time.time()
        
        try:
            # Run extraction with extended timeout
            result = await asyncio.wait_for(
                run_extraction(
                    source_url=test_case['url'],
                    target_schema=test_case['schema'],
                    use_gpu_ocr=False,  # Force CPU processing
                    confidence_threshold=0.5,
                    dev_mode=True  # Use Ollama models
                ),
                timeout=test_case['timeout']
            )
            
            duration = time.time() - start_time
            
            # Analyze results
            success = result.get('status') == 'success'
            has_data = bool(result.get('data'))
            confidence = result.get('confidence', 0.0)
            errors = result.get('errors', [])
            warnings = result.get('warnings', [])
            
            print(f"   Status: {'✅ Success' if success else '❌ Failed'}")
            print(f"   Duration: {duration:.1f}s")
            print(f"   Has Data: {'📊 Yes' if has_data else '📭 No'}")
            print(f"   Confidence: {confidence:.2f}")
            print(f"   Errors: {len(errors)}")
            print(f"   Warnings: {len(warnings)}")
            
            if has_data:
                print(f"   Extracted Data Preview:")
                data_preview = {k: str(v)[:50] + '...' if len(str(v)) > 50 else v 
                               for k, v in result['data'].items()}
                print(f"   {json.dumps(data_preview, indent=2)}")
            
            results.append({
                'name': test_case['name'],
                'success': success,
                'has_data': has_data,
                'duration': duration,
                'confidence': confidence,
                'error_count': len(errors),
                'warning_count': len(warnings)
            })
            
        except asyncio.TimeoutError:
            print(f"   Status: ⏰ Timeout after {test_case['timeout']}s")
            results.append({
                'name': test_case['name'],
                'success': False,
                'has_data': False,
                'duration': test_case['timeout'],
                'confidence': 0.0,
                'error_count': 1,
                'warning_count': 0
            })
            
        except Exception as e:
            duration = time.time() - start_time
            print(f"   Status: 💥 Error: {str(e)[:100]}...")
            results.append({
                'name': test_case['name'],
                'success': False,
                'has_data': False,
                'duration': duration,
                'confidence': 0.0,
                'error_count': 1,
                'warning_count': 0
            })
        
        # Brief pause between tests
        if i < len(test_cases):
            print("   ⏸️  Pausing 5 seconds...")
            await asyncio.sleep(5)
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 COMPREHENSIVE TEST SUMMARY")
    print("=" * 70)
    
    successful = sum(1 for r in results if r['success'])
    total = len(results)
    
    print(f"Total Tests: {total}")
    print(f"Successful: {successful} ({successful/total*100:.1f}%)")
    print(f"Failed: {total - successful}")
    
    print("\n📈 Detailed Results:")
    for result in results:
        status_icon = "✅" if result['success'] else "❌"
        data_icon = "📊" if result['has_data'] else "📭"
        print(f"   {status_icon} {result['name']}: {data_icon} "
              f"({result['duration']:.1f}s, conf: {result['confidence']:.2f}, "
              f"errors: {result['error_count']})")
    
    # Save detailed results
    results_file = "test_results_comprehensive.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n💾 Full results saved to: {results_file}")
    
    return results

if __name__ == "__main__":
    print("🚀 Starting Comprehensive Real-World Test")
    print("This will test the actual DocuFlow pipeline with real URLs")
    print("and CPU-optimized processing. Expect 10-20 minutes runtime.")
    print()
    
    results = asyncio.run(test_real_extraction())
    
    print("\n🎉 Comprehensive test completed!")
    print("The system has been tested with real document processing,")
    print("Ollama models, and CPU-optimized workflows.")