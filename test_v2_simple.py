#!/usr/bin/env python3
"""
Simple test suite for DocuFlow Headless v2 transformation.
Tests core functionality without complex dependencies.
"""

import pytest
from src.models import ProcessingInput, FileInput, create_dynamic_schema


def test_input_schema_validation():
    """Test V2 input schema validation."""
    sample_input = {
        "files": [
            {
                "url": "https://example.com/sample.pdf",
                "filename": "sample.pdf",
                "base64": ""
            }
        ],
        "filter_keywords": ["Invoice", "Receipt"],
        "schema": {
            "vendor_name": "string",
            "invoice_date": "string",
            "total_amount": "number"
        }
    }
    
    schema = ProcessingInput(**sample_input)
    
    assert len(schema.files) == 1
    assert schema.files[0].filename == "sample.pdf"
    assert schema.files[0].url == "https://example.com/sample.pdf"
    assert "Invoice" in schema.filter_keywords
    assert "vendor_name" in schema.schema


def test_dynamic_model_creation():
    """Test dynamic Pydantic model creation with all Optional fields."""
    user_schema = {
        "vendor_name": "string",
        "invoice_date": "string", 
        "total_amount": "number",
        "items": "array"
    }
    DynamicModel = create_dynamic_schema(user_schema)
    
    # Test model instantiation with no data
    instance = DynamicModel()
    assert instance.vendor_name is None
    assert instance.invoice_date is None
    assert instance.total_amount is None
    assert instance.items is None
    
    # Test model instantiation with partial data
    instance = DynamicModel(vendor_name="Test Corp")
    assert instance.vendor_name == "Test Corp"
    assert instance.invoice_date is None


def test_file_input_validation():
    """Test FileInput validation."""
    # Valid file input
    file_input = FileInput(url="https://example.com/test.pdf", filename="test.pdf")
    assert file_input.url == "https://example.com/test.pdf"
    assert file_input.filename == "test.pdf"
    
    # Valid base64 input
    file_input = FileInput(base64="dGVzdA==", filename="test.pdf")
    assert file_input.base64 == "dGVzdA=="
    assert file_input.filename == "test.pdf"


def test_schema_validation_edge_cases():
    """Test schema validation with edge cases."""
    # Valid minimal schema
    schema = ProcessingInput(
        files=[{"url": "test.pdf", "filename": "test.pdf", "base64": ""}],
        filter_keywords=[],
        schema={"test": "string"}
    )
    assert len(schema.files) == 1


if __name__ == "__main__":
    test_input_schema_validation()
    test_dynamic_model_creation()
    test_file_input_validation()
    test_schema_validation_edge_cases()
    print("All simple tests passed!")