#!/usr/bin/env python3
"""
Comprehensive test suite for DocuFlow Headless v2 transformation.
Tests all components against the master checklist requirements.
"""

import asyncio
import json
import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime
import base64

# Import v2 components
from src.models import ProcessingInput, FileInput, ProcessingOutput, create_dynamic_schema
from src.engine.intelligent_ingest import IntelligentIngestionEngine
from src.engine.engine_cpu import CPUEngine
from src.engine.engine_gpu import GPUEngine
from src.engine.schema_builder import SchemaBuilder
from src.engine.output_formatter import OutputFormatter
from src.main import main


class TestV2Transformation:
    """Comprehensive test suite for DocuFlow Headless v2."""

    @pytest.fixture
    def sample_input_schema(self):
        """Sample input schema for testing."""
        return {
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
                "total_amount": "number",
                "items": "array"
            }
        }

    @pytest.fixture
    def sample_pdf_content(self):
        """Sample PDF content for testing."""
        return b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
>>
endobj
4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
100 700 Td
(Invoice #12345) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f 
0000000010 00000 n 
0000000053 00000 n 
0000000100 00000 n 
0000000178 00000 n 
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
270
%%EOF"""

    def test_input_schema_validation(self, sample_input_schema):
        """Test V2 input schema validation."""
        schema = V2InputSchema(**sample_input_schema)
        
        assert len(schema.files) == 1
        assert schema.files[0].filename == "sample.pdf"
        assert schema.files[0].url == "https://example.com/sample.pdf"
        assert "Invoice" in schema.filter_keywords
        assert "vendor_name" in schema.schema

    def test_dynamic_model_creation(self, sample_input_schema):
        """Test dynamic Pydantic model creation with all Optional fields."""
        user_schema = sample_input_schema["schema"]
        DynamicModel = create_dynamic_model(user_schema)
        
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

    @pytest.mark.asyncio
    async def test_intelligent_ingestion_engine(self, sample_input_schema, sample_pdf_content):
        """Test intelligent ingestion with AGB filtering."""
        engine = IntelligentIngestionEngine()
        
        # Create temporary PDF file
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(sample_pdf_content)
            temp_path = f.name
        
        try:
            # Mock file download
            with patch('src.engine.intelligent_ingest.download_file') as mock_download:
                mock_download.return_value = temp_path
                
                # Test with matching keyword
                result = await engine.process_files(sample_input_schema["files"], ["Invoice"])
                
                assert len(result) == 1
                assert result[0]["filename"] == "sample.pdf"
                assert result[0]["route"] in ["CPU_FAST", "GPU_VISION"]
                assert "text_density" in result[0]
                
                # Test with non-matching keyword
                result = await engine.process_files(sample_input_schema["files"], ["Receipt"])
                assert len(result) == 0  # Should be filtered out
                
        finally:
            os.unlink(temp_path)

    def test_file_compression_logic(self):
        """Test file compression for large files."""
        engine = IntelligentIngestionEngine()
        
        # Test PDF compression threshold
        assert engine.should_compress_pdf(15 * 1024 * 1024) is True  # 15MB
        assert engine.should_compress_pdf(5 * 1024 * 1024) is False  # 5MB
        
        # Test image compression threshold
        assert engine.should_compress_image(6 * 1024 * 1024) is True  # 6MB
        assert engine.should_compress_image(3 * 1024 * 1024) is False  # 3MB

    @pytest.mark.asyncio
    async def test_cpu_engine_extraction(self, sample_pdf_content):
        """Test CPU engine with PyMuPDF extraction."""
        engine = CPUEngine()
        
        # Create temporary PDF file
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(sample_pdf_content)
            temp_path = f.name
        
        try:
            result = await engine.extract_text(temp_path)
            
            assert "Invoice" in result
            assert isinstance(result, str)
            assert len(result) > 0
            
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_gpu_engine_extraction(self):
        """Test GPU engine with external API calls."""
        engine = GPUEngine()
        
        with patch('src.engine.engine_gpu.requests.post') as mock_post:
            mock_post.return_value.json.return_value = {
                "text": "Extracted text from GPU",
                "confidence": 0.95
            }
            mock_post.return_value.raise_for_status = Mock()
            
            result = await engine.extract_text("https://example.com/test.pdf")
            
            assert result == "Extracted text from GPU"
            mock_post.assert_called_once()

    def test_routing_decision_logic(self):
        """Test routing decision based on text density."""
        engine = IntelligentIngestionEngine()
        
        # High text density -> CPU_FAST
        assert engine.calculate_route(has_text_layer=True, text_density=100) == "CPU_FAST"
        
        # Low text density -> GPU_VISION
        assert engine.calculate_route(has_text_layer=False, text_density=10) == "GPU_VISION"
        
        # Medium text density with text layer -> CPU_FAST
        assert engine.calculate_route(has_text_layer=True, text_density=60) == "CPU_FAST"

    def test_output_formatter_metadata(self, sample_input_schema):
        """Test output formatter with metadata generation."""
        formatter = OutputFormatter()
        
        extracted_data = {
            "vendor_name": "Test Corp",
            "invoice_date": "2024-01-15",
            "total_amount": 150.50
        }
        
        result = formatter.format_output(
            extracted_data, 
            "CPU_FAST", 
            "sample.pdf",
            sample_input_schema["schema"]
        )
        
        assert result["vendor_name"] == "Test Corp"
        assert result["invoice_date"] == "2024-01-15"
        assert result["total_amount"] == 150.50
        
        # Check metadata
        assert result["_meta"]["processed_by"] == "CPU_FAST"
        assert result["_meta"]["suggested_filename"] == "2024-01-15_Test Corp_Invoice.pdf"
        assert result["_meta"]["routing_folder"] == "/2024/01/Test Corp"

    def test_iso8601_date_conversion(self):
        """Test ISO8601 date conversion in output formatter."""
        formatter = OutputFormatter()
        
        test_cases = [
            ("15.01.2024", "2024-01-15"),
            ("01/15/2024", "2024-01-15"),
            ("15-Jan-2024", "2024-01-15"),
            ("January 15, 2024", "2024-01-15"),
        ]
        
        for input_date, expected_output in test_cases:
            result = formatter.convert_to_iso8601(input_date)
            assert result == expected_output

    @pytest.mark.asyncio
    async def test_end_to_end_workflow(self, sample_input_schema, sample_pdf_content):
        """Test complete end-to-end workflow."""
        # Create temporary PDF file
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(sample_pdf_content)
            temp_path = f.name
        
        try:
            # Mock file operations and external calls
            with patch('src.engine.intelligent_ingest.download_file') as mock_download, \
                 patch('src.engine.engine_cpu.CPUEngine.extract_text') as mock_cpu, \
                 patch('src.engine.llm.ChatGroq') as mock_groq:
                
                mock_download.return_value = temp_path
                mock_cpu.return_value = "Invoice #12345 from Test Corp dated 15.01.2024 for $150.50"
                
                # Mock LLM response
                mock_llm_instance = Mock()
                mock_llm_instance.with_structured_output.return_value.ainvoke = AsyncMock(
                    return_value=Mock(
                        vendor_name="Test Corp",
                        invoice_date="2024-01-15",
                        total_amount=150.50,
                        items=None
                    )
                )
                mock_groq.return_value = mock_llm_instance
                
                # Run main workflow
                result = await main(sample_input_schema)
                
                assert len(result) == 1
                assert result[0]["vendor_name"] == "Test Corp"
                assert result[0]["invoice_date"] == "2024-01-15"
                assert result[0]["total_amount"] == 150.50
                assert result[0]["_meta"]["processed_by"] in ["cpu", "gpu"]
                
        finally:
            os.unlink(temp_path)

    def test_error_handling(self):
        """Test error handling and logging."""
        engine = IntelligentIngestionEngine()
        
        # Test with invalid file
        with pytest.raises(Exception):
            asyncio.run(engine.process_files([{"url": "invalid://file.pdf"}], []))

    def test_retry_mechanism(self):
        """Test retry mechanism for GPU engine."""
        engine = GPUEngine()
        
        with patch('src.engine.engine_gpu.requests.post') as mock_post:
            # First two calls fail, third succeeds
            mock_post.side_effect = [
                Exception("Network error"),
                Exception("Timeout"),
                Mock(json=lambda: {"text": "Success"}, raise_for_status=Mock())
            ]
            
            with patch('tenacity.AsyncRetrying.wait', return_value=AsyncMock()):
                result = asyncio.run(engine.extract_text_with_retry("test.pdf"))
                assert result == "Success"
                assert mock_post.call_count == 3

    def test_large_file_handling(self):
        """Test handling of large files."""
        engine = IntelligentIngestionEngine()
        
        # Mock large file
        large_content = b"A" * (20 * 1024 * 1024)  # 20MB
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(large_content)
            temp_path = f.name
        
        try:
            # Should trigger compression
            assert engine.should_compress_pdf(os.path.getsize(temp_path)) is True
            
        finally:
            os.unlink(temp_path)

    def test_concurrent_processing(self):
        """Test concurrent processing of multiple files."""
        engine = IntelligentIngestionEngine()
        
        # Mock multiple files
        files = [
            {"url": f"https://example.com/file{i}.pdf", "filename": f"file{i}.pdf"}
            for i in range(5)
        ]
        
        with patch.object(engine, 'process_single_file', new_callable=AsyncMock) as mock_process:
            mock_process.return_value = {"processed": True}
            
            results = asyncio.run(engine.process_files(files, []))
            assert len(results) == 5
            assert mock_process.call_count == 5

    def test_schema_validation_edge_cases(self):
        """Test schema validation with edge cases."""
        # Empty schema
        with pytest.raises(ValueError):
            ProcessingInput(files=[], filter_keywords=[], schema={})
        
        # Invalid file format
        with pytest.raises(ValueError):
            ProcessingInput(files=[{"invalid": "data"}], filter_keywords=[], schema={})
        
        # Valid minimal schema
        schema = ProcessingInput(
            files=[{"url": "test.pdf", "filename": "test.pdf", "base64": ""}],
            filter_keywords=[],
            schema={"test": "string"}
        )
        assert len(schema.files) == 1


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])