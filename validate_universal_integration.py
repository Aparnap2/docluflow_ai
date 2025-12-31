"""Simple validation script for Universal OpenAI SDK + Modal integration."""

import os
import sys
import asyncio
import tempfile
from datetime import datetime
import structlog

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from engine.universal_llm import UniversalLLMExtractor
from engine.modal_client import ModalCPUClient, ModalGPUClient, check_modal_endpoints
from models import create_dynamic_schema, format_n8n_output

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
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

def test_dynamic_schema_creation():
    """Test dynamic Pydantic model creation."""
    print("\n🧪 Testing Dynamic Schema Creation...")
    
    user_schema = {
        "invoice_number": "string",
        "date": "string", 
        "amount": "number",
        "paid": "boolean"
    }
    
    try:
        DynamicModel = create_dynamic_schema(user_schema)
        
        # Test model instantiation
        instance = DynamicModel(
            invoice_number="INV-001",
            date="2024-01-01",
            amount=100.50,
            paid=True
        )
        
        assert instance.invoice_number == "INV-001"
        assert instance.date == "2024-01-01"
        assert instance.amount == 100.50
        assert instance.paid is True
        
        # Test optional fields (anti-hallucination)
        instance2 = DynamicModel()  # All fields should be optional
        assert instance2.invoice_number is None
        assert instance2.date is None
        assert instance2.amount is None
        assert instance2.paid is None
        
        print("✅ Dynamic schema creation test passed")
        return True
        
    except Exception as e:
        print(f"❌ Dynamic schema creation failed: {e}")
        return False

def test_n8n_output_formatting():
    """Test n8n-compatible output formatting."""
    print("\n🧪 Testing n8n Output Formatting...")
    
    try:
        extracted_data = {
            "invoice_number": "INV-2024-001",
            "date": "2024-01-15",
            "vendor": "TechCorp Solutions",
            "total_amount": 1300.50
        }
        
        result = format_n8n_output(extracted_data, "test_invoice.pdf", "cpu_fast")
        
        assert "main_data" in result
        assert "_meta" in result
        assert result["main_data"] == extracted_data
        assert result["_meta"]["processed_by"] == "cpu_fast"
        assert result["_meta"]["original_filename"] == "test_invoice.pdf"
        assert "suggested_filename" in result["_meta"]
        assert "routing_folder" in result["_meta"]
        
        # Validate filename format
        suggested_filename = result["_meta"]["suggested_filename"]
        assert "2024-01-15" in suggested_filename
        assert "TechCorp Solutions" in suggested_filename
        
        # Validate routing folder format
        routing_folder = result["_meta"]["routing_folder"]
        assert "/2024/01/TechCorp Solutions" == routing_folder
        
        print("✅ n8n output formatting test passed")
        print(f"   📄 Suggested filename: {suggested_filename}")
        print(f"   📁 Routing folder: {routing_folder}")
        return True
        
    except Exception as e:
        print(f"❌ n8n output formatting failed: {e}")
        return False

async def test_groq_universal_sdk():
    """Test Groq integration with Universal OpenAI SDK format."""
    print("\n🧪 Testing Groq Universal SDK...")
    
    # Skip if no API key
    if not os.getenv('GROQ_API_KEY'):
        print("⚠️  Skipping Groq test - GROQ_API_KEY not configured")
        return True
    
    try:
        extractor = UniversalLLMExtractor(provider="groq", model_name="llama-3-70b-8192")
        
        sample_schema = {
            "invoice_number": {"type": "string", "description": "Invoice number"},
            "date": {"type": "string", "description": "Invoice date"},
            "vendor": {"type": "string", "description": "Vendor name"},
            "total_amount": {"type": "number", "description": "Total amount"}
        }
        
        sample_content = """
        INVOICE #INV-2024-001
        Date: 2024-01-15
        Vendor: TechCorp Solutions
        
        Items:
        - Laptop: $1,200.00
        - Mouse: $25.50
        - Keyboard: $75.00
        
        Total: $1,300.50
        """
        
        result = await extractor.extract_structured_data(sample_content, sample_schema)
        
        assert result.success is True
        assert result.data is not None
        assert result.confidence > 0.0
        assert isinstance(result.needs_gpu_ocr, bool)
        
        print("✅ Groq Universal SDK test passed")
        print(f"   📊 Confidence: {result.confidence}")
        print(f"   🎯 Extracted fields: {len(result.data)}")
        return True
        
    except Exception as e:
        print(f"❌ Groq Universal SDK test failed: {e}")
        return False

def test_anti_hallucination_constraints():
    """Test anti-hallucination constraints are enforced."""
    print("\n🧪 Testing Anti-Hallucination Constraints...")
    
    try:
        # Test that all fields are Optional in dynamic schema
        user_schema = {
            "required_field": "string",
            "another_required": "number"
        }
        
        DynamicModel = create_dynamic_schema(user_schema)
        
        # Should be able to create instance without any fields
        instance = DynamicModel()
        assert instance.required_field is None
        assert instance.another_required is None
        
        # Should be able to create instance with partial fields
        instance2 = DynamicModel(required_field="test")
        assert instance2.required_field == "test"
        assert instance2.another_required is None
        
        print("✅ Anti-hallucination constraints verified")
        return True
        
    except Exception as e:
        print(f"❌ Anti-hallucination constraints failed: {e}")
        return False

def test_no_torch_transformers_in_main():
    """Verify no torch/transformers imports in main container."""
    print("\n🧪 Testing No Torch/Transformers in Main Container...")
    
    try:
        import sys
        
        # Check that torch is not imported
        assert 'torch' not in sys.modules, "torch should not be imported in main container"
        
        # Check that transformers is not imported  
        assert 'transformers' not in sys.modules, "transformers should not be imported in main container"
        
        print("✅ Anti-hallucination import check passed")
        return True
        
    except AssertionError as e:
        print(f"❌ Anti-hallucination import check failed: {e}")
        return False

async def test_modal_client_initialization():
    """Test Modal client initialization."""
    print("\n🧪 Testing Modal Client Initialization...")
    
    success_count = 0
    total_tests = 0
    
    # Test CPU client
    total_tests += 1
    if os.getenv('MODAL_GRANITE_URL'):
        try:
            client = ModalCPUClient()
            assert client.endpoint_url == os.getenv('MODAL_GRANITE_URL')
            assert client.model_name == "ibm-granite/granite-docling-258M"
            print("✅ Modal CPU client initialized successfully")
            success_count += 1
        except Exception as e:
            print(f"⚠️  Modal CPU client initialization failed: {e}")
    else:
        print("⚠️  Skipping Modal CPU client - MODAL_GRANITE_URL not configured")
    
    # Test GPU client
    total_tests += 1
    if os.getenv('MODAL_DEEPSEEK_URL'):
        try:
            client = ModalGPUClient()
            assert client.endpoint_url == os.getenv('MODAL_DEEPSEEK_URL')
            assert client.model_name == "deepseek-ai/DeepSeek-OCR"
            print("✅ Modal GPU client initialized successfully")
            success_count += 1
        except Exception as e:
            print(f"⚠️  Modal GPU client initialization failed: {e}")
    else:
        print("⚠️  Skipping Modal GPU client - MODAL_DEEPSEEK_URL not configured")
    
    return success_count == total_tests or total_tests == 0

async def test_modal_endpoint_health():
    """Test Modal endpoint health checking."""
    print("\n🧪 Testing Modal Endpoint Health Check...")
    
    try:
        results = await check_modal_endpoints()
        
        assert isinstance(results, dict)
        assert 'granite_docling' in results
        assert 'deepseek_ocr' in results
        
        for service, status in results.items():
            assert 'status' in status
            assert 'endpoint' in status or 'error' in status
            
        print("✅ Modal endpoint health check completed")
        for service, status in results.items():
            print(f"   🔍 {service}: {status['status']}")
        return True
        
    except Exception as e:
        print(f"❌ Modal endpoint health check failed: {e}")
        return False

def test_environment_configuration():
    """Test environment variable configuration."""
    print("\n🧪 Testing Environment Configuration...")
    
    required_vars = [
        'GROQ_API_KEY',
        'MODAL_GRANITE_URL',
        'MODAL_DEEPSEEK_URL'
    ]
    
    configured_count = 0
    for var in required_vars:
        value = os.getenv(var)
        if value and 'placeholder' not in value.lower():
            print(f"   ✅ {var}: Configured")
            configured_count += 1
        else:
            print(f"   ⚠️  {var}: Not configured or placeholder")
    
    print(f"   📊 Environment configuration: {configured_count}/{len(required_vars)} variables")
    return True  # Don't fail the test for missing env vars

async def run_all_tests():
    """Run all validation tests."""
    print("🚀 Starting Universal OpenAI SDK + Modal Integration Validation")
    print("=" * 70)
    
    tests = [
        ("Dynamic Schema Creation", test_dynamic_schema_creation),
        ("n8n Output Formatting", test_n8n_output_formatting),
        ("Anti-Hallucination Constraints", test_anti_hallucination_constraints),
        ("No Torch/Transformers in Main", test_no_torch_transformers_in_main),
        ("Modal Client Initialization", test_modal_client_initialization),
        ("Modal Endpoint Health", test_modal_endpoint_health),
        ("Environment Configuration", test_environment_configuration),
        ("Groq Universal SDK", test_groq_universal_sdk),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 VALIDATION SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
    
    print(f"\n📈 Overall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All validation tests passed!")
        print("\n🚀 Ready for Modal deployment:")
        print("   1. Install Modal: pip install modal")
        print("   2. Authenticate: modal token set")
        print("   3. Deploy: python modal_backend/deploy_modal.py")
        return True
    else:
        print("⚠️  Some tests failed. Please review the output above.")
        return False

if __name__ == "__main__":
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv("src/.env")
    
    # Run tests
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)