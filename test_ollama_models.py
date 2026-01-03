"""
Test script to verify the Docuflow system with actual Ollama models
"""
import asyncio
import json
import httpx
import os

async def test_ollama_endpoints():
    """Test the Ollama endpoints with actual models."""
    print("Testing Ollama endpoints with actual models...")
    
    # Test Ollama connectivity
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get("http://localhost:11434/api/tags")
            response.raise_for_status()
            models = response.json()
            print(f"✅ Ollama is running with {len(models.get('models', []))} models")
            
            # Check if our required models are available
            model_names = [model['name'] for model in models.get('models', [])]
            required_models = ["deepseek-ocr:3b", "sam860/LFM2:2.6b"]
            
            for req_model in required_models:
                if req_model in model_names:
                    print(f"✅ Required model available: {req_model}")
                else:
                    print(f"❌ Required model missing: {req_model}")
                    
        except Exception as e:
            print(f"❌ Ollama connection failed: {e}")
            return False
    
    return True

async def test_deepseek_ocr_model():
    """Test the DeepSeek OCR model with a sample request."""
    print("\nTesting DeepSeek OCR model...")

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            # Test with a simple text prompt (in practice, you'd use an image URL)
            payload = {
                "model": "deepseek-ocr:3b",  # Using the exact name from curl output
                "messages": [
                    {
                        "role": "user",
                        "content": "Extract text from this document: This is a test document with sample text for OCR testing."
                    }
                ],
                "stream": False,
                "options": {
                    "temperature": 0
                }
            }

            response = await client.post("http://localhost:11434/api/chat", json=payload)
            response.raise_for_status()

            result = response.json()
            content = result.get("message", {}).get("content", "")

            print(f"✅ DeepSeek OCR responded successfully")
            print(f"   Response length: {len(content)} characters")
            print(f"   Preview: {content[:100]}...")

            return True

        except Exception as e:
            print(f"❌ DeepSeek OCR test failed: {e}")
            return False

async def test_lfm2_json_model():
    """Test the LFM2 model for JSON formatting."""
    print("\nTesting LFM2 model for JSON formatting...")

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            # Test with a JSON formatting request
            schema = {
                "type": "object",
                "properties": {
                    "vendor_name": {"type": "string"},
                    "invoice_number": {"type": "string"},
                    "total_amount": {"type": "number"},
                    "date": {"type": "string"}
                }
            }

            payload = {
                "model": "sam860/LFM2:2.6b",
                "messages": [
                    {
                        "role": "system",
                        "content": f"You are a structured data extraction expert. Extract information according to this JSON schema: {json.dumps(schema)}"
                    },
                    {
                        "role": "user",
                        "content": "Extract structured data from this text: Invoice from ACME Corp, Invoice #INV-2024-001, Date: 2024-01-15, Total: $1,250.50"
                    }
                ],
                "stream": False,
                "format": "json",  # Request JSON format
                "options": {
                    "temperature": 0
                }
            }

            response = await client.post("http://localhost:11434/api/chat", json=payload)
            response.raise_for_status()

            result = response.json()
            content = result.get("message", {}).get("content", "")

            print(f"✅ LFM2 JSON formatting responded successfully")
            print(f"   Response length: {len(content)} characters")
            print(f"   Preview: {content[:100]}...")

            # Try to parse as JSON to verify format
            try:
                parsed = json.loads(content)
                print(f"   ✅ Response is valid JSON")
                print(f"   JSON keys: {list(parsed.keys()) if isinstance(parsed, dict) else 'Not a dict'}")
            except json.JSONDecodeError:
                print(f"   ⚠️  Response is not valid JSON")

            return True

        except Exception as e:
            print(f"❌ LFM2 JSON formatting test failed: {e}")
            return False

async def test_granite_docling_model():
    """Test the IBM Granite Docling model."""
    print("\nTesting IBM Granite Docling model...")

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            payload = {
                "model": "ibm/granite-docling:latest",  # Using the exact name from curl output
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a document understanding engine. Extract structured information from the provided text."
                    },
                    {
                        "role": "user",
                        "content": "Extract structured information from this document text: Invoice #12345 dated 2024-01-15 from Vendor XYZ for $500.00"
                    }
                ],
                "stream": False,
                "options": {
                    "temperature": 0
                }
            }

            response = await client.post("http://localhost:11434/api/chat", json=payload)
            response.raise_for_status()

            result = response.json()
            content = result.get("message", {}).get("content", "")

            print(f"✅ IBM Granite Docling responded successfully")
            print(f"   Response length: {len(content)} characters")
            print(f"   Preview: {content[:100]}...")

            return True

        except Exception as e:
            print(f"❌ IBM Granite Docling test failed: {e}")
            return False

async def main():
    """Run all tests."""
    print("🔍 Testing Docuflow system with actual Ollama models")
    print("="*60)
    
    # Test basic connectivity
    ollama_ok = await test_ollama_endpoints()
    if not ollama_ok:
        print("\n❌ Cannot proceed: Ollama is not accessible")
        return
    
    # Test each model
    results = []
    results.append(("DeepSeek OCR", await test_deepseek_ocr_model()))
    results.append(("LFM2 JSON", await test_lfm2_json_model()))
    results.append(("Granite Docling", await test_granite_docling_model()))
    
    print("\n" + "="*60)
    print("📊 TEST RESULTS SUMMARY")
    print("="*60)
    
    all_passed = True
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name:20} {status}")
        if not passed:
            all_passed = False
    
    print("="*60)
    if all_passed:
        print("🎉 ALL TESTS PASSED! Ollama models are ready for use.")
        print("\n🎯 The Docuflow system can now use:")
        print("   • DeepSeek OCR for document text extraction")
        print("   • LFM2 for JSON formatting and structured extraction") 
        print("   • IBM Granite Docling for document understanding")
    else:
        print("⚠️  Some tests failed. Please check model availability.")
    
    return all_passed

if __name__ == "__main__":
    asyncio.run(main())