# EntryAI Platform - Intelligent Document Extraction

**AI-powered document processing platform** that transforms unstructured PDFs into clean, actionable data. Uses Google Gemini 2.0 Flash for vision-based extraction with n8n workflow automation.

## Architecture

```
Email/File → n8n → Local Server / Apify → Gemini 2.0 Flash → Router → Actions
                                                          ↓
                              ┌────────────────────────────┴────────────────────────────┐
                              ↓                      ↓                      ↓           ↓
                        Invoices               Certificates            Leases        Quotes
                        (Airtable)            (Calendar+Slack)        (Airtable)    (Airtable)
```

## Tech Stack

- **Extraction**: Google Gemini 2.0 Flash (Multimodal vision)
- **Validation**: Pydantic v2 with business logic
- **Automation**: n8n workflow orchestration
- **Local Dev**: FastAPI server (bypasses Apify Cloud)
- **Data Processing**: Pandas for CRM cleaning

## Quick Start

### 1. Set API Key

```bash
# Create .env file
echo "GOOGLE_API_KEY=your_key_here" > .env
```

### 2. Development Mode (Local Server)

```bash
# Start local server (no Apify/Gemini API needed for testing)
python main_local.py

# Server runs at http://127.0.0.1:8000
# Endpoints:
#   POST /run-sync    - Main extraction endpoint
#   POST /process     - n8n workflow endpoint
#   GET  /health      - Health check
```

### 3. Production Mode (Apify)

```bash
# Push to Apify
apify push

# Or run locally via Apify CLI
apify run
```

## n8n Integration

### Local Development

Import `templates/n8n_workflow_local.json` to n8n.

**Workflow Flow:**
1. Gmail Trigger or Webhook → Merge Inputs
2. HTTP Request → `POST http://127.0.0.1:8000/process`
3. Router Switch on `{{ $json.doc_type }}`:
   - `invoice` → Airtable (Invoices table)
   - `coi` → Google Calendar + Slack (urgent alerts)
   - `lease` → Airtable (Leases table)
   - `quote` → Airtable (Quotes table)
   - `unknown` → Slack review alert

### Production (Apify)

Update n8n HTTP Request URL to your Apify Actor endpoint.

## API Response Format

### Success Response
```json
{
  "status": "success",
  "doc_type": "invoice",
  "summary": "Invoice extracted successfully",
  "payload": {
    "invoice_number": "INV-2024-001",
    "vendor_name": "Acme Corp",
    "total_amount": 1500.00,
    "invoice_date": "2024-01-15"
  },
  "is_urgent": false,
  "warnings": []
}
```

### COI Critical Alert
```json
{
  "status": "success",
  "doc_type": "coi",
  "payload": {
    "insured_name": "ABC Corp",
    "expiration_date": "2025-02-15",
    "days_until_expiry": 30,
    "is_urgent": true
  },
  "is_urgent": true
}
```

## Document Types

| Type | Key Fields | n8n Action |
|------|------------|------------|
| **Invoice** | invoice_number, vendor_name, total_amount, due_date | Airtable |
| **COI** | insured_name, expiration_date, policy_limit, days_until_expiry | Calendar + Slack |
| **Lease** | tenant_name, monthly_rent, end_date, notice_period_days | Airtable |
| **Quote** | vendor_name, total_amount, true_cost, line_items | Airtable |

## Testing

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_main_local.py -v

# Run golden dataset benchmark
python run_benchmark.py --ci
```

## Test Results

| Suite | Status |
|-------|--------|
| Unit Tests | 155 passed, 6 skipped |
| Local Server | 28 passed |
| Golden Dataset | Ready (add PDFs to tests/golden_dataset/) |

## Project Structure

```
├── main.py                    # Apify Actor (production)
├── main_local.py              # Local dev server (FastAPI)
├── schemas.py                 # Pydantic validation
├── run_benchmark.py           # Golden dataset regression tests
├── tests/
│   ├── test_main_local.py     # Local server tests
│   ├── test_entryai_router.py # Router tests
│   ├── test_invoice_extraction.py
│   ├── test_crm_cleaning.py
│   └── golden_dataset/        # Test documents
├── templates/
│   └── n8n_workflow_local.json  # n8n import
└── .env                       # API keys
```

## Environment Variables

```bash
GOOGLE_API_KEY=AIza...  # Required for main.py (Gemini API)
```

## Development

### Adding New Document Types

1. Add schema to `schemas.py` (e.g., `class NewDocData(BaseModel)`)
2. Add extraction function to `main.py` (e.g., `extract_newdoc()`)
3. Add route in `router()` function
4. Update `CRITICAL_FIELDS` in `run_benchmark.py`
5. Add test case to `tests/golden_dataset/`

### Running Tests with Real PDFs

```bash
# Add PDFs to tests/golden_dataset/inputs/
# Add expected JSON to tests/golden_dataset/expected_outputs/
python run_benchmark.py -v
```

## License

MIT
