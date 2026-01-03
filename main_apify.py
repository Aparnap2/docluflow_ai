"""
Apify Actor for Document Processing with DeepInfra and Ollama Integration

This actor processes documents using:
- DeepSeek-OCR via DeepInfra (production) or local Ollama (development) for OCR
- LFM2 (development) or Gemma (production) via DeepInfra for JSON formatting
- Docling Python library for PDF processing (not the LLM model)
- GLiNER for Tier 1 entity extraction (free & instant)
- JSON schema validation for structured output
"""
import os
import json
import asyncio
from typing import Dict, Any, Optional, List
import httpx
from apify import Actor
from pydantic import BaseModel, create_model, ValidationError
from docling.document_converter import DocumentConverter
from gliner import GLiNER


# Configuration
DEEPINFRA_BASE_URL = os.getenv("DEEPINFRA_BASE_URL", "https://api.deepinfra.com/v1/openai").rstrip("/")
DEEPINFRA_TOKEN = os.getenv("DEEPINFRA_TOKEN", "")

# DeepSeek OCR model for image processing (production)
DEEPINFRA_OCR_MODEL = os.getenv("DEEPINFRA_OCR_MODEL", "deepseek-ai/DeepSeek-OCR")

# JSON formatting models (production vs development)
DEEPINFRA_JSON_MODEL = os.getenv("DEEPINFRA_JSON_MODEL", "google/gemma-3-12b-it")

# Ollama endpoints for local development
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434").rstrip("/")
OLLAMA_OCR_MODEL = os.getenv("OLLAMA_OCR_MODEL", "deepseek-ocr:3b")
OLLAMA_JSON_MODEL = os.getenv("OLLAMA_JSON_MODEL", "sam860/LFM2:2.6b")

# Use local models for development
USE_LOCAL_MODELS = os.getenv("USE_LOCAL_MODELS", "false").lower() == "true"

# Max text length to prevent token blowups
MAX_TEXT_LENGTH = 30000


def detect_type(url: str) -> str:
    """Detect document type from URL."""
    u = url.lower()
    if any(u.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".tiff", ".bmp"]):
        return "image"
    if u.endswith(".pdf"):
        return "pdf"
    if u.endswith(".txt"):
        return "text"
    if u.startswith("http"):
        return "unknown"
    return "unknown"


def build_dynamic_model(schema: Dict[str, Any]) -> type[BaseModel]:
    """Build a dynamic Pydantic model from user-provided schema."""
    fields = schema.get("fields", {})
    if not fields:
        raise ValueError("Schema must include 'fields' object with field definitions")

    model_fields = {}
    for name, spec in fields.items():
        field_type = spec.get("type", "string")
        description = spec.get("description", f"Field {name}")

        # Map schema types to Python types
        type_map = {
            "string": (str, None),
            "number": (float, None),
            "integer": (int, None),
            "boolean": (bool, None),
            "array": (list, None),
            "object": (dict, None)
        }

        py_type = type_map.get(field_type, (str, None))[0]
        model_fields[name] = (Optional[py_type], None)  # Use Optional to prevent hallucinations

    return create_model("DynamicSchema", **model_fields)


async def fetch_document(doc_url: str) -> bytes:
    """Fetch document from URL."""
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.get(doc_url, follow_redirects=True)
        response.raise_for_status()
        return response.content


def docling_pdf_to_markdown(pdf_bytes: bytes) -> str:
    """Convert PDF to markdown using Docling library."""
    try:
        # Create a temporary file to work with Docling
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf:
            temp_pdf.write(pdf_bytes)
            temp_pdf_path = temp_pdf.name

        try:
            # Use Docling to convert PDF to markdown
            converter = DocumentConverter()
            result = converter.convert(temp_pdf_path)
            markdown_text = result.document.export_to_markdown()
            return markdown_text
        finally:
            # Clean up temporary file
            os.unlink(temp_pdf_path)
    except Exception as e:
        raise Exception(f"PDF conversion failed: {str(e)}")


async def extract_with_gliner(text_content: str) -> Dict[str, Any]:
    """Tier 1: GLiNER extraction - Instant and free for specific entities."""
    try:
        # Load GLiNER model
        model = GLiNER.from_pretrained("urchade/gliner_medium-v2.1")

        # Define common labels for document processing
        labels = [
            "invoice_number", "date", "total_amount", "vendor_name", "customer_name", 
            "item", "quantity", "price", "subtotal", "tax", "due_date", "po_number",
            "payment_terms", "address", "phone", "email", "website"
        ]

        # Extract entities using GLiNER
        entities = model.predict_entities(text_content[:MAX_TEXT_LENGTH], labels)

        # Format entities into structured data
        structured_data = {}
        for entity in entities:
            label = entity['label']
            text = entity['text']
            
            # Group entities by label
            if label not in structured_data:
                structured_data[label] = []
            structured_data[label].append(text)

        return {
            "gliner_entities": structured_data,
            "used": "gliner_extraction",
            "text_content": text_content[:MAX_TEXT_LENGTH]  # Pass through the text for downstream processing
        }

    except Exception as e:
        return {"error": f"GLiNER extraction failed: {str(e)}", "used": "gliner_extraction_error"}


async def call_ocr_service(doc_url: str, doc_type: str) -> Dict[str, Any]:
    """Call OCR service (either DeepInfra or Ollama based on configuration)."""
    if USE_LOCAL_MODELS:
        return await call_ollama_ocr(doc_url, doc_type)
    else:
        return await call_deepinfra_ocr(doc_url, doc_type)


async def call_deepinfra_ocr(doc_url: str, doc_type: str) -> Dict[str, Any]:
    """Call DeepSeek OCR via DeepInfra API."""
    if not DEEPINFRA_TOKEN:
        return {"error": "Missing DEEPINFRA_TOKEN"}

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPINFRA_TOKEN}"
    }

    # For multimodal models like DeepSeek-OCR, we need to handle image content
    if doc_type in ("image", "pdf"):
        # For now, we'll pass the URL directly - in production, you'd download and encode the image
        payload = {
            "model": DEEPINFRA_OCR_MODEL,
            "messages": [
                {"role": "system", "content": "You are an OCR engine. Return only extracted text from the document."},
                {"role": "user", "content": [
                    {"type": "text", "text": "Extract all text from this document."},
                    {"type": "image_url", "image_url": {"url": doc_url}}
                ]},
            ],
            "stream": False,
            "temperature": 0,
            "max_tokens": 2048,
        }
    else:
        # For text documents, just pass the content
        payload = {
            "model": DEEPINFRA_OCR_MODEL,
            "messages": [
                {"role": "system", "content": "You are an OCR engine. Return only extracted text."},
                {"role": "user", "content": f"Extract text from this document:\n{doc_url}"},
            ],
            "stream": False,
            "temperature": 0,
            "max_tokens": 2048,
        }

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(f"{DEEPINFRA_BASE_URL}/v1/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {"ocr_text": text, "used": "deepinfra_ocr"}
    except Exception as e:
        return {"error": f"DeepInfra OCR failed: {str(e)}", "used": "deepinfra_ocr_error"}


async def call_ollama_ocr(doc_url: str, doc_type: str) -> Dict[str, Any]:
    """Call local Ollama model for OCR."""
    headers = {"Content-Type": "application/json"}

    if doc_type in ("image", "pdf"):
        payload = {
            "model": OLLAMA_OCR_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract all text from this document. Return only the extracted text."},
                        {"type": "image_url", "image_url": {"url": doc_url}}
                    ]
                }
            ],
            "options": {
                "temperature": 0
            },
            "stream": False
        }
    else:
        # For text documents
        payload = {
            "model": OLLAMA_OCR_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": f"Extract text from this document: {doc_url}"
                }
            ],
            "options": {
                "temperature": 0
            },
            "stream": False
        }

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return {"ocr_text": data["message"]["content"], "used": "ollama_ocr"}
    except Exception as e:
        return {"error": f"Ollama OCR failed: {str(e)}", "used": "ollama_ocr_error"}


async def call_json_formatting_service(text_content: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    """Call JSON formatting service (either DeepInfra or Ollama based on configuration)."""
    if USE_LOCAL_MODELS:
        return await call_ollama_json_formatting(text_content, schema)
    else:
        return await call_deepinfra_json_formatting(text_content, schema)


async def call_deepinfra_json_formatting(text_content: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    """Format extracted text into structured JSON using DeepInfra model."""
    if not DEEPINFRA_TOKEN:
        return {"error": "Missing DEEPINFRA_TOKEN"}

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPINFRA_TOKEN}"
    }

    # Create a system prompt that specifies the schema
    schema_description = json.dumps(schema, indent=2)
    system_prompt = f"""You are a structured data extraction expert. Extract information from the provided text according to the given JSON schema.

JSON Schema:
{schema_description}

Instructions:
1. Extract only information that is explicitly present in the text
2. If information is not available, use null values
3. Follow the exact field names and types specified in the schema
4. Return only valid JSON that conforms to the schema
5. Do not add any additional fields not specified in the schema"""

    user_prompt = f"Extract structured data from the following text:\n\n{text_content[:MAX_TEXT_LENGTH]}"

    payload = {
        "model": DEEPINFRA_JSON_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0,
        "max_tokens": 1024,
        "response_format": {"type": "json_object"}
    }

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(f"{DEEPINFRA_BASE_URL}/v1/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            # Parse the JSON response
            try:
                structured_data = json.loads(content)
                return {
                    "structured_data": structured_data,
                    "used": "deepinfra_json"
                }
            except json.JSONDecodeError:
                return {"error": f"Invalid JSON response from model: {content}", "used": "deepinfra_json_parse_error"}
    except Exception as e:
        return {"error": f"DeepInfra JSON formatting failed: {str(e)}", "used": "deepinfra_json_error"}


async def call_ollama_json_formatting(text_content: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    """Format extracted text into structured JSON using local Ollama model."""
    headers = {"Content-Type": "application/json"}

    # Create a system prompt that specifies the schema
    schema_description = json.dumps(schema, indent=2)
    system_prompt = f"""You are a structured data extraction expert. Extract information from the provided text according to the given JSON schema.

JSON Schema:
{schema_description}

Instructions:
1. Extract only information that is explicitly present in the text
2. If information is not available, use null values
3. Follow the exact field names and types specified in the schema
4. Return only valid JSON that conforms to the schema
5. Do not add any additional fields not specified in the schema"""

    user_prompt = f"Extract structured data from the following text:\n\n{text_content[:MAX_TEXT_LENGTH]}"

    payload = {
        "model": OLLAMA_JSON_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "options": {
            "temperature": 0
        },
        "format": "json",  # Request JSON format
        "stream": False
    }

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            content = data["message"]["content"]
            
            # Parse the JSON response
            try:
                structured_data = json.loads(content)
                return {
                    "structured_data": structured_data,
                    "used": "ollama_json"
                }
            except json.JSONDecodeError:
                return {"error": f"Invalid JSON response from model: {content}", "used": "ollama_json_parse_error"}
    except Exception as e:
        return {"error": f"Ollama JSON formatting failed: {str(e)}", "used": "ollama_json_error"}


async def process_document(doc_url: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    """Process a single document with the three-tier approach."""
    result = {
        "doc_url": doc_url,
        "status": "processing",
        "data": {},
        "processing_steps": [],
        "errors": []
    }

    try:
        # Step 1: Fetch document
        doc_type = detect_type(doc_url)
        doc_bytes = await fetch_document(doc_url)
        result["processing_steps"].append(f"fetch_{doc_type}")
        
        text_content = ""
        
        # Step 2: Try GLiNER extraction first (Tier 1 - free & instant)
        if doc_type in ("text", "unknown"):
            # For text documents, decode the bytes
            text_content = doc_bytes.decode("utf-8", errors="ignore")
        else:
            # For other types, we'll get text later
            text_content = ""
        
        gliner_result = await extract_with_gliner(text_content)
        if "gliner_entities" in gliner_result:
            result["gliner_data"] = gliner_result["gliner_entities"]
            result["processing_steps"].append("gliner_extraction")
        elif "error" in gliner_result:
            result["errors"].append(gliner_result["error"])
        
        # Step 3: Process document based on type
        if doc_type == "pdf":
            # Use Docling for PDF processing
            try:
                text_content = docling_pdf_to_markdown(doc_bytes)
                result["docling_markdown"] = text_content
                result["processing_steps"].append("docling_pdf_conversion")
            except Exception as e:
                result["errors"].append(f"PDF conversion failed: {str(e)}")
                # Fallback to OCR
                ocr_result = await call_ocr_service(doc_url, doc_type)
                if "ocr_text" in ocr_result:
                    text_content = ocr_result["ocr_text"]
                    result["processing_steps"].append(ocr_result.get("used", "ocr_fallback"))
                else:
                    result["status"] = "error"
                    result["errors"].append(ocr_result.get("error", "OCR failed with no text extracted"))
                    return result
        elif doc_type in ("image", "text"):
            # Use OCR for images and other types
            ocr_result = await call_ocr_service(doc_url, doc_type)
            if "ocr_text" in ocr_result:
                text_content = ocr_result["ocr_text"]
                result["processing_steps"].append(ocr_result.get("used", "ocr_processing"))
            else:
                result["status"] = "error"
                result["errors"].append(ocr_result.get("error", "OCR failed with no text extracted"))
                return result
        else:
            # For unknown types, try to decode as text
            text_content = doc_bytes.decode("utf-8", errors="ignore")
        
        # Step 4: JSON formatting (Tier 2/3)
        json_result = await call_json_formatting_service(text_content, schema)
        if "structured_data" in json_result:
            result["structured_data"] = json_result["structured_data"]
            result["processing_steps"].append(json_result.get("used", "json_formatting"))
        else:
            result["errors"].append(json_result.get("error", "JSON formatting failed"))
            result["status"] = "error"
            return result

        # Step 5: Validation with user schema
        try:
            DynamicModel = build_dynamic_model(schema)
            validated_data = DynamicModel(**result["structured_data"]).model_dump()
            result["validated_data"] = validated_data
            result["validation_passed"] = True
        except ValidationError as e:
            result["validation_errors"] = e.errors()
            result["validation_passed"] = False
            result["errors"].append(f"Validation error: {str(e)}")

        # Step 6: Combine GLiNER results with final output
        if "gliner_data" in result:
            # Add GLiNER entities to the final result
            for key, value in result["gliner_data"].items():
                if key not in result.get("structured_data", {}):
                    if "structured_data" in result:
                        result["structured_data"][key] = value[0] if len(value) == 1 else value
                    else:
                        result["structured_data"] = {key: value[0] if len(value) == 1 else value}

        result["status"] = "success"
        return result

    except Exception as e:
        result["status"] = "error"
        result["errors"].append(str(e))
        result["processing_steps"].append("error")
        return result


async def main() -> None:
    """Main function for the Apify Actor."""
    async with Actor:
        # Get input from Apify platform
        input_data = await Actor.get_input() or {}
        
        # Extract parameters from input
        doc_urls = input_data.get("docUrls", [])
        schema = input_data.get("schema", {})
        
        if not doc_urls:
            raise ValueError("Input must include 'docUrls' parameter with document URLs")
        
        if not schema:
            raise ValueError("Input must include 'schema' parameter with the expected output structure")
        
        # Process each document
        for doc_url in doc_urls:
            try:
                result = await process_document(doc_url, schema)
                await Actor.push_data(result)  # Push result to Apify dataset
            except Exception as e:
                error_result = {
                    "doc_url": doc_url,
                    "status": "error",
                    "error": str(e),
                    "processing_steps": ["error"],
                    "errors": [str(e)]
                }
                await Actor.push_data(error_result)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())