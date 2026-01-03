"""
Test suite for Docuflow Apify Actor with DeepInfra and Ollama integration
Tests the complete pipeline: document processing -> OCR -> JSON formatting -> validation
"""
import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from pydantic import ValidationError

# Import the functions we need to test
from main import process_document, extract_with_gliner, call_deepinfra_ocr, call_ollama_json_formatting


@pytest.fixture
def sample_schema():
    return {
        "fields": {
            "vendor_name": {"type": "string", "description": "Name of the vendor"},
            "invoice_number": {"type": "string", "description": "Invoice number"},
            "total_amount": {"type": "number", "description": "Total amount"},
            "date": {"type": "string", "format": "date", "description": "Invoice date"}
        }
    }


@pytest.mark.asyncio
async def test_process_document_with_valid_input(sample_schema):
    """Test the complete document processing pipeline with valid input."""
    with patch('main.call_deepinfra_ocr') as mock_ocr, \
         patch('main.call_deepinfra_json_formatting') as mock_llm, \
         patch('main.extract_with_gliner') as mock_gliner:
        
        # Mock GLiNER to return partial data
        mock_gliner.return_value = {
            "vendor_name": "ACME Corp",
            "invoice_number": "INV-2024-001"
        }
        
        # Mock OCR to return sample text
        mock_ocr.return_value = "Invoice from: ACME Corp\nInvoice #: INV-2024-001\nDate: 2024-01-15\nTotal: $1,250.50"
        
        # Mock LLM to return remaining fields
        mock_llm.return_value = {
            "total_amount": 1250.50,
            "date": "2024-01-15"
        }
        
        result = await process_document(
            doc_url="https://example.com/invoice.pdf",
            schema=sample_schema
        )
        
        assert result.status == "success"
        assert result.extracted_data["vendor_name"] == "ACME Corp"
        assert result.extracted_data["total_amount"] == 1250.50
        assert result.processing_method in ["gliner_extraction", "deepinfra_json", "deepinfra_json_fallback"]


@pytest.mark.asyncio 
async def test_process_document_with_invalid_schema(sample_schema):
    """Test processing with schema that should fail validation."""
    with patch('main.call_deepinfra_ocr') as mock_ocr, \
         patch('main.call_deepinfra_json_formatting') as mock_llm, \
         patch('main.extract_with_gliner') as mock_gliner:
        
        mock_ocr.return_value = "Some text"
        mock_gliner.return_value = {}  # No entities extracted
        # Return data that violates schema requirements
        mock_llm.return_value = {"some_other_field": "value"}
        
        result = await process_document(
            doc_url="https://example.com/invoice.pdf", 
            schema=sample_schema
        )
        
        # Even with mismatched data, it should still return a result
        assert result.doc_url == "https://example.com/invoice.pdf"
        assert result.status in ["success", "partial"]


def test_gliner_extraction_function():
    """Test GLiNER extraction function directly."""
    # This would require GLiNER to be installed
    # For now, we'll test the function signature and basic behavior
    schema = {
        "fields": {
            "name": {"type": "string"},
            "age": {"type": "number"}
        }
    }
    
    # Mock text content
    text = "John Smith is 30 years old."
    
    # If GLiNER is available, test actual extraction
    try:
        from gliner import GLiNER
        # Actual GLiNER test would go here
        pass
    except ImportError:
        # If GLiNER is not available, verify the function handles it gracefully
        with patch('main.GLINER_AVAILABLE', False):
            with pytest.raises(RuntimeError, match="GLiNER not available"):
                asyncio.run(extract_with_gliner(text, schema))


@pytest.mark.asyncio
async def test_process_document_error_handling():
    """Test error handling in document processing."""
    with patch('main.call_deepinfra_ocr', side_effect=Exception("OCR failed")):
        
        schema = {
            "fields": {
                "vendor_name": {"type": "string"}
            }
        }
        
        result = await process_document(
            doc_url="https://example.com/bad_document.jpg",
            schema=schema
        )
        
        assert result.status == "error"
        assert "OCR failed" in result.errors[0]


@pytest.mark.asyncio
async def test_process_document_local_models():
    """Test processing with local models enabled."""
    with patch('main.USE_LOCAL_MODELS', True), \
         patch('main.call_ollama_ocr') as mock_ollama_ocr, \
         patch('main.call_ollama_json_formatting') as mock_ollama_llm:
        
        mock_ollama_ocr.return_value = "Extracted text from document"
        mock_ollama_llm.return_value = {"vendor_name": "Test Vendor", "amount": 100.0}
        
        schema = {
            "fields": {
                "vendor_name": {"type": "string"},
                "amount": {"type": "number"}
            }
        }
        
        result = await process_document(
            doc_url="https://example.com/document.jpg",
            schema=schema
        )
        
        assert result.status == "success"
        assert result.processing_method in ["ollama_ocr", "ollama_json"]
        assert result.extracted_data["vendor_name"] == "Test Vendor"


@pytest.mark.asyncio
async def test_process_document_with_pdf():
    """Test processing a PDF document."""
    with patch('main.httpx.AsyncClient') as mock_client_class, \
         patch('main.extract_with_gliner') as mock_gliner, \
         patch('main.call_deepinfra_json_formatting') as mock_llm:
        
        # Mock the async client and its response
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.text = "Sample PDF text content"
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        
        mock_client_class.__aenter__.return_value = mock_client
        mock_gliner.return_value = {"vendor_name": "PDF Vendor"}
        mock_llm.return_value = {"amount": 250.75}
        
        schema = {
            "fields": {
                "vendor_name": {"type": "string"},
                "amount": {"type": "number"}
            }
        }
        
        result = await process_document(
            doc_url="https://example.com/document.pdf",
            schema=schema
        )
        
        assert result.status == "success"
        assert result.extracted_data["vendor_name"] == "PDF Vendor"


@pytest.mark.asyncio
async def test_deepinfra_json_formatting():
    """Test DeepInfra JSON formatting function."""
    with patch('main.httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "choices": [
                {"message": {"content": '{"vendor_name": "Test Corp", "total": 500.0}'}}
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_class.__aenter__.return_value = mock_client
        
        schema = {
            "fields": {
                "vendor_name": {"type": "string"},
                "total": {"type": "number"}
            }
        }
        
        result = await call_deepinfra_json_formatting(
            client=mock_client,
            text="Invoice from Test Corp for $500.00",
            schema=schema,
            model="test-model"
        )
        
        assert result["vendor_name"] == "Test Corp"
        assert result["total"] == 500.0


@pytest.mark.asyncio
async def test_ollama_json_formatting():
    """Test Ollama JSON formatting function."""
    with patch('main.httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "message": {"content": '{"customer": "John Doe", "amount": 123.45}'}
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_class.__aenter__.return_value = mock_client
        
        schema = {
            "fields": {
                "customer": {"type": "string"},
                "amount": {"type": "number"}
            }
        }
        
        result = await call_ollama_json_formatting(
            client=mock_client,
            text="Receipt for John Doe: $123.45",
            schema=schema
        )
        
        assert result["customer"] == "John Doe"
        assert result["amount"] == 123.45


def test_schema_validation():
    """Test schema validation with Pydantic."""
    from pydantic import create_model
    
    # Test creating a dynamic model from schema
    fields = {
        "name": (str, ...),
        "age": (int, ...)
    }
    
    DynamicModel = create_model("DynamicSchema", **fields)
    
    # Valid data
    valid_data = {"name": "John", "age": 30}
    model_instance = DynamicModel(**valid_data)
    assert model_instance.name == "John"
    assert model_instance.age == 30
    
    # Invalid data (missing required field)
    try:
        invalid_data = {"name": "Jane"}  # Missing age
        DynamicModel(**invalid_data)
        assert False, "Should have raised ValidationError"
    except ValidationError:
        pass  # Expected


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])