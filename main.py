"""
Apify Actor for Document Processing with DeepInfra and Local Ollama Models

This actor processes documents using:
- DeepSeek-OCR via DeepInfra for OCR (production)
- Local Ollama models for development
- JSON schema validation for structured output
"""
import os
import json
import asyncio
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
import tempfile

import httpx
from apify import Actor
from jsonschema import validate, ValidationError, Draft202012Validator
from openai import AsyncOpenAI
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter


# Configuration
DEEPINFRA_BASE_URL = os.getenv("DEEPINFRA_BASE_URL", "https://api.deepinfra.com/v1/openai").rstrip("/")
DEEPINFRA_TOKEN = os.getenv("DEEPINFRA_TOKEN", "")
LOCAL_OLLAMA_BASE_URL = os.getenv("LOCAL_OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1")  # For Docker

# Model configurations
OCR_MODEL = os.getenv("OCR_MODEL", "deepseek-ai/DeepSeek-OCR")
JSON_MODEL_PRIMARY = os.getenv("JSON_MODEL_PRIMARY", "google/gemma-3-12b-it")
JSON_MODEL_FALLBACK = os.getenv("JSON_MODEL_FALLBACK", "deepseek-ai/DeepSeek-V3.1")
LOCAL_OCR_MODEL = os.getenv("LOCAL_OCR_MODEL", "deepseek-ocr:3b")
LOCAL_JSON_MODEL = os.getenv("LOCAL_JSON_MODEL", "sam860/LFM2:2.6b")

# For development vs production
USE_LOCAL_MODELS = os.getenv("USE_LOCAL_MODELS", "false").lower() == "true"


async def validate_json_schema(data: Dict[str, Any], schema: Dict[str, Any]) -> Tuple[bool, list]:
    """
    Validate data against JSON schema.

    Args:
        data: Data to validate
        schema: JSON schema to validate against

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    try:
        Draft202012Validator.check_schema(schema)  # Validate the schema itself
        validator = Draft202012Validator(schema)
        errors = list(validator.iter_errors(data))
        error_messages = [str(error.message) for error in errors]
        return len(errors) == 0, error_messages
    except Exception as e:
        return False, [str(e)]


async def extract_with_ocr(doc_url: str, use_local_models: bool = False) -> str:
    """
    Extract text from document using OCR.

    Args:
        doc_url: URL to the document (image or PDF)
        use_local_models: Whether to use local Ollama models (for dev) or DeepInfra (for prod)

    Returns:
        Extracted text from the document
    """
    if use_local_models:
        # Use local Ollama model
        client = AsyncOpenAI(
            base_url=LOCAL_OLLAMA_BASE_URL,
            api_key="ollama"  # Ollama doesn't require a real API key
        )
        model_name = LOCAL_OCR_MODEL
    else:
        # Use DeepInfra
        if not DEEPINFRA_TOKEN:
            raise ValueError("DEEPINFRA_TOKEN is required for production mode")
        client = AsyncOpenAI(
            base_url=DEEPINFRA_BASE_URL,
            api_key=DEEPINFRA_TOKEN
        )
        model_name = OCR_MODEL

    # For image URLs, use multimodal OCR
    if any(doc_url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp', '.tiff', '.bmp']):
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract all text from this document. Return only the extracted text."},
                    {"type": "image_url", "image_url": {"url": doc_url}}
                ]
            }
        ]
    else:
        # For other files, we might need to download and process differently
        # For now, just pass the URL as text context
        messages = [
            {
                "role": "user",
                "content": f"Extract text from this document: {doc_url}"
            }
        ]

    try:
        response = await client.chat.completions.create(
            model=model_name,
            messages=messages,
            max_tokens=4000,
            temperature=0.0
        )
        return response.choices[0].message.content
    except Exception as e:
        raise Exception(f"OCR extraction failed: {str(e)}")


async def format_json_with_llm(text: str, schema: Dict[str, Any], use_local_models: bool = False) -> Dict[str, Any]:
    """
    Format extracted text into structured JSON using an LLM.

    Args:
        text: Extracted text from document
        schema: JSON schema that defines the expected output structure
        use_local_models: Whether to use local Ollama models (for dev) or DeepInfra (for prod)

    Returns:
        Structured JSON data matching the schema
    """
    # Create a system prompt that explains the schema
    schema_description = json.dumps(schema, indent=2)

    system_prompt = f"""You are a structured data extraction expert. Your task is to extract information from the provided text according to the given JSON schema.

JSON Schema:
{schema_description}

Instructions:
1. Extract only information that is explicitly present in the text
2. If information is not available, use null values
3. Follow the exact field names and types specified in the schema
4. Return only valid JSON that conforms to the schema
5. Do not add any additional fields not specified in the schema"""

    user_prompt = f"Extract structured data from the following text:\n\n{text}"

    if use_local_models:
        client = AsyncOpenAI(
            base_url=LOCAL_OLLAMA_BASE_URL,
            api_key="ollama"
        )
        model_name = LOCAL_JSON_MODEL
    else:
        if not DEEPINFRA_TOKEN:
            raise ValueError("DEEPINFRA_TOKEN is required for production mode")
        client = AsyncOpenAI(
            base_url=DEEPINFRA_BASE_URL,
            api_key=DEEPINFRA_TOKEN
        )
        model_name = JSON_MODEL_PRIMARY

    try:
        response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=2000,
            temperature=0.0,
            response_format={"type": "json_object"}  # Force JSON response
        )

        content = response.choices[0].message.content
        # Parse the JSON response
        result = json.loads(content)
        return result
    except json.JSONDecodeError:
        raise Exception(f"LLM returned invalid JSON: {content}")
    except Exception as e:
        # If primary model fails, try fallback model
        if not use_local_models and model_name == JSON_MODEL_PRIMARY:
            try:
                client = AsyncOpenAI(
                    base_url=DEEPINFRA_BASE_URL,
                    api_key=DEEPINFRA_TOKEN
                )

                response = await client.chat.completions.create(
                    model=JSON_MODEL_FALLBACK,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    max_tokens=2000,
                    temperature=0.0,
                    response_format={"type": "json_object"}
                )

                content = response.choices[0].message.content
                result = json.loads(content)
                return result
            except Exception as fallback_error:
                raise Exception(f"Primary and fallback LLMs failed: {str(e)}, {str(fallback_error)}")
        else:
            raise Exception(f"LLM formatting failed: {str(e)}")


async def process_pdf_with_docling(pdf_bytes: bytes) -> str:
    """
    Process PDF documents using Docling for structured text extraction.

    Args:
        pdf_bytes: PDF content as bytes

    Returns:
        Extracted text from PDF
    """
    # Create a temporary file for Docling to process
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf:
        temp_pdf.write(pdf_bytes)
        temp_pdf_path = temp_pdf.name

    try:
        # Configure Docling pipeline
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True  # Enable OCR for scanned PDFs
        pipeline_options.do_table_structure = True  # Extract table structures

        # Convert document
        converter = DocumentConverter(pipeline_options=pipeline_options)
        result = converter.convert(temp_pdf_path)

        # Export to markdown format
        markdown_text = result.document.export_to_markdown()
        return markdown_text
    finally:
        # Clean up temporary file
        Path(temp_pdf_path).unlink(missing_ok=True)


async def process_document(doc_url: str, schema: Dict[str, Any], use_local_models: bool = False) -> Dict[str, Any]:
    """
    Process a single document: OCR -> JSON formatting -> validation.

    Args:
        doc_url: URL to the document to process
        schema: JSON schema for the expected output
        use_local_models: Whether to use local models (dev) or DeepInfra (prod)

    Returns:
        Processing result with status, data, and validation info
    """
    result = {
        "doc_url": doc_url,
        "status": "processing",
        "data": None,
        "validation": {"passed": False, "errors": []},
        "processing_details": {
            "ocr_used": "local" if use_local_models else "deepinfra",
            "model_used": LOCAL_OCR_MODEL if use_local_models else OCR_MODEL
        }
    }

    try:
        # Determine if this is a PDF that should be processed with Docling first
        if doc_url.lower().endswith('.pdf'):
            # For PDFs, we might want to download and process with Docling first
            async with httpx.AsyncClient() as client:
                response = await client.get(doc_url)
                response.raise_for_status()
                pdf_bytes = response.content

            # Process PDF with Docling
            docling_text = await process_pdf_with_docling(pdf_bytes)
            extracted_text = docling_text
        else:
            # For images and other formats, use OCR directly
            extracted_text = await extract_with_ocr(doc_url, use_local_models)

        # Format the extracted text into structured JSON
        structured_data = await format_json_with_llm(extracted_text, schema, use_local_models)

        # Validate the result against the schema
        is_valid, validation_errors = await validate_json_schema(structured_data, schema)

        result["data"] = structured_data
        result["validation"] = {
            "passed": is_valid,
            "errors": validation_errors
        }

        if is_valid:
            result["status"] = "success"
        else:
            result["status"] = "validation_error"

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        result["data"] = None

    return result


async def main():
    """
    Main function for the Apify Actor.
    Processes input documents according to provided schema.
    """
    async with Actor:
        # Get input from Apify platform
        input_data = await Actor.get_input() or {}

        # Extract parameters from input
        doc_urls = input_data.get("docUrls", [])
        schema = input_data.get("jsonSchema", {})
        use_local = input_data.get("useLocalModels", USE_LOCAL_MODELS)

        if not doc_urls:
            raise ValueError("Input must include 'docUrls' parameter with document URLs")

        if not schema:
            raise ValueError("Input must include 'jsonSchema' parameter with the expected output schema")

        # Process each document
        for doc_url in doc_urls:
            try:
                # Process the document
                result = await process_document(doc_url, schema, use_local)

                # Push result to Apify dataset
                await Actor.push_data([result])

            except Exception as e:
                error_result = {
                    "doc_url": doc_url,
                    "status": "error",
                    "error": str(e),
                    "data": None
                }
                await Actor.push_data([error_result])


if __name__ == "__main__":
    asyncio.run(main())