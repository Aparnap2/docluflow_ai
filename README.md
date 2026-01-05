# PropFlow Agent - AI Clerk for Property Managers

**Turn unstructured property documents (PDFs) into autonomous actions** - Calendar events, Bid comparisons, Slack alerts.

This Apify Actor implements **Autonomous Intelligence** through Router + Reasoning + Validation layers, processing property documents (leases, quotes, COIs) with embedded business logic.

> 📖 **For detailed PRD implementation documentation, see [PRD_IMPLEMENTATION.md](PRD_IMPLEMENTATION.md)**

## Architecture

**Philosophy:** "Apify is the Brain (Heavy Lift). n8n is the Limbs (Connectivity)."

- **OCR**: Docling (Local, fast, table-aware)
- **Brain**: LangGraph (Routing & State Management)
- **Inference**: Ollama (dev) / DeepSeek-V3 via DeepInfra (prod)
- **Guardrails**: Pydantic (Strict Schema Validation with Business Logic)

### Core Features (The "Agentic" Layer)

| Feature | Document Type | AI Logic (Reasoning) | Action (Output) |
| :--- | :--- | :--- | :--- |
| **Lease Auditor** | Lease Agreements (PDF) | Calculate Notice Date = End Date - Notice Period. Flag Rent Cap %. | **Google Calendar:** "Notice Due: Unit 4B" |
| **Bid Leveler** | Vendor Quotes (PDF) | Find hidden fees. Standardize line items. Rank by 'True Cost'. | **Email Reply:** HTML Table comparing 3 bids. |
| **COI Watchdog** | Insurance Certs (PDF) | Check if Expiration < Today + 30. Check Policy Limit > $1M. | **Slack Alert:** "CRITICAL: Plumber insurance expiring!" |

## Features

- **Autonomous Intelligence**: Business logic embedded in Pydantic schemas
- **Router**: Intelligent document type detection (lease, quote, COI)
- **Business Logic Validators**: 
  - Lease: Auto-calculate notice dates, flag missing rent caps
  - Quote: Calculate true cost for bid ranking
  - COI: Flag expiring policies and low policy limits
- **Production Hardened**: 
  - ✅ Optional fields prevent hallucination
  - ✅ Warnings array for missing data
  - ✅ ValidationError handling (partial success)
  - ✅ Increased timeouts for large documents
  - ✅ **Enterprise Security**: Password-protected PDF detection, filename sanitization, magic bytes verification, ReDoS prevention
- **Local Development**: Ollama models (ministral-3:3b)
- **Production Ready**: Structured for DeepInfra migration
- **n8n Integration**: Outputs actionable JSON for automation workflows

> ⚠️ **Before deploying**: See [N8N_INTEGRATION_GUIDE.md](N8N_INTEGRATION_GUIDE.md) for critical n8n timeout configuration

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

The actor accepts both PRD format (`docUrl`) and backward-compatible format (`docUrls`):

**PRD Format (Single Document):**
```json
{
  "docUrl": "https://example.com/lease.pdf"
}
```

**Backward Compatible (Multiple Documents):**
```json
{
  "docUrls": ["https://example.com/lease.pdf", "https://example.com/quote.pdf"]
}
```

## Output Format

The actor outputs actionable JSON with business logic applied:

**Lease Example (Success):**
```json
{
  "doc_url": "https://example.com/lease.pdf",
  "doc_type": "lease",
  "status": "success",
  "final_data": {
    "doc_type": "lease",
    "tenant_name": "John Smith",
    "end_date": "2024-12-31",
    "notice_period_days": 60,
    "calculated_notice_date": "2024-11-01",
    "rent_cap_percentage": null,
    "rent_cap_flagged": true,
    "warnings": ["Rent cap percentage not found - Compliance Risk"]
  }
}
```

**Lease Example (Partial Success - Missing Fields):**
```json
{
  "doc_url": "https://example.com/lease.pdf",
  "doc_type": "lease",
  "status": "partial_success",
  "warnings": [
    {
      "type": "validation_error",
      "loc": ["notice_period_days"],
      "msg": "field required"
    }
  ],
  "final_data": {
    "status": "validation_error",
    "partial_data": {
      "tenant_name": "John Smith",
      "end_date": "2024-12-31"
    }
  }
}
```

**Quote Example:**
```json
{
  "doc_type": "quote",
  "final_data": {
    "doc_type": "quote",
    "vendor_name": "ACME Plumbing",
    "total_amount": 1000.0,
    "hidden_fees_found": true,
    "true_cost": 1100.0,
    "line_items_standardized": ["Labor: $500", "Materials: $500"]
  }
}
```

**COI Example:**
```json
{
  "doc_type": "coi",
  "final_data": {
    "doc_type": "coi",
    "expiration_date": "2024-02-15",
    "policy_limit": 500000.0,
    "is_critical": true,
    "policy_limit_flagged": true
  }
}
```

## Local Development

To run locally with Ollama models:

1. Start Ollama with required models:
   ```bash
   ollama pull ministral-3:3b  # For extraction
   ollama pull deepseek-ocr:3b  # For OCR (if needed)
   ```

2. Run tests:
   ```bash
   uv run python test_propflow_transformation.py  # Basic tests
   uv run python test_prd_features.py            # PRD feature tests
   uv run python test_propflow_e2e.py            # End-to-end with LLM
   ```

3. Run the actor:
   ```bash
   uv run python main.py
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

Run the test suites:
```bash
# Basic transformation tests
uv run python test_propflow_transformation.py

# PRD feature tests (business logic validators)
uv run python test_prd_features.py

# Edge case tests (data formats, error handling)
uv run python test_edge_cases.py

# End-to-end tests with actual LLM
uv run python test_propflow_e2e.py
```

**Test Results**: 27+ test cases, 100% pass rate ✅

See [PRD_IMPLEMENTATION.md](PRD_IMPLEMENTATION.md) for detailed documentation on business logic validators.

## Production Deployment

### Critical Configuration

**n8n Setup** (REQUIRED):
- Set Apify Node timeout to **300000ms** (5 minutes)
- See [N8N_INTEGRATION_GUIDE.md](N8N_INTEGRATION_GUIDE.md) for complete setup

**Status Handling**:
- `success`: Process normally
- `partial_success`: Send to manual review (check `warnings` array)
- `error`: Log and alert

**Warnings Array**:
- Always check `warnings` array in responses
- Missing fields generate warnings (prevents hallucination)
- Handle warnings in n8n workflow (manual review path)

## Documentation

- **[PRD_IMPLEMENTATION.md](PRD_IMPLEMENTATION.md)** - Detailed business logic documentation
- **[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)** - Complete implementation status
- **[LOAD_TEST_SUMMARY.md](LOAD_TEST_SUMMARY.md)** - Performance metrics and optimization
- **[CRITICAL_FIXES_APPLIED.md](CRITICAL_FIXES_APPLIED.md)** - Production fixes details
- **[ENTERPRISE_HARDENING.md](ENTERPRISE_HARDENING.md)** - Enterprise security features
- **[N8N_INTEGRATION_GUIDE.md](N8N_INTEGRATION_GUIDE.md)** - n8n setup and configuration

## Troubleshooting

- **n8n timeout errors**: Set Apify Node timeout to 300000ms (5 minutes)
- **Missing data in results**: Check `warnings` array - fields may be Optional to prevent hallucination
- **Validation errors**: Check `status` field - `partial_success` includes `partial_data` and `errors`
- **Complex tables not extracted**: Enable VLM backend in Docling (see `utils_ocr.py`)
- **Docker issues**: Ensure `host.docker.internal` resolves to your host machine
- **DeepInfra**: Verify your token has access to required models
- **PDF URLs**: Ensure URLs are publicly accessible for processing