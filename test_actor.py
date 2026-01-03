"""
Test suite for Docuflow Apify Actor
Tests the complete pipeline: document processing -> OCR -> JSON extraction -> validation
"""
import asyncio
import json
from unittest.mock import AsyncMock, patch
import pytest

from main import process_document, validate_json_schema, extract_with_ocr, format_json_with_llm


@pytest.fixture
def sample_schema():
    return {
        "type": "object",
        "properties": {
            "vendor_name": {"type": "string"},
            "invoice_number": {"type": "string"},
            "total": {"type": "number"},
            "date": {"type": "string", "format": "date"}
        },
        "required": ["vendor_name"]
    }


@pytest.mark.asyncio
async def test_process_document_with_valid_input(sample_schema):
    """Test the complete document processing pipeline with valid input."""
    with patch('main.extract_with_ocr') as mock_ocr, \
         patch('main.format_json_with_llm') as mock_llm:
        
        # Mock OCR to return sample text
        mock_ocr.return_value = "Invoice from: ACME Corp\\nInvoice #: INV-2024-001\\nDate: 2024-01-15\\nTotal: $1,250.50"
        
        # Mock LLM to return structured JSON
        mock_llm.return_value = {
            "vendor_name": "ACME Corp",
            "invoice_number": "INV-2024-001", 
            "total": 1250.50,
            "date": "2024-01-15"
        }
        
        result = await process_document(
            doc_url="https://example.com/invoice.pdf",
            schema=sample_schema,
            use_local_models=False  # Use DeepInfra in test
        )
        
        assert result["status"] == "success"
        assert "data" in result
        assert result["data"]["vendor_name"] == "ACME Corp"
        assert result["data"]["total"] == 1250.50


@pytest.mark.asyncio 
async def test_process_document_with_invalid_schema(sample_schema):
    """Test processing with schema that should fail validation."""
    with patch('main.extract_with_ocr') as mock_ocr, \
         patch('main.format_json_with_llm') as mock_llm:
        
        mock_ocr.return_value = "Some text"
        # Return data that violates schema (missing required field)
        mock_llm.return_value = {"some_other_field": "value"}
        
        result = await process_document(
            doc_url="https://example.com/invoice.pdf", 
            schema=sample_schema,
            use_local_models=False
        )
        
        assert result["status"] == "validation_error"
        assert "errors" in result


def test_json_schema_validation():
    """Test JSON schema validation function."""
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "number"}
        },
        "required": ["name"]
    }
    
    # Valid instance
    valid_data = {"name": "John", "age": 30}
    is_valid, errors = validate_json_schema(valid_data, schema)
    assert is_valid
    assert len(errors) == 0
    
    # Invalid instance (missing required field)
    invalid_data = {"age": 30}
    is_valid, errors = validate_json_schema(invalid_data, schema)
    assert not is_valid
    assert len(errors) > 0


@pytest.mark.asyncio
async def test_extract_with_ocr_local():
    """Test OCR extraction with local models."""
    # This would require local Ollama to be running
    # For now, we'll mock the OpenAI client
    with patch('openai.AsyncOpenAI') as mock_client:
        mock_instance = AsyncMock()
        mock_instance.chat.completions.create.return_value = AsyncMock()
        mock_instance.chat.completions.create.return_value.choices = [AsyncMock()]
        mock_instance.chat.completions.create.return_value.choices[0].message.content = "Extracted text from document"
        mock_client.return_value = mock_instance
        
        result = await extract_with_ocr(
            doc_url="https://example.com/image.jpg",
            use_local_models=True
        )
        
        assert "Extracted text from document" in result


@pytest.mark.asyncio
async def test_format_json_with_llm_local():
    """Test JSON formatting with local models."""
    with patch('openai.AsyncOpenAI') as mock_client:
        mock_instance = AsyncMock()
        mock_instance.chat.completions.create.return_value = AsyncMock()
        mock_instance.chat.completions.create.return_value.choices = [AsyncMock()]
        mock_instance.chat.completions.create.return_value.choices[0].message.content = '{"vendor_name": "Test Corp", "total": 100.0}'
        mock_client.return_value = mock_instance
        
        schema = {
            "type": "object",
            "properties": {
                "vendor_name": {"type": "string"},
                "total": {"type": "number"}
            }
        }
        
        result = await format_json_with_llm(
            text="Invoice from Test Corp for $100.00",
            schema=schema,
            use_local_models=True
        )
        
        assert result["vendor_name"] == "Test Corp"
        assert result["total"] == 100.0