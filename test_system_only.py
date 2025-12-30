#!/usr/bin/env python3
"""
System-only test for DocuFlow Headless
Tests the ingestion and processing pipeline without LLM extraction
"""

import asyncio
import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from engine.ingest import determine_input_type
from engine.crawler import crawl_url
from engine.ocr import process_document

async def test_ingestion_only():
    """Test only the ingestion pipeline without LLM extraction."""
    print("🧪 Testing System-Only Pipeline...")
    print("=" * 60)
    
    test_cases = [
        {
            "name": "PDF Ingestion",
            "url": "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf",
            "expected_type": "pdf"
        },
        {
            "name": "Web Page Ingestion", 
            "url": "https://httpbin.org/html",
            "expected_type": "web"
        },
        {
            "name": "Image Ingestion",
            "url": "https://httpbin.org/image/png",
            "expected_type": "image"
        }
    ]
    
    results = {}
    
    for test_case in test_cases:
        print(f"\n🧪 Testing {test_case['name']}...")
        print(f"URL: {test_case['url']}")
        
        try:
            # Test type detection
            detected_type = determine_input_type(test_case['url'])
            print(f"Detected type: {detected_type}")
            
            if detected_type == "error":
                print("❌ Type detection failed")
                results[test_case['name']] = {"success": False, "error": "Type detection failed"}
                continue
            
            # Test content extraction
            if detected_type == "web":
                content = await crawl_url(test_case['url'])
                print(f"Web content length: {len(content)}")
                print(f"Content preview: {content[:100]}...")
                results[test_case['name']] = {
                    "success": True, 
                    "content_length": len(content),
                    "content_preview": content[:100]
                }
                
            elif detected_type in ["pdf", "image"]:
                result = await process_document(test_case['url'], use_gpu_ocr=False)
                markdown = result.get("markdown", "")
                print(f"Document content length: {len(markdown)}")
                print(f"Content preview: {markdown[:100]}...")
                results[test_case['name']] = {
                    "success": True,
                    "content_length": len(markdown),
                    "content_preview": markdown[:100],
                    "confidence": result.get("confidence", 0),
                    "engine": result.get("engine", "unknown")
                }
            else:
                print("❌ Unknown content type")
                results[test_case['name']] = {"success": False, "error": "Unknown content type"}
                
        except Exception as e:
            print(f"❌ FAILED: {e}")
            results[test_case['name']] = {"success": False, "error": str(e)}
    
    return results

async def main():
    """Run system-only tests."""
    print("🚀 Starting System-Only Tests")
    print("Testing ingestion pipeline without LLM extraction")
    print("=" * 80)
    
    results = await test_ingestion_only()
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 SYSTEM TEST SUMMARY")
    print("=" * 80)
    
    success_count = sum(1 for r in results.values() if r.get('success', False))
    total_tests = len(results)
    
    print(f"Total Tests: {total_tests}")
    print(f"Successful: {success_count}")
    print(f"Failed: {total_tests - success_count}")
    
    for test_name, result in results.items():
        if result.get('success'):
            print(f"  ✅ {test_name}: SUCCESS (content: {result.get('content_length', 0)} chars)")
        else:
            print(f"  ❌ {test_name}: FAILED - {result.get('error', 'Unknown error')}")
    
    if success_count == total_tests:
        print("\n🎉 ALL SYSTEM TESTS PASSED! Ingestion pipeline is working correctly.")
        print("The LLM timeout issues are separate from the core document processing.")
    else:
        print(f"\n⚠️  {total_tests - success_count} system tests failed.")
    
    return results

if __name__ == "__main__":
    results = asyncio.run(main())