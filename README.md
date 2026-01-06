# PropFlow Agent - AI Document Extraction for Property Managers

**Turn unstructured property PDFs into autonomous actions** - Calendar events, Spreadsheet rows, Slack alerts.

## Architecture

**Philosophy:** "Local OCR + Ollama = Private, Fast, Free"

```
Gmail → n8n → Local Server (FastAPI) → DeepSeek OCR → Router → Ministral → n8n Actions
                                                    ↓
                              ┌─────────────────────┴─────────────────────┐
                              ↓                     ↓                     ↓
                        Google Calendar       Google Sheets/Airtable       Slack
```

### Tech Stack
- **OCR**: DeepSeek OCR (Ollama) with Docling fallback
- **Extraction**: Ministral-3B (Ollama)
- **Routing**: Keyword-based (fast, deterministic)
- **Server**: FastAPI for n8n integration
- **Validation**: Pydantic with business logic

## Quick Start

### 1. Start Ollama Models
```bash
docker exec ollama ollama pull deepseek-ocr:3b
docker exec ollama ollama pull ministral-3:3b
```

### 2. Start Local Server
```bash
source .venv/bin/activate
python server.py
# Server runs at http://localhost:8000
```

### 3. n8n Integration
Import `templates/n8n_local_server_workflow.json` to n8n.

**n8n Flow:**
1. Gmail Trigger → Filter PDF
2. HTTP Request → `POST http://localhost:8000/extract`
3. Switch on `{{ $json.doc_type }}`:
   - `lease` → Google Calendar
   - `quote` → Google Sheets/Airtable
   - `coi` → Slack (if `is_critical`)

## n8n Output Format

### Success Response
```json
{
  "status": "success",
  "doc_type": "lease",
  "filename": "lease.pdf",
  "data": {
    "doc_type": "lease",
    "tenant_name": "Jane Doe",
    "end_date": "2025-05-31",
    "calculated_notice_date": "2025-04-01",
    "rent_cap_flagged": true,
    "warnings": ["Rent cap percentage not found"]
  },
  "is_critical": false,
  "notice_date": "2025-04-01"
}
```

### COI Critical Alert
```json
{
  "status": "success",
  "doc_type": "coi",
  "data": {
    "doc_type": "coi",
    "expiration_date": "2025-02-15",
    "insured_name": "ABC Corp",
    "is_critical": true
  },
  "is_critical": true  // Route to Slack
}
```

## Testing

```bash
# Test router logic (fast)
python test_chunk1_router.py

# Test n8n response format (fast)
python test_chunk2_server.py

# Test extraction with sample text (fast)
python test_extraction_direct.py

# Full pipeline with real PDFs (slow - DeepSeek OCR)
python test_real_pdfs.py
```

## Test Results

| Test | Status |
|------|--------|
| Router Logic | ✓ COI/Lease/Quote detection |
| n8n Format | ✓ Correct Switch node routing |
| Extraction | ✓ JSON output validated |

## Document Types

| Type | Fields | n8n Action |
|------|--------|------------|
| **Lease** | tenant_name, end_date, notice_date | Google Calendar |
| **Quote** | vendor_name, total_amount, true_cost | Google Sheets |
| **COI** | insured_name, expiration_date, is_critical | Slack Alert |

## Environment Variables

```bash
export DOCUFLOW_API_KEY="dev-key-123"  # Optional API key
export PORT=8000                       # Server port
```

## Files

```
├── server.py                    # FastAPI server for n8n
├── agent_graph.py              # LangGraph workflow
├── utils_ocr.py                # OCR (DeepSeek + Docling)
├── schemas.py                  # Pydantic schemas
├── templates/
│   ├── n8n_local_server_workflow.json  # n8n import
│   ├── lease contract.pdf
│   ├── bid.pdf
│   └── COI.pdf
└── test_*.py                   # Test scripts
```
