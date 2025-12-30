#!/usr/bin/env python3
"""Test script for DocuFlow Headless implementation."""

import asyncio
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.graph import run_extraction

async def test_basic_functionality():
    """Test basic functionality with a simple web page."""
    print("🧪 Testing DocuFlow Headless Implementation")
    print("=" * 50)
    
    # Test 1: Simple web page
    print("\n1️⃣ Testing web page extraction...")
    try:
        result = await run_extraction(
            source_url="https://httpbin.org/html",
            target_schema={
                "title": "string",
                "h1_text": "string",
                "paragraphs": "array"
            },
            use_gpu_ocr=False,
            confidence_threshold=0.5,
            dev_mode=True  # Use Ollama for development
        )
        
        print(f"Status: {result['status']}")
        if result['status'] == 'success':
            print(f"Confidence: {result['extraction_confidence']}")
            print(f"Data: {result['final_data']}")
            print("✅ Web extraction test PASSED")
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
            print("❌ Web extraction test FAILED")
            
    except Exception as e:
        print(f"❌ Web extraction test FAILED: {e}")
    
    # Test 2: Error handling - private URL
    print("\n2️⃣ Testing error handling (private URL)...")
    try:
        result = await run_extraction(
            source_url="http://httpstat.us/403",
            target_schema={"test": "string"},
            use_gpu_ocr=False,
            dev_mode=True  # Use Ollama for development
        )
        
        if result['status'] == 'failed':
            print(f"Expected failure: {result.get('error', 'Unknown error')}")
            print("✅ Error handling test PASSED")
        else:
            print("❌ Error handling test FAILED - should have failed")
            
    except Exception as e:
        print(f"✅ Error handling test PASSED: {e}")
    
    # Test 3: Document processing (if we have a test document)
    print("\n3️⃣ Testing document processing...")
    test_pdf = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
    try:
        result = await run_extraction(
            source_url=test_pdf,
            target_schema={
                "title": "string",
                "content_type": "string"
            },
            use_gpu_ocr=False,  # Start with CPU
            confidence_threshold=0.6,
            dev_mode=True  # Use Ollama for development
        )
        
        print(f"Status: {result['status']}")
        if result['status'] == 'success':
            print(f"Confidence: {result['extraction_confidence']}")
            print(f"GPU OCR used: {result.get('gpu_ocr_used', False)}")
            print(f"Data: {result['final_data']}")
            print("✅ Document processing test PASSED")
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
            print("❌ Document processing test FAILED")
            
    except Exception as e:
        print(f"❌ Document processing test FAILED: {e}")

async def test_ollama_integration():
    """Test Ollama integration for local models."""
    print("\n4️⃣ Testing Ollama integration...")
    
    try:
        # Check if Ollama is available
        import aiohttp
        ollama_host = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{ollama_host}/api/tags") as response:
                if response.status == 200:
                    models = await response.json()
                    print(f"Ollama available with models: {[m['name'] for m in models.get('models', [])]}")
                    
                    # Check for our specific models
                    available_models = [m['name'] for m in models.get('models', [])]
                    
                    if 'granite4:3b' in available_models:
                        print("✅ granite4:3b model available")
                    else:
                        print("⚠️  granite4:3b model not found")
                    
                    if 'deepseek-ocr:3b' in available_models:
                        print("✅ deepseek-ocr:3b model available")
                    else:
                        print("⚠️  deepseek-ocr:3b model not found")
                    
                    print("✅ Ollama integration test PASSED")
                else:
                    print(f"❌ Ollama not available: {response.status}")
                    
    except Exception as e:
        print(f"❌ Ollama integration test FAILED: {e}")
        print("Make sure Ollama is running with: ollama serve")

def check_environment():
    """Check environment setup."""
    print("\n🔍 Checking environment setup...")
    
    # For dev mode, we don't need Groq API key
    print("🧪 Running in development mode (using Ollama)")
    
    # Simple check for Ollama - just try to connect
    try:
        import urllib.request
        import json
        
        ollama_host = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
        
        # Try to get models list
        req = urllib.request.Request(f"{ollama_host}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                available_models = [m['name'] for m in data.get('models', [])]
                
                required_models = ["granite4:3b", "deepseek-ocr:3b", "ministral-3:3b"]
                missing_models = [model for model in required_models if model not in available_models]
                
                if missing_models:
                    print(f"⚠️  Missing Ollama models: {missing_models}")
                    print("   Run: ollama pull " + " ".join(missing_models))
                else:
                    print("✅ All required Ollama models available")
                
                return True
            else:
                print(f"❌ Ollama not available: {response.status}")
                return False
                
    except Exception as e:
        print(f"❌ Ollama check failed: {e}")
        print("Make sure Ollama is running with: ollama serve")
        print("   and required models are installed:")
        print("   ollama pull granite4:3b")
        print("   ollama pull deepseek-ocr:3b")
        print("   ollama pull ministral-3:3b")
        return False
    
    # Check optional variables
    optional_vars = ["OLLAMA_HOST", "MODAL_OCR_ENDPOINT", "APIFY_PROXY_PASSWORD"]
    for var in optional_vars:
        if os.getenv(var):
            print(f"✅ {var} is set")
        else:
            print(f"⚠️  {var} is not set (optional)")
    
    return True

async def main():
    """Main test function."""
    print("🚀 Starting DocuFlow Headless Tests")
    print("=" * 50)
    
    # Check environment first
    if not check_environment():
        print("\n❌ Environment check failed. Please set up required variables.")
        return 1
    
    # Run tests
    await test_basic_functionality()
    await test_ollama_integration()
    
    print("\n" + "=" * 50)
    print("🎯 Test Summary")
    print("Review the results above to see which tests passed/failed.")
    print("\nNext steps:")
    print("1. Set up Ollama with required models if not already done:")
    print("   ollama pull granite4:3b")
    print("   ollama pull deepseek-ocr:3b")
    print("   ollama pull ministral-3:3b")
    print("2. Start Ollama server: ollama serve")
    print("3. For production, set up Groq API key in .env file")
    print("4. Run more comprehensive tests with real documents")
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)