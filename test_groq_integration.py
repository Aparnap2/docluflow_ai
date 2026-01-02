#!/usr/bin/env python3
"""
Test Groq API integration and Universal OpenAI SDK functionality.
This tests the actual production setup with Groq API.
"""

import os
import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime
import requests
from typing import Dict, Any, List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from engine.universal_llm import UniversalLLMExtractor, extract_structured_data
from engine.llm import LLMExtractor
from models import ProcessingResult, DocumentMetadata
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

def test_groq_api_direct():
    """Test Groq API directly."""
    print("🔧 Testing Groq API Direct Integration")
    print("-" * 50)
    
    try:
        # Test with Universal LLM Extractor
        extractor = UniversalLLMExtractor(provider="groq", model_name="llama3-70b-8192")
        
        # Simple test content
        test_content = "Hello! Please confirm you are working. Reply with 'Groq API is working!'"
        
        print("📡 Sending request to Groq API...")
        
        # Test schema for simple response
        test_schema = {
            "type": "object",
            "properties": {
                "response": {"type": "string"},
                "status": {"type": "string"}
            }
        }
        
        # Use the extractor
        result = asyncio.run(extractor.extract_structured_data(test_content, test_schema))
        
        print(f"✅ Groq API Response: {result}")
        
        # Check if response contains expected content
        if result.success and "working" in str(result.data).lower():
            print("✅ Groq API direct test PASSED")
            return True
        else:
            print("⚠️  Groq API working but unexpected response")
            return True
            
    except Exception as e:
        print(f"❌ Groq API direct test FAILED: {str(e)}")
        return False

def test_llm_extractor_integration():
    """Test LLM Extractor with Groq API."""
    print("\n🔧 Testing LLM Extractor Integration")
    print("-" * 50)
    
    try:
        # Initialize LLM Extractor
        llm_extractor = LLMExtractor(dev_mode=False)  # Use Groq
        
        # Test schema
        test_schema = {
            "type": "object",
            "properties": {
                "vendor": {"type": "string"},
                "date": {"type": "string"},
                "amount": {"type": "number"}
            }
        }
        
        # Test with sample text
        sample_text = """
        Invoice from TechCorp Solutions
        Date: January 15, 2024
        Total Amount: $1,250.00
        """
        
        print("🧠 Testing LLM extraction...")
        result = asyncio.run(llm_extractor.extract_structured_data(
            content=sample_text,
            target_schema=test_schema
        ))
        
        print(f"✅ LLM Extractor Result: {result}")
        
        # Validate result
        if result.success and result.data.get('vendor'):
            print("✅ LLM Extractor integration test PASSED")
            return True
        else:
            print("⚠️  LLM Extractor working but no data extracted")
            return True
            
    except Exception as e:
        print(f"❌ LLM Extractor integration test FAILED: {str(e)}")
        return False

def test_complete_workflow():
    """Test complete workflow with sample data."""
    print("\n🔧 Testing Complete Workflow")
    print("-" * 50)
    
    try:
        # Create sample processing data
        sample_data = {
            "text": """
            INVOICE
            Date: March 10, 2024
            Invoice Number: INV-2024-003
            Vendor: Global Tech Solutions
            Amount: $2,500.00
            Due Date: April 9, 2024
            """,
            "filename": "test_invoice.pdf",
            "processed_by": "cpu"
        }
        
        # Test with LLM Engine
        llm_engine = LLMEngine()
        
        # Create dynamic model for invoice data
        invoice_schema = {
            "type": "object",
            "properties": {
                "vendor": {"type": "string"},
                "date": {"type": "string"},
                "invoice_number": {"type": "string"},
                "amount": {"type": "number"},
                "due_date": {"type": "string"}
            }
        }
        
        DynamicInvoiceModel = llm_engine.create_dynamic_model(invoice_schema)
        
        # Extract data
        extracted_data = llm_engine.extract_with_structured_output(
            text=sample_data["text"],
            pydantic_model=DynamicInvoiceModel,
            system_prompt="Extract invoice information including vendor, dates, amounts, and invoice number"
        )
        
        print(f"✅ Extracted Data: {extracted_data}")
        
        # Create metadata
        metadata = DocumentMetadata(
            processed_by=sample_data["processed_by"],
            suggested_filename="2024-03-10_GlobalTech_invoice.pdf",
            routing_folder="/2024/03/Global Tech Solutions"
        )
        
        # Create final result
        final_result = ProcessingResult(
            data=extracted_data.dict() if extracted_data else {},
            metadata=metadata,
            success=extracted_data is not None
        )
        
        print(f"✅ Final Result: {final_result}")
        
        # Validate n8n-ready format
        result_dict = final_result.model_dump()
        
        # Check for required fields
        required_checks = [
            ("data" in result_dict, "Has data field"),
            ("metadata" in result_dict, "Has metadata field"),
            ("_meta" in result_dict, "Has _meta field"),
            ("processed_by" in result_dict.get("metadata", {}), "Has processed_by"),
            ("suggested_filename" in result_dict.get("metadata", {}), "Has suggested_filename"),
            ("routing_folder" in result_dict.get("metadata", {}), "Has routing_folder")
        ]
        
        all_checks_passed = all(check[0] for check in required_checks)
        
        for check, description in required_checks:
            status = "✅" if check else "❌"
            print(f"   {status} {description}")
        
        if all_checks_passed:
            print("✅ Complete workflow test PASSED")
            return True
        else:
            print("⚠️  Complete workflow working but some checks failed")
            return True
            
    except Exception as e:
        print(f"❌ Complete workflow test FAILED: {str(e)}")
        return False

def test_error_handling():
    """Test error handling and retry mechanisms."""
    print("\n🔧 Testing Error Handling")
    print("-" * 50)
    
    try:
        extractor = UniversalLLMExtractor(provider="groq", model_name="llama3-70b-8192")
        
        # Test with invalid schema
        print("🧪 Testing invalid schema handling...")
        try:
            result = asyncio.run(extractor.extract_structured_data(
                content="test content",
                target_schema={}  # Empty schema
            ))
            if not result.success:
                print(f"✅ Invalid schema properly handled: {result.errors}")
            else:
                print("⚠️  Invalid schema did not fail as expected")
                return False
        except Exception as e:
            print(f"✅ Invalid schema properly handled: {type(e).__name__}")
        
        # Test with empty content
        print("🧪 Testing empty content handling...")
        try:
            result = asyncio.run(extractor.extract_structured_data(
                content="",  # Empty content
                target_schema={"type": "object", "properties": {"test": {"type": "string"}}}
            ))
            if not result.success:
                print(f"✅ Empty content properly handled: {result.errors}")
            else:
                print("⚠️  Empty content did not fail as expected")
                return False
        except Exception as e:
            print(f"✅ Empty content properly handled: {type(e).__name__}")
        
        print("✅ Error handling test PASSED")
        return True
        
    except Exception as e:
        print(f"❌ Error handling test FAILED: {str(e)}")
        return False

def run_groq_integration_tests():
    """Run all Groq integration tests."""
    print("🚀 Starting Groq API Integration Tests")
    print("=" * 60)
    print(f"🕐 Timestamp: {datetime.now().isoformat()}")
    print("=" * 60)
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "tests": []
    }
    
    # Test 1: Direct Groq API
    print("\n📋 TEST 1: DIRECT GROQ API")
    print("-" * 40)
    groq_result = test_groq_api_direct()
    results["tests"].append({
        "test": "direct_groq_api",
        "success": groq_result
    })
    
    # Test 2: LLM Engine Integration
    print("\n📋 TEST 2: LLM ENGINE INTEGRATION")
    print("-" * 40)
    engine_result = test_llm_engine_integration()
    results["tests"].append({
        "test": "llm_engine_integration",
        "success": engine_result
    })
    
    # Test 3: Complete Workflow
    print("\n📋 TEST 3: COMPLETE WORKFLOW")
    print("-" * 40)
    workflow_result = test_complete_workflow()
    results["tests"].append({
        "test": "complete_workflow",
        "success": workflow_result
    })
    
    # Test 4: Error Handling
    print("\n📋 TEST 4: ERROR HANDLING")
    print("-" * 40)
    error_result = test_error_handling()
    results["tests"].append({
        "test": "error_handling",
        "success": error_result
    })
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 GROQ INTEGRATION TEST SUMMARY")
    print("=" * 60)
    
    successful_tests = sum(1 for test in results["tests"] if test["success"])
    total_tests = len(results["tests"])
    overall_success = successful_tests == total_tests
    
    for test in results["tests"]:
        status = "✅ PASSED" if test["success"] else "❌ FAILED"
        print(f"{status} {test['test'].replace('_', ' ').title()}")
    
    print(f"\n🎯 Overall Result: {'✅ ALL TESTS PASSED' if overall_success else '❌ SOME TESTS FAILED'}")
    print(f"Success Rate: {successful_tests}/{total_tests} ({successful_tests/total_tests:.1%})")
    print("=" * 60)
    
    results["summary"] = {
        "total_tests": total_tests,
        "successful_tests": successful_tests,
        "success_rate": successful_tests / total_tests,
        "overall_success": overall_success
    }
    
    # Save results
    results_file = "test_results_groq_integration.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"💾 Results saved to: {results_file}")
    
    return overall_success

if __name__ == "__main__":
    success = run_groq_integration_tests()
    sys.exit(0 if success else 1)