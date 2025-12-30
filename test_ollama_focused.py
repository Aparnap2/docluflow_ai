#!/usr/bin/env python3
"""Focused test for Ollama models with CPU-optimized settings."""

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Dict, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from engine.llm import extract_structured_data, LLMExtractor
from engine.ocr import process_document, is_ocr_recommended
from engine.ingest import determine_input_type, is_garbage
from engine.validator import validate_extraction
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

async def test_ollama_models():
    """Test Ollama models with CPU-optimized settings."""
    print("🧪 Testing Ollama Models with CPU Optimization")
    print("=" * 60)
    
    # Test 1: Small model for quick validation
    print("\n1️⃣ Testing granite4:3b model (fastest)")
    try:
        extractor = LLMExtractor(model_name="granite4:3b", dev_mode=True)
        
        # Simple extraction test
        test_content = """
        Company: TechCorp Inc.
        Revenue: $1,250,000
        Employees: 45
        Founded: 2018
        """
        
        schema = {
            "company_name": "string",
            "revenue": "number",
            "employee_count": "number",
            "founded_year": "number"
        }
        
        print("   Extracting from simple business data...")
        result = await extractor.extract_structured_data(test_content, schema)
        
        print(f"   ✅ Success: {result.success}")
        print(f"   📊 Confidence: {result.confidence:.2f}")
        print(f"   📋 Extracted data: {json.dumps(result.data, indent=2)}")
        
    except Exception as e:
        print(f"   ❌ granite4:3b failed: {e}")

    # Test 2: OCR recommendation
    print("\n2️⃣ Testing OCR recommendation logic")
    try:
        # Test with different content types
        test_cases = [
            ("Clear digital text", "This is a well-formatted digital document with clear text."),
            ("Scanned document simulation", "This text appears to be from a scanned document with some OCR errors and formatting issues."),
            ("Complex layout", "Document with tables, images, and complex formatting that might need advanced OCR.")
        ]
        
        for name, content in test_cases:
            recommendation = is_ocr_recommended("test.pdf", "pdf")  # Simulate PDF document
            print(f"   {name}: GPU OCR recommended = {recommendation}")
            
    except Exception as e:
        print(f"   ❌ OCR recommendation failed: {e}")

    # Test 3: Document type detection
    print("\n3️⃣ Testing document type detection")
    test_urls = [
        "https://example.com/page.html",
        "https://example.com/document.pdf",
        "https://example.com/image.jpg",
        "https://example.com/photo.png"
    ]
    
    for url in test_urls:
        try:
            doc_type = determine_input_type(url)
            print(f"   {url} -> {doc_type}")
        except Exception as e:
            print(f"   {url} -> error: {e}")

    # Test 4: Content quality detection
    print("\n4️⃣ Testing content quality detection")
    test_content = [
        ("Good content", "This is a substantial piece of content with multiple sentences and meaningful information that should pass quality checks."),
        ("Login wall", "Please login to continue. Enter your username and password to access this content."),
        ("Empty content", ""),
        ("Short content", "Hi")
    ]
    
    for name, content in test_content:
        is_bad = is_garbage(content)
        print(f"   {name}: {'❌ garbage' if is_bad else '✅ good'}")

    # Test 5: Validation with simple data
    print("\n5️⃣ Testing data validation")
    try:
        schema = {
            "name": "string",
            "age": "number",
            "active": "boolean"
        }
        
        test_data = {
            "name": "John Doe",
            "age": 30,
            "active": True
        }
        
        result = validate_extraction(test_data, schema)
        print(f"   ✅ Validation: {result.is_valid}")
        print(f"   📊 Errors: {len(result.errors)}")
        print(f"   ⚠️  Warnings: {len(result.warnings)}")
        
    except Exception as e:
        print(f"   ❌ Validation failed: {e}")

    print("\n" + "=" * 60)
    print("✅ Ollama-focused tests completed!")
    print("Note: Some network-dependent tests may fail due to connectivity issues.")

if __name__ == "__main__":
    asyncio.run(test_ollama_models())