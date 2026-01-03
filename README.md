# Apify Actor for Document Processing with DeepInfra and Ollama

This is an Apify Actor that processes documents using DeepInfra for OCR and local Ollama models for JSON formatting.

## Architecture

- **OCR**: DeepSeek-OCR via DeepInfra (OpenAI-compatible API)
- **JSON Formatting**: LFM2:2.6b via local Ollama (dev) or DeepInfra (prod) 
- **PDF Processing**: Docling for PDF to structured text
- **Validation**: Pydantic for schema validation

## Environment Variables

- `DEEPINFRA_TOKEN`: Your DeepInfra API token
- `DEEPINFRA_BASE_URL`: DeepInfra API endpoint (default: https://api.deepinfra.com/v1/openai)
- `OCR_MODEL`: OCR model name (default: deepseek-ai/DeepSeek-OCR)
- `JSON_MODEL_PRIMARY`: Primary JSON model (default: google/gemma-3-12b-it)
- `JSON_MODEL_FALLBACK`: Fallback JSON model (default: deepseek-ai/DeepSeek-V3.1)

## Input Schema

```json
{
  "docUrls": ["https://example.com/document.jpg"],
  "jsonSchema": {
    "type": "object",
    "properties": {
      "vendor_name": {"type": "string"},
      "invoice_number": {"type": "string"},
      "total": {"type": "number"}
    }
  }
}
```