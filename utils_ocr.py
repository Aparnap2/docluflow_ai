"""
Document OCR utilities for PropFlow Agent.
Docling first, fallback to DeepSeek OCR for scanned PDFs.
"""
import tempfile
import os
import httpx
from typing import Optional
from docling.document_converter import DocumentConverter
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.base_models import InputFormat
from docling.document_converter import PdfFormatOption
from utils_security import (
    validate_document_url,
    validate_and_prepare_document,
    truncate_text
)

async def run_docling(doc_url: Optional[str] = None, doc_bytes: Optional[bytes] = None, use_vlm_for_tables: bool = False) -> str:
    """
    Convert document to markdown using Docling (local OCR).
    """
    if doc_bytes is None:
        if doc_url is None:
            raise ValueError("Either doc_url or doc_bytes must be provided")

        # Validate URL before fetching
        url_error = validate_document_url(doc_url)
        if url_error:
            raise ValueError(f"Invalid document URL: {url_error.get('error')}")

        # Fetch the document
        if doc_url.startswith('file://'):
            local_path = doc_url.replace('file://', '', 1)
            if not os.path.exists(local_path):
                raise ValueError(f"Local file not found: {local_path}")
            with open(local_path, 'rb') as f:
                doc_bytes = f.read()
        else:
            async with httpx.AsyncClient(timeout=300) as client:
                response = await client.get(doc_url, follow_redirects=True)
                response.raise_for_status()
                doc_bytes = response.content

    hint_url = doc_url or "uploaded_document.pdf"
    validation_result = validate_and_prepare_document(hint_url, doc_bytes)

    if validation_result.get("error"):
        error_info = validation_result["error"]
        raise ValueError(f"Document validation failed: {error_info.get('error')}")

    temp_pdf_path = validation_result["file_path"]
    file_size_mb = validation_result["file_size_mb"]

    if validation_result.get("was_compressed"):
        print(f"Document compressed from {file_size_mb:.1f}MB")

    try:
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_table_structure = True

        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )

        result = converter.convert(temp_pdf_path)
        markdown_text = result.document.export_to_markdown()

        # Check if output is empty or too short (might be scanned)
        if len(markdown_text.strip()) < 50:
            raise ValueError("Docling produced minimal output - likely scanned PDF")

        return markdown_text

    except Exception as e:
        # Check if it's a "minimal output" error - trigger fallback
        error_msg = str(e).lower()
        if "minimal output" in error_msg or "empty" in error_msg or "scanned" in error_msg:
            raise ValueError(f"Scanned PDF detected: {e}")
        else:
            raise


async def run_deepseek_ocr(doc_url: Optional[str] = None, doc_bytes: Optional[bytes] = None) -> str:
    """
    Convert document to markdown using DeepSeek OCR via Ollama.
    Fallback for scanned PDFs.
    """
    import base64
    from langchain_ollama import OllamaLLM

    if doc_bytes is None:
        if doc_url is None:
            raise ValueError("Either doc_url or doc_bytes must be provided")

        if doc_url.startswith('file://'):
            local_path = doc_url.replace('file://', '', 1)
            with open(local_path, 'rb') as f:
                doc_bytes = f.read()
        else:
            async with httpx.AsyncClient(timeout=300) as client:
                response = await client.get(doc_url, follow_redirects=True)
                response.raise_for_status()
                doc_bytes = response.content

    doc_base64 = base64.b64encode(doc_bytes).decode('utf-8')
    llm = OllamaLLM(model="deepseek-ocr:3b", temperature=0)

    prompt = """Extract ALL text from this document as clean markdown.
Include all headings, tables, paragraphs, and list items."""

    image_data_uri = f"data:application/pdf;base64,{doc_base64}"

    try:
        result = llm.invoke([{"role": "user", "content": prompt, "images": [image_data_uri]}])
        return result if result else ""
    except Exception as e:
        raise Exception(f"DeepSeek OCR failed: {str(e)}")


async def run_ocr(doc_url: Optional[str] = None, doc_bytes: Optional[bytes] = None, use_deepseek: bool = False) -> str:
    """
    Main OCR function.

    If use_deepseek=True: Use DeepSeek OCR directly (for scanned PDFs)
    Otherwise: Try Docling first, fallback to DeepSeek OCR if minimal output
    """
    if use_deepseek:
        return await run_deepseek_ocr(doc_url, doc_bytes)

    # Try Docling first
    try:
        return await run_docling(doc_url, doc_bytes)
    except ValueError as e:
        error_msg = str(e).lower()
        if "scanned pdf" in error_msg or "minimal output" in error_msg:
            print("Docling produced minimal output, falling back to DeepSeek OCR...")
            return await run_deepseek_ocr(doc_url, doc_bytes)
        raise
