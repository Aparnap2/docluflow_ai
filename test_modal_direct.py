#!/usr/bin/env python3
"""
Direct testing of deployed Modal endpoints using OpenAI-compatible API.
Tests health checks and basic functionality.
"""

import requests
import json
import time
from pathlib import Path
import base64
from datetime import datetime
import sys

# Modal endpoint URLs
GRANITE_CPU_URL = "https://ap3617180--granite-docling-cpu-final-serve.modal.run"
DEEPSEEK_GPU_URL = "https://ap3617180--deepseek-ocr-gpu-final-serve.modal.run"

def test_health_check(endpoint_url: str, endpoint_name: str) -> bool:
    """Test health check endpoint."""
    try:
        print(f"🩺 Testing health check for {endpoint_name}...")
        print(f"   URL: {endpoint_url}/health")
        
        response = requests.get(f"{endpoint_url}/health", timeout=30)
        
        if response.status_code == 200:
            health_data = response.json()
            print(f"   ✅ Health check PASSED: {health_data}")
            return True
        else:
            print(f"   ❌ Health check FAILED: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"   ❌ Health check ERROR: {str(e)}")
        return False

def test_openai_chat_completion(endpoint_url: str, endpoint_name: str) -> bool:
    """Test OpenAI-compatible chat completion endpoint."""
    try:
        print(f"💬 Testing OpenAI chat completion for {endpoint_name}...")
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        payload = {
            "model": "llm",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful assistant that processes documents."
                },
                {
                    "role": "user",
                    "content": "Hello! Please confirm you are working and can process documents."
                }
            ],
            "max_tokens": 100,
            "temperature": 0.1,
            "stream": False
        }
        
        print(f"   Sending request to: {endpoint_url}/v1/chat/completions")
        start_time = time.time()
        
        response = requests.post(
            f"{endpoint_url}/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        
        elapsed_time = time.time() - start_time
        
        if response.status_code == 200:
            result = response.json()
            print(f"   ✅ Chat completion PASSED ({elapsed_time:.2f}s)")
            print(f"   Response: {result.get('choices', [{}])[0].get('message', {}).get('content', 'No content')[:100]}...")
            return True
        else:
            print(f"   ❌ Chat completion FAILED: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"   ❌ Chat completion ERROR: {str(e)}")
        return False

def test_document_processing(endpoint_url: str, endpoint_name: str, file_path: Path) -> bool:
    """Test document processing with file upload."""
    try:
        print(f"📄 Testing document processing for {endpoint_name} with {file_path.name}...")
        
        # Read file
        with open(file_path, 'rb') as f:
            file_content = f.read()
        
        # Create multipart form data
        files = {
            'file': (file_path.name, file_content, 'application/octet-stream')
        }
        
        data = {
            'model': 'llm',
            'messages': json.dumps([
                {
                    "role": "user",
                    "content": f"Process this {file_path.suffix[1:].upper()} document and extract all text content"
                }
            ]),
            'max_tokens': '500',
            'temperature': '0.1',
            'stream': 'false'
        }
        
        print(f"   Sending file to: {endpoint_url}/v1/chat/completions")
        start_time = time.time()
        
        response = requests.post(
            f"{endpoint_url}/v1/chat/completions",
            files=files,
            data=data,
            timeout=120
        )
        
        elapsed_time = time.time() - start_time
        
        if response.status_code == 200:
            result = response.json()
            content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            print(f"   ✅ Document processing PASSED ({elapsed_time:.2f}s)")
            print(f"   Extracted content preview: {content[:150]}...")
            return True
        else:
            print(f"   ❌ Document processing FAILED: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"   ❌ Document processing ERROR: {str(e)}")
        return False

def create_simple_test_files():
    """Create simple test files for testing."""
    test_dir = Path("test_files")
    test_dir.mkdir(exist_ok=True)
    
    # Create a simple text file
    text_file = test_dir / "test_document.txt"
    with open(text_file, 'w') as f:
        f.write("""INVOICE
Date: January 15, 2024
Invoice Number: INV-2024-001
Vendor: TechCorp Solutions
Amount: $1,250.00

This is a test document for DocuFlow Headless v2 production testing.
The system should extract vendor information, dates, and amounts.

Payment Terms: Net 30
Due Date: February 14, 2024""")
    
    print(f"📁 Created test file: {text_file}")
    return text_file

def run_production_tests():
    """Run comprehensive production tests."""
    print("🚀 Starting DocuFlow Headless v2 Production Testing")
    print("=" * 60)
    print(f"🕐 Timestamp: {datetime.now().isoformat()}")
    print("=" * 60)
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "tests": [],
        "summary": {}
    }
    
    # Test 1: Health Checks
    print("\n📋 TEST 1: HEALTH CHECKS")
    print("-" * 40)
    
    cpu_health = test_health_check(GRANITE_CPU_URL, "Granite-Docling CPU")
    gpu_health = test_health_check(DEEPSEEK_GPU_URL, "DeepSeek-OCR GPU")
    
    results["tests"].append({
        "test": "health_checks",
        "cpu_health": cpu_health,
        "gpu_health": gpu_health,
        "overall_health": cpu_health and gpu_health
    })
    
    # Test 2: Basic Chat Completion
    print("\n📋 TEST 2: BASIC CHAT COMPLETION")
    print("-" * 40)
    
    cpu_chat = test_openai_chat_completion(GRANITE_CPU_URL, "Granite-Docling CPU")
    gpu_chat = test_openai_chat_completion(DEEPSEEK_GPU_URL, "DeepSeek-OCR GPU")
    
    results["tests"].append({
        "test": "basic_chat",
        "cpu_chat": cpu_chat,
        "gpu_chat": gpu_chat,
        "overall_chat": cpu_chat and gpu_chat
    })
    
    # Test 3: Document Processing
    print("\n📋 TEST 3: DOCUMENT PROCESSING")
    print("-" * 40)
    
    test_file = create_simple_test_files()
    
    cpu_doc = test_document_processing(GRANITE_CPU_URL, "Granite-Docling CPU", test_file)
    gpu_doc = test_document_processing(DEEPSEEK_GPU_URL, "DeepSeek-OCR GPU", test_file)
    
    results["tests"].append({
        "test": "document_processing",
        "cpu_doc": cpu_doc,
        "gpu_doc": gpu_doc,
        "overall_doc": cpu_doc and gpu_doc
    })
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 PRODUCTION TEST SUMMARY")
    print("=" * 60)
    
    health_passed = results["tests"][0]["overall_health"]
    chat_passed = results["tests"][1]["overall_chat"]
    doc_passed = results["tests"][2]["overall_doc"]
    
    overall_success = health_passed and chat_passed and doc_passed
    
    print(f"✅ Health Checks: {'PASSED' if health_passed else 'FAILED'}")
    print(f"✅ Basic Chat: {'PASSED' if chat_passed else 'FAILED'}")
    print(f"✅ Document Processing: {'PASSED' if doc_passed else 'FAILED'}")
    print(f"🎯 Overall Result: {'✅ ALL TESTS PASSED' if overall_success else '❌ SOME TESTS FAILED'}")
    print("=" * 60)
    
    results["summary"] = {
        "health_checks": health_passed,
        "basic_chat": chat_passed,
        "document_processing": doc_passed,
        "overall_success": overall_success
    }
    
    # Save results
    results_file = "test_results_modal_direct.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"💾 Results saved to: {results_file}")
    
    return overall_success

if __name__ == "__main__":
    success = run_production_tests()
    sys.exit(0 if success else 1)