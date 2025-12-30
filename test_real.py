#!/usr/bin/env python3
"""
Real End-to-End Test for DocuFlow Headless
Tests actual networking, Crawl4AI, Docling, and Groq integration with real URLs
"""

import asyncio
import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from graph import run_extraction

async def test_real_pdf():
    """Test with a real, stable W3C PDF to validate Docling integration."""
    print("🧪 Testing REAL Public PDF...")
    print("=" * 60)
    
    # A real, stable W3C PDF
    real_pdf = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
    
    state = {
        "source_url": real_pdf,
        "input_type": "auto",
        "target_schema": {"title": "string", "content_type": "string", "page_count": "number"},
        "use_gpu_ocr": False,
        "confidence_threshold": 0.5,
        "retries": 0,
        "errors": [],
        "dev_mode": True  # Force dev mode to use Ollama
    }
    
    try:
        print(f"📄 Processing: {real_pdf}")
        print("⏳ This will test actual networking, Docling CPU processing, and LLM extraction...")
        
        result = await run_extraction(
            source_url=state["source_url"],
            target_schema=state["target_schema"],
            use_gpu_ocr=state.get("use_gpu_ocr", False),
            confidence_threshold=state.get("confidence_threshold", 0.5),
            dev_mode=True  # Force dev mode
        )
        
        print("\n📊 RESULTS:")
        print(f"Status: {result.get('status', 'unknown')}")
        print(f"Has Data: {result.get('has_data', False)}")
        print(f"Confidence: {result.get('confidence', 0)}")
        print(f"GPU OCR Used: {result.get('gpu_ocr_used', False)}")
        
        if result.get('output'):
            print(f"Extracted Data: {json.dumps(result['output'], indent=2)}")
        
        if result.get('errors'):
            print(f"Errors: {result['errors']}")
            
        print("\n✅ Real PDF test completed!")
        return result
        
    except Exception as e:
        print(f"❌ FAILED: {e}")
        print(f"Error Type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return None

async def test_real_webpage():
    """Test with a real webpage to validate Crawl4AI integration."""
    print("\n🧪 Testing REAL Web Page...")
    print("=" * 60)
    
    # A simple, stable webpage
    real_webpage = "https://httpbin.org/html"
    
    state = {
        "source_url": real_webpage,
        "input_type": "auto",
        "target_schema": {"title": "string", "h1_text": "string", "has_moby_dick": "boolean"},
        "use_gpu_ocr": False,
        "confidence_threshold": 0.5,
        "retries": 0,
        "errors": [],
        "dev_mode": True  # Force dev mode to use Ollama
    }
    
    try:
        print(f"🌐 Processing: {real_webpage}")
        print("⏳ This will test actual networking, Crawl4AI web scraping, and LLM extraction...")
        
        result = await run_extraction(
            source_url=state["source_url"],
            target_schema=state["target_schema"],
            use_gpu_ocr=state.get("use_gpu_ocr", False),
            confidence_threshold=state.get("confidence_threshold", 0.5),
            dev_mode=True  # Force dev mode
        )
        
        print("\n📊 RESULTS:")
        print(f"Status: {result.get('status', 'unknown')}")
        print(f"Has Data: {result.get('has_data', False)}")
        print(f"Confidence: {result.get('confidence', 0)}")
        print(f"GPU OCR Used: {result.get('gpu_ocr_used', False)}")
        
        if result.get('output'):
            print(f"Extracted Data: {json.dumps(result['output'], indent=2)}")
        
        if result.get('errors'):
            print(f"Errors: {result['errors']}")
            
        print("\n✅ Real webpage test completed!")
        return result
        
    except Exception as e:
        print(f"❌ FAILED: {e}")
        print(f"Error Type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return None

async def test_real_image():
    """Test with a real image to validate DeepSeek OCR integration."""
    print("\n🧪 Testing REAL Image with OCR...")
    print("=" * 60)
    
    # A simple, stable image (using httpbin which is more reliable)
    real_image = "https://httpbin.org/image/png"
    
    state = {
        "source_url": real_image,
        "input_type": "auto",
        "target_schema": {"image_type": "string", "has_content": "boolean"},
        "use_gpu_ocr": True,  # Force GPU OCR for images
        "confidence_threshold": 0.5,
        "retries": 0,
        "errors": [],
        "dev_mode": True  # Force dev mode to use Ollama
    }
    
    try:
        print(f"🖼️  Processing: {real_image}")
        print("⏳ This will test actual networking, DeepSeek OCR, and LLM extraction...")
        
        result = await run_extraction(
            source_url=state["source_url"],
            target_schema=state["target_schema"],
            use_gpu_ocr=state.get("use_gpu_ocr", False),
            confidence_threshold=state.get("confidence_threshold", 0.5),
            dev_mode=True  # Force dev mode
        )
        
        print("\n📊 RESULTS:")
        print(f"Status: {result.get('status', 'unknown')}")
        print(f"Has Data: {result.get('has_data', False)}")
        print(f"Confidence: {result.get('confidence', 0)}")
        print(f"GPU OCR Used: {result.get('gpu_ocr_used', False)}")
        
        if result.get('output'):
            print(f"Extracted Data: {json.dumps(result['output'], indent=2)}")
        
        if result.get('errors'):
            print(f"Errors: {result['errors']}")
            
        print("\n✅ Real image test completed!")
        return result
        
    except Exception as e:
        print(f"❌ FAILED: {e}")
        print(f"Error Type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return None

async def main():
    """Run all real E2E tests."""
    print("🚀 Starting REAL End-to-End Tests")
    print("This will test actual networking, document processing, and LLM extraction")
    print("=" * 80)
    
    results = {}
    
    # Test 1: Real PDF with Docling
    results['pdf'] = await test_real_pdf()
    
    # Test 2: Real webpage with Crawl4AI
    results['webpage'] = await test_real_webpage()
    
    # Test 3: Real image with DeepSeek OCR
    results['image'] = await test_real_image()
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 FINAL TEST SUMMARY")
    print("=" * 80)
    
    success_count = sum(1 for r in results.values() if r and r.get('status') == 'success')
    total_tests = len(results)
    
    print(f"Total Tests: {total_tests}")
    print(f"Successful: {success_count}")
    print(f"Failed: {total_tests - success_count}")
    
    for test_name, result in results.items():
        if result:
            status = result.get('status', 'unknown')
            has_data = result.get('has_data', False)
            confidence = result.get('confidence', 0)
            print(f"  {test_name}: {status} (data: {has_data}, conf: {confidence:.2f})")
        else:
            print(f"  {test_name}: FAILED")
    
    if success_count == total_tests:
        print("\n🎉 ALL REAL TESTS PASSED! System is ready for deployment.")
    else:
        print(f"\n⚠️  {total_tests - success_count} tests failed. Need to fix before deployment.")
    
    return results

if __name__ == "__main__":
    results = asyncio.run(main())