# n8n Integration Guide - PropFlow Agent

## Critical: n8n Timeout Configuration

### The Problem
If a user uploads a 50-page lease, Docling + DeepSeek might take > 2 minutes to process.

**n8n Default**: The HTTP Request node (or Apify node) often times out at 2-5 minutes.

**Result**: Apify finishes successfully, but n8n thinks it failed and retries (or errors out), sending the user duplicate emails or nothing.

### The Solution

#### Option 1: Increase n8n Timeout (Simplest)

In your n8n **Apify Node** configuration:

1. Open the Apify Node settings
2. Find **"Timeout"** option
3. Set to **`300000`** (5 minutes in milliseconds)
4. Save

**Recommended for**: Most use cases (single document processing)

#### Option 2: Async Pattern with Webhook (Advanced)

For batch processing or very large documents:

1. **In n8n Apify Node**:
   - Use `Actor.start()` instead of `Run Synchronously`
   - This fires and forgets (non-blocking)

2. **Pass Webhook URL**:
   ```json
   {
     "docUrl": "https://example.com/document.pdf",
     "webhookUrl": "https://your-n8n-instance.com/webhook/propflow-callback"
   }
   ```

3. **Create Webhook Node in n8n**:
   - Receives callback when processing completes
   - Continues workflow with results

**Recommended for**: Batch processing, very large documents (>50 pages)

### Current Implementation

The PropFlow Agent currently supports **synchronous processing** (Option 1).

For async support, you would need to:
1. Add webhook callback support to `main.py`
2. Use Apify's `Actor.start()` API
3. POST results back to webhook URL when done

---

## Local Hosting (for n8n in Docker)

If you are running n8n locally via Docker and the PropFlow Agent on your host machine, use the following configuration:

### 1. Start the Local Server
```bash
# Install dependencies
uv pip install fastapi uvicorn

# Start the server
python server.py
```
The server will start on `http://localhost:8000`.

### 2. Connect from n8n Docker
In your n8n **HTTP Request** node:
- **URL**: `http://host.docker.internal:8000/extract`
- **Method**: `POST`
- **Authentication**: Header `X-API-Key` with value `dev-key-123` (or your env var)

### 3. Body Parameters (JSON)
```json
{
  "source_url": "URL_OR_LOCAL_FILE_PATH",
  "use_gpu_ocr": false
}
```

---

## n8n Workflow Setup

### Basic Workflow Structure

```
Gmail Trigger (has:attachment)
  ↓
Apify Node (Run Actor Synchronously)
  ↓
Switch Node (by doc_type)
  ├─→ Lease → Google Calendar
  ├─→ Quote → Google Sheets
  └─→ COI → Slack Alert
```

### Apify Node Configuration

**Input Format** (PRD-compliant):
```json
{
  "docUrl": "{{ $json.attachments[0].url }}"
}
```

**Or** (backward compatible):
```json
{
  "docUrls": ["{{ $json.attachments[0].url }}"]
}
```

**Timeout**: Set to `300000` (5 minutes)

### Output Format

**Success Response**:
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
    "warnings": []
  }
}
```

**Partial Success** (Validation Errors):
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

**Error Response**:
```json
{
  "doc_url": "https://example.com/document.pdf",
  "status": "error",
  "error": "Document URL inaccessible",
  "error_type": "HTTPError",
  "final_data": {
    "error": "Document URL inaccessible"
  }
}
```

### Switch Node Configuration

**Expression**: `{{ $json.final_data.doc_type }}`

**Outputs**:
- `lease` → Google Calendar Node
- `quote` → Google Sheets Node
- `coi` → Slack Node (with `is_critical` check)

### Google Calendar Node (Lease)

**Event Title**: `Lease Renewal: {{ $json.final_data.tenant_name }}`

**Start Date**: `{{ $json.final_data.calculated_notice_date }}`

**Conditional**: If `rent_cap_flagged == true`, add note about compliance risk

### Google Sheets Node (Quote)

**Columns**:
- Vendor: `{{ $json.final_data.vendor_name }}`
- Total: `{{ $json.final_data.total_amount }}`
- True Cost: `{{ $json.final_data.true_cost }}`
- Hidden Fees: `{{ $json.final_data.hidden_fees_found }}`

**Sort by**: `true_cost` (ascending)

### Slack Node (COI)

**Condition**: `{{ $json.final_data.is_critical == true }}`

**Message**:
```
CRITICAL: {{ $json.final_data.vendor_name }} insurance expiring on {{ $json.final_data.expiration_date }}!

{{#if $json.final_data.policy_limit_flagged}}
⚠️ Policy limit below $1M: ${{ $json.final_data.policy_limit }}
{{/if}}
```

---

## Handling Warnings

The PropFlow Agent now includes `warnings` array in responses to flag missing or uncertain data.

**Example**:
```json
{
  "warnings": [
    "Notice period not found - Manual Review Needed",
    "Rent cap percentage not found - Compliance Risk"
  ]
}
```

**In n8n**: Add a condition to check if `warnings` array is not empty, and send to a "Manual Review" workflow or notification.

---

## Best Practices

1. **Always set timeout to 5 minutes** for Apify Node
2. **Check `status` field** before processing results
3. **Handle `warnings` array** for data quality issues
4. **Use `partial_success` status** to flag documents needing review
5. **Monitor `error_type`** for debugging

---

## Troubleshooting

### Issue: n8n times out before Apify finishes
**Solution**: Increase timeout to 300000ms (5 minutes)

### Issue: Duplicate emails sent
**Solution**: Use async pattern with webhook, or add deduplication logic

### Issue: Missing data in results
**Solution**: Check `warnings` array - fields may be Optional to prevent hallucination

### Issue: Complex tables not extracted correctly
**Solution**: Enable VLM backend in Docling (see `utils_ocr.py` for `use_vlm_for_tables` parameter)

