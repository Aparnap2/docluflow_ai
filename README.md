# DocuFlow Apify Actor with DeepInfra and Ollama Integration

This Apify Actor processes documents using DeepInfra for production and local Ollama models for development, with structured JSON output validated against user-defined schemas.

## Architecture

- **Production**: DeepSeek-OCR via DeepInfra + Gemma/DeepSeek-V3 for JSON formatting
- **Development**: Local Ollama models (LFM2:2.6b, DeepSeek-OCR:3b) via host.docker.internal
- **PDF Processing**: Docling for structured text extraction
- **Validation**: JSON Schema validation for structured output

## Features

- Three-tier processing: GLiNER (Tier 1) → DeepInfra OCR (Tier 2) → DeepInfra JSON formatting (Tier 3)
- Local development support with Ollama
- Production deployment with DeepInfra
- PDF and image document processing
- JSON schema validation
- Error handling and fallback mechanisms

## Environment Variables

### Production (set in Apify Secrets)
- `DEEPINFRA_TOKEN`: Your DeepInfra API token
- `DEEPINFRA_BASE_URL`: DeepInfra API endpoint (default: https://api.deepinfra.com/v1/openai)
- `OCR_MODEL`: OCR model name (default: deepseek-ai/DeepSeek-OCR)
- `JSON_MODEL_PRIMARY`: Primary JSON model (default: google/gemma-3-12b-it)
- `JSON_MODEL_FALLBACK`: Fallback JSON model (default: deepseek-ai/DeepSeek-V3.1)

### Development (for local testing)
- `USE_LOCAL_MODELS`: Set to "true" to use local Ollama models
- `LOCAL_OLLAMA_BASE_URL`: Local Ollama endpoint (default: http://host.docker.internal:11434/v1)

## Input Schema

The actor accepts the following input:

```json
{
  "docUrls": ["https://example.com/document.jpg"],
  "jsonSchema": {
    "type": "object",
    "properties": {
      "vendor_name": {"type": "string"},
      "invoice_number": {"type": "string"},
      "total": {"type": "number"}
    },
    "required": ["vendor_name"]
  },
  "useLocalModels": false
}
```

## Output Format

The actor outputs structured data for each processed document:

```json
{
  "doc_url": "https://example.com/document.jpg",
  "status": "success",
  "data": {
    "vendor_name": "ACME Corp",
    "invoice_number": "INV-2024-001",
    "total": 1250.50
  },
  "validation": {
    "passed": true,
    "errors": []
  },
  "processing_details": {
    "ocr_used": "deepinfra",
    "model_used": "deepseek-ai/DeepSeek-OCR"
  }
}
```

## Local Development

To run locally with Ollama models:

1. Start Ollama with required models:
   ```bash
   ollama pull deepseek-ocr:3b
   ollama pull sam860/LFM2:2.6b
   ```

2. Set environment variables:
   ```bash
   export USE_LOCAL_MODELS=true
   export LOCAL_OLLAMA_BASE_URL=http://host.docker.internal:11434/v1
   ```

3. Run the actor:
   ```bash
   python main.py
   ```

## Deployment to Apify

1. Install Apify CLI:
   ```bash
   npm install -g apify-cli
   ```

2. Login to Apify:
   ```bash
   apify login
   ```

3. Deploy the actor:
   ```bash
   apify push
   ```

## Testing

Run the test suite:
```bash
pytest test_apify_actor.py -v
```

## Troubleshooting

- If using Docker for local development, ensure `host.docker.internal` resolves to your host machine
- For production, verify your DeepInfra token has access to the required models
- Check that PDF URLs are publicly accessible for processing
- For image processing, ensure the image URLs are valid and accessible