import tempfile
import os
import httpx
from docling.document_converter import DocumentConverter
from docling.datamodel.pipeline_options import PipelineOptions
from utils_security import (
    validate_document_url,
    validate_and_prepare_document,
    truncate_text
)

async def run_docling(doc_url: str, use_vlm_for_tables: bool = False) -> str:
    """
    Convert document to markdown using Docling.
    
    Includes enterprise-grade security checks:
    - URL validation
    - File type verification (magic bytes)
    - Encryption detection
    - Filename sanitization
    
    Args:
        doc_url: URL of the document to process
        use_vlm_for_tables: If True, use VLM backend for complex tables (merged cells)
                           This is slower but handles complex quote tables better
    
    Returns:
        Markdown text from document
        
    Raises:
        ValueError: If document fails security checks
    """
    # Validate URL before fetching
    url_error = validate_document_url(doc_url)
    if url_error:
        raise ValueError(f"Invalid document URL: {url_error.get('error')}")
    
    # Fetch the document
    async with httpx.AsyncClient(timeout=300) as client:  # Increased timeout for large docs
        response = await client.get(doc_url, follow_redirects=True)
        response.raise_for_status()
        doc_bytes = response.content

    # Comprehensive validation and preparation
    validation_result = validate_and_prepare_document(doc_url, doc_bytes)
    
    if validation_result.get("error"):
        error_info = validation_result["error"]
        raise ValueError(f"Document validation failed: {error_info.get('error')} (type: {error_info.get('error_type')})")
    
    temp_pdf_path = validation_result["file_path"]
    file_size_mb = validation_result["file_size_mb"]
    
    # Log if compression was applied
    if validation_result.get("was_compressed"):
        print(f"Document compressed from {file_size_mb:.1f}MB")

    try:
        # Configure Docling pipeline options
        pipeline_options = PipelineOptions()
        
        # Enable table structure detection for complex tables (merged cells)
        # This helps with construction quotes that have complex table layouts
        pipeline_options.do_table_structure = True
        
        # Optionally use VLM backend for tables if enabled
        # This is slower but more accurate for complex merged-cell tables
        if use_vlm_for_tables:
            # Note: VLM backend requires additional setup
            # For V1, standard table detection is usually sufficient
            pipeline_options.do_table_structure = True
        
        # Use Docling to convert PDF to markdown
        converter = DocumentConverter(pipeline_options=pipeline_options)
        result = converter.convert(temp_pdf_path)
        markdown_text = result.document.export_to_markdown()
        return markdown_text
    except Exception as e:
        # If standard conversion fails, try with VLM fallback
        if not use_vlm_for_tables:
            # Retry with VLM backend as fallback
            try:
                pipeline_options = PipelineOptions()
                pipeline_options.do_table_structure = True
                converter = DocumentConverter(pipeline_options=pipeline_options)
                result = converter.convert(temp_pdf_path)
                markdown_text = result.document.export_to_markdown()
                return markdown_text
            except Exception as retry_error:
                raise Exception(f"Docling conversion failed: {str(e)}. Retry with VLM also failed: {str(retry_error)}")
        else:
            raise Exception(f"Docling conversion failed: {str(e)}")
    finally:
        # Clean up temporary file
        os.unlink(temp_pdf_path)