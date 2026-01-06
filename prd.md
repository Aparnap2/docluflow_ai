# Product Requirements Document (PRD) - EntryAI Platform v1.0

**Product Name:** EntryAI Platform
**Version:** 1.0
**Last Updated:** 2026-01-07
**Status:** Draft / In Review

---

## 1. Executive Summary

### 1.1 Vision Statement

EntryAI is an intelligent automation platform that transforms unstructured data into clean, actionable business intelligence. By combining vision-based document extraction with rule-based verification and data hygiene capabilities, EntryAI eliminates manual data entry, reduces human error, and accelerates business workflows from input to action.

The platform serves as the "front door" for business automation, handling the three critical stages of data ingestion: capturing information from documents, validating its accuracy against business rules, and maintaining database hygiene through deduplication and standardization.

### 1.2 Problem Statement

Organizations face three interconnected data challenges:

1. **Document Chaos:** Millions of documents (invoices, forms, contracts, medical records) arrive daily in formats that resist automation. PDFs are image-heavy, handwritten content is unreadable by OCR, and critical data is trapped in layout-dependent formats.

2. **Verification Gaps:** Extracted data often contains errors that downstream systems cannot catch. An invoice with a wrong vendor, a calculation mismatch, or a date outside fiscal parameters can cause payment delays, compliance violations, and audit failures.

3. **Data Decay:** Customer databases, vendor lists, and CRM records accumulate duplicates, inconsistent formatting, and missing fields over time. This "data entropy" reduces marketing effectiveness, inflates storage costs, and creates operational friction.

### 1.3 Solution Overview

EntryAI provides three integrated modules that address these challenges:

- **Module A (Input Clerk):** Vision-based extraction from structured and unstructured documents, transforming PDFs, images, and forms into clean JSON/CSV.

- **Module B (Compliance Officer):** Rule-based verification engine that cross-checks extracted data against approved lists, validates calculations, and enforces business logic.

- **Module C (Janitor):** Database maintenance layer that deduplicates records, standardizes formats, and enriches missing data points.

All modules share a common Apify Actor infrastructure with a task_type router, enabling unified deployment and scaling.

---

## 2. Platform Architecture

### 2.1 High-Level Architecture

```
                                    EntryAI Platform
    +---------------------------------------------------------------------+
    |                                                                     |
    |  +---------------------+     +---------------------+                |
    |  |   n8n Workflows     |     |   Direct API Calls  |                |
    |  +---------------------+     +---------------------+                |
    |            |                          |                             |
    |            v                          v                             |
    |  +-----------------------------------------------------------+      |
    |  |                    Apify Actor (EntryAI)                  |      |
    |  +-----------------------------------------------------------+      |
    |            |                          |                             |
    |            v                          v                             |
    |  +-----------------------------------------------------------+      |
    |  |                    Task Type Router                       |      |
    |  +-----------------------------------------------------------+      |
    |            |            |            |                          |
    |            v            v            v                          |
    |  +-----------+   +-----------+   +-----------+                  |
    |  | Module A  |   | Module B  |   | Module C  |                  |
    |  | Input     |   | Compliance|   | Janitor   |                  |
    |  | Clerk     |   | Officer   |   |           |                  |
    |  +-----------+   +-----------+   +-----------+                  |
    |            |            |            |                          |
    |            v            v            v                          |
    |  +-----------------------------------------------------------+  |
    |  |              Google Gemini 2.0 Flash (Vision)             |  |
    |  +-----------------------------------------------------------+  |
    |                                                                     |
    +---------------------------------------------------------------------+
```

### 2.2 Input/Output Schema

All interactions follow a consistent JSON schema pattern:

#### Input Schema
```json
{
  "task_type": "document_extract | data_clean | data_verify",
  "file_binary": "base64_encoded_content",
  "filename": "document.pdf",
  "config": {
    "output_format": "json | csv",
    "extraction_mode": "fast | detailed",
    "verify_calculations": true,
    "fuzzy_threshold": 0.85,
    "standardize_phone": true,
    "enrich_missing": false
  },
  "reference_data": {
    "approved_vendors": ["vendor1", "vendor2"],
    "fiscal_year_start": "2025-01-01",
    "dedupe_fields": ["email", "company_name"]
  }
}
```

#### Output Schema
```json
{
  "status": "success | error | needs_review",
  "task_type": "document_extract",
  "result": {},
  "stats": {
    "processing_time_ms": 2500,
    "confidence_score": 0.94,
    "fields_extracted": 12,
    "errors_found": 0
  },
  "verification": {
    "passed": true,
    "issues": []
  }
}
```

### 2.3 Task Type Router

The router pattern enables a single Apify Actor to handle multiple task types:

| Task Type | Module | Description |
|-----------|--------|-------------|
| `document_extract` | Input Clerk | Extract structured data from documents |
| `data_verify` | Compliance Officer | Validate extracted data against rules |
| `data_clean` | Janitor | Deduplicate and standardize records |

---

## 3. Module A: The "Input Clerk" (Document Digitization)

### 3.1 Module Overview

The Input Clerk transforms unstructured and semi-structured documents into clean, machine-readable formats. Using Google Gemini 2.0 Flash's vision capabilities, it can read printed text, handwritten content, tables, and complex layouts.

### 3.2 Supported Document Types

#### 3.2.1 Financial Documents

**Invoices**
- Extract line items (description, quantity, unit price, total)
- Capture header data (invoice number, date, due date, vendor)
- Calculate subtotals, taxes, and grand totals
- Identify payment terms and PO numbers
- Output format: JSON with line_items array or flattened CSV

**Receipts**
- Capture merchant name, date, and total
- Extract individual item purchases
- Identify payment method (card, cash, digital)
- Handle handwritten receipts with lower confidence scores

#### 3.2.2 Business Forms

**Intake Forms**
- Read handwritten field logs and service tickets
- Extract structured fields (name, date, location, notes)
- Handle checkboxes and radio button selections
- Preserve narrative text as separate field

**Application Forms**
- Parse standard application layouts
- Extract personal information, employment history, references
- Handle both typed and handwritten responses

#### 3.2.3 Legal & Medical Documents

**Contracts & Agreements**
- Identify and extract specific clauses (termination, liability, payment terms)
- Capture key dates (effective date, expiration, renewal terms)
- Extract party names and contact information
- Flag missing standard clauses for review

**Medical Records**
- Extract patient demographics and visit dates
- Parse diagnosis codes (ICD-10) and procedure codes (CPT)
- Capture medication names and dosages
- Handle varied medical document layouts

#### 3.2.4 Property Documents (Legacy Support)

The platform maintains support for property management documents:

**Leases**
- Tenant name, property address, unit number
- Lease term (start date, end date)
- Rent amount, security deposit, payment terms
- Special clauses and conditions

**Insurance Certificates (COIs)**
- Insured name and policy number
- Coverage types and limits
- Expiration date (critical for alerts)
- Certificate holder information

**Vendor Quotes**
- Vendor identification and contact
- Line items with pricing
- Total amount and validity period
- Comparison against historical pricing

### 3.3 Extraction Capabilities

| Capability | Status | Notes |
|------------|--------|-------|
| Printed text extraction | Stable | 99%+ accuracy on clean documents |
| Handwritten text | Beta | Accuracy varies by handwriting clarity |
| Table extraction | Stable | Handles multi-page tables |
| Signature detection | Planned | v1.1 |
| Form field recognition | Stable | Auto-detects labeled fields |
| Multi-language | Beta | English primary, Spanish experimental |
| Poor quality scans | Stable | Upscaling improves results |

### 3.4 Output Formats

**JSON (Default)**
```json
{
  "document_type": "invoice",
  "confidence": 0.97,
  "extracted_at": "2026-01-07T10:30:00Z",
  "data": {
    "vendor": {
      "name": "Acme Office Supplies",
      "address": "123 Business Park, Austin TX 78701"
    },
    "invoice_number": "INV-2026-0042",
    "date": "2026-01-05",
    "due_date": "2026-02-05",
    "line_items": [
      {
        "description": "Premium Copy Paper, 10 reams",
        "quantity": 10,
        "unit_price": 45.00,
        "total": 450.00
      }
    ],
    "subtotal": 450.00,
    "tax_rate": 0.0825,
    "tax_amount": 37.13,
    "total": 487.13
  }
}
```

**CSV (Flattened)**
```
document_type,invoice_number,vendor_name,date,total,line_item_1_description,line_item_1_total
invoice,INV-2026-0042,Acme Office Supplies,2026-01-05,487.13,"Premium Copy Paper, 10 reams",450.00
```

### 3.5 Configuration Options

```python
class ExtractionConfig(BaseModel):
    """Module A Configuration"""
    output_format: Literal["json", "csv"] = "json"
    extraction_mode: Literal["fast", "detailed"] = "detailed"
    include_raw_text: bool = False
    fallback_ocr: bool = True  # Use traditional OCR if vision fails
    table_format: Literal["nested", "flattened"] = "nested"
```

---

## 4. Module B: The "Compliance Officer" (Data Verification)

### 4.1 Module Overview

The Compliance Officer validates extracted data against business rules and external references. It acts as a gatekeeper, ensuring that only accurate, compliant data flows downstream to ERP, accounting, and CRM systems.

### 4.2 Verification Types

#### 4.2.1 Cross-Reference Verification

**Vendor Validation**
```
Rule: "Does vendor exist in Approved Vendors list?"
Input: Extracted vendor name = "Acme Office Supplies"
Reference: approved_vendors = ["Acme Corp", "Office Depot", "Staples"]
Result: MATCH with fuzzy matching (similarity: 0.92)
```

**Account Mapping**
```
Rule: "Does GL code match department?"
Input: GL code = 6500, Department = "Marketing"
Reference: valid_mappings = {"Marketing": [6200, 6300, 6400]}
Result: FLAG - 6500 not in Marketing range
```

#### 4.2.2 Mathematical Verification

**Invoice Calculation Checks**
```
Rule: "Does Subtotal + Tax = Total?"
Input: subtotal = 450.00, tax = 37.13, total = 487.13
Calculation: 450.00 + 37.13 = 487.13
Result: PASS
```

**Line Item Math**
```
Rule: "Does Quantity × Unit Price = Line Total?"
Input: quantity = 10, unit_price = 45.00, line_total = 450.00
Calculation: 10 × 45.00 = 450.00
Result: PASS
```

**Discount Application**
```
Rule: "Is discounted price calculated correctly?"
Input: original = 1000.00, discount_percent = 15, discounted = 850.00
Calculation: 1000 × (1 - 0.15) = 850.00
Result: PASS
```

#### 4.2.3 Temporal Verification

**Date Range Validation**
```
Rule: "Is invoice date within fiscal year?"
Input: invoice_date = 2026-01-05
Reference: fiscal_year = 2025-01-01 to 2025-12-31
Result: FLAG - Date outside fiscal year
```

**Due Date Logic**
```
Rule: "Is due date after invoice date?"
Input: invoice_date = 2026-01-05, due_date = 2026-01-04
Result: FLAG - Due date precedes invoice
```

**Expiration Monitoring**
```
Rule: "Is document expiring within warning period?"
Input: expiration_date = 2026-02-01, today = 2026-01-07
Warning threshold = 30 days
Result: CRITICAL - Expires in 25 days
```

#### 4.2.4 Format Validation

**Email Format**
```
Rule: "Is email address properly formatted?"
Input: user@domain.com
Result: PASS / FAIL with suggestion
```

**Phone Number**
```
Rule: "Does phone number match expected format?"
Input: "555-123-4567" or "(555) 123-4567"
Result: Standardize to canonical format
```

**Currency Codes**
```
Rule: "Is currency code valid ISO 4217?"
Input: "USD", "EUR", "INVALID"
Result: PASS / SUGGESTION
```

### 4.3 Verification Result Structure

```python
class VerificationResult(BaseModel):
    """Module B Output"""
    overall_status: Literal["passed", "flagged", "failed"]
    checks_performed: int
    checks_passed: int
    checks_failed: int
    issues: list[VerificationIssue]

class VerificationIssue(BaseModel):
    """Individual verification failure"""
    rule_name: str
    severity: Literal["error", "warning", "info"]
    field_path: str  # e.g., "invoice.total"
    expected_value: Optional[str]
    actual_value: str
    message: str
    suggestion: Optional[str]
```

### 4.4 Handling Verification Failures

| Severity | Action | Example |
|----------|--------|---------|
| **Error** | Block processing, require manual review | Vendor not in approved list |
| **Warning** | Process with flag, notify | Invoice outside fiscal year |
| **Info** | Log only, no intervention | Phone number reformatted |

---

## 5. Module C: The "Janitor" (Database Maintenance)

### 5.1 Module Overview

The Janitor maintains data hygiene across customer databases, vendor lists, and CRM records. It operates on existing data stores to deduplicate, standardize, and enrich records.

### 5.2 Core Functions

#### 5.2.1 Deduplication Engine

**Fuzzy Matching**
```
Input Records:
1. {name: "Bob Smith", email: "bob.smith@email.com", company: "Acme Inc"}
2. {name: "Robert Smith", email: "r.smith@email.com", company: "Acme Incorporated"}
3. {name: "John Doe", email: "john@other.com", company: "Other Co"}

Analysis:
- Record 1 & 2: 0.89 similarity (name variation + company variation)
- Record 1 & 3: 0.12 similarity
- Record 2 & 3: 0.11 similarity

Result: Merge recommendation for 1 & 2
```

**Matching Strategies**
| Strategy | Fields | Use Case |
|----------|--------|----------|
| Exact | email, phone, tax_id | High-confidence duplicates |
| Fuzzy | name, company_name | Name variations, typos |
| Hybrid | email + name | Cross-validation |
| Phonetic | name | Phonetic similarity (NYSIIS) |

#### 5.2.2 Standardization Engine

**Phone Number Formatting**
```
Input: "5551234567", "555-123-4567", "(555) 123.4567"
Output: "(555) 123-4567" (North American format)
```

**Address Standardization**
```
Input: "123 Main St, Austin, TX 78701"
Parsed:
  street: "123 Main Street"
  city: "Austin"
  state: "TX"
  zip: "78701"
  normalized: "123 Main St, Austin, TX 78701"
```

**Name Normalization**
```
Input variations: "bob smith", "Bob Smith", "ROBERT SMITH", "bob  smith  "
Output: "Bob Smith" (Title case, whitespace normalized)
```

**Email Validation**
```
Input: "BOB.SMITH@EMAIL.COM" -> "bob.smith@email.com"
Flag: "bob@email" -> Suggestion: "Missing domain TLD"
```

#### 5.2.3 Data Enrichment

**Postal Code Enrichment**
```
Input: {city: "Austin", state: "TX"}
Lookup: ZIP code database
Output: {city: "Austin", state: "TX", zip: "78701"}
```

**Company Enrichment (External API)**
```
Input: {company_name: "Acme Inc"}
External API: Dun & Bradstreet, Clearbit
Output: {
  company_name: "Acme Inc",
  industry: "Manufacturing",
  employee_count: "500-1000",
  revenue_range: "$50M-$100M"
}
```

**Geocoding**
```
Input: {address: "123 Main St, Austin, TX"}
Geocoding API: Google Maps, OpenStreetMap
Output: {lat: 30.2672, lng: -97.7431}
```

### 5.3 Output Structure

```python
class CleanResult(BaseModel):
    """Module C Output"""
    records_processed: int
    duplicates_found: int
    duplicates_merged: int
    standardization_changes: int
    enrichment_count: int
    output_records: list[dict]

class MergeDecision(BaseModel):
    """Deduplication merge recommendation"""
    cluster_id: str
    records: list[str]  # Record IDs
    confidence: float
    merge_strategy: str
    merged_fields: dict
    conflicts: list[ConflictDetail]
```

---

## 6. n8n Workflow Templates

### 6.1 Workflow 1: Accounts Payable Automation

**Trigger:** Email received with invoice attachment

```
+--------------------+     +--------------------+     +--------------------+
| Gmail Trigger      |     | Split Attachments  |     | Filter PDFs Only   |
| Poll: 1 minute     | --> | One attachment     | --> | MIME type check    |
| Filter: has:attach |     | per execution      |     |                    |
+--------------------+     +--------------------+     +--------------------+
                                                            |
                                                            v
+--------------------+     +--------------------+     +--------------------+
| Xero/QuickBooks    |     | If Flagged:        |     | Module A + B       |
| Create Bill        | <-- | Manual Review      | <-- | Extract + Verify   |
|                   |     | (Human in loop)    |     |                    |
+--------------------+     +--------------------+     +--------------------+
                                                            |
                              +----------------------------+
                              |
                              v
                       +--------------------+
                       | Switch on Status   |
                       +--------------------+
                              |
              +---------------+---------------+
              |               |               |
              v               v               v
       +-----------+    +-----------+    +-----------+
       | Xero:     |    | Slack:    |    | Slack:    |
       | Create    |    | Alert:    |    | Alert:    |
       | Bill      |    | Verify    |    | Error     |
       +-----------+    | Issues    |    |           |
                        +-----------+    +-----------+
```

**n8n Node Configuration:**

```yaml
Gmail Trigger:
  resource: message
  event: new email
  filters:
    hasAttachment: true
    subject:
      - contains: "invoice"
      - contains: "INV"

Apify Input:
  task_type: "document_extract"
  config:
    extraction_mode: "detailed"
    verify_calculations: true
  reference_data:
    approved_vendors: "{{ $json.approved_vendors }}"

Switch Node:
  expression: "{{ $json.status }}"
  cases:
    "success":
      - Xero Node
    "needs_review":
      - Manual Review Branch
    "error":
      - Slack Error Alert
```

### 6.2 Workflow 2: Field Operations Digitizer

**Trigger:** Dropbox file upload / Mobile app submission

```
+--------------------+     +--------------------+     +--------------------+
| Dropbox Trigger    |     | Read File          |     | Module A           |
| Watch folder:      | --> | Binary to Base64   | --> | Handwriting Mode   |
| /field-reports     |     |                    |     |                    |
+--------------------+     +--------------------+     +--------------------+
                                                            |
                                                            v
+--------------------+     +--------------------+     +--------------------+
| Salesforce         |     | If Low Confidence: |     | Parse Results      |
| Create/Update      | <-- | Queue for Review   | <-- | Extract fields     |
| Case/Record        |     |                    |     |                    |
+--------------------+     +--------------------+     +--------------------+
```

**n8n Node Configuration:**

```yaml
Dropbox Trigger:
  resource: file
  path: "/field-reports"
  recursive: false

Module A Config:
  task_type: "document_extract"
  config:
    extraction_mode: "detailed"
    include_raw_text: true
  # Special handling for handwriting
  custom_prompt: |
    Extract all data from this handwritten field report.
    Pay special attention to: date, location, technician name,
    work performed, materials used, and any safety notes.

Salesforce Output:
  operation: upsert
  object: "Case"
  fields:
    Subject: "{{ $json.work_type }} - {{ $json.date }}"
    Description: "{{ $json.notes }}"
    Status: "In Progress"
    Priority: "{{ $json.urgency }}"
```

### 6.3 Workflow 3: CRM Hygiene Automation

**Trigger:** Scheduled (daily/weekly)

```
+--------------------+     +--------------------+     +--------------------+
| Schedule Trigger   |     | Read CRM           |     | Module C           |
| Frequency: Daily   | --> | Export Leads/      | --> | Clean + Dedupe     |
| Time: 2:00 AM UTC  |     | Contacts           |     |                    |
+--------------------+     +--------------------+     +--------------------+
                                                            |
                                                            v
+--------------------+     +--------------------+     +--------------------+
| CRM Update         |     | Report Generation  |     | Review Changes     |
| Apply Updates      | <-- | Summary Stats      | <-- | Manual Approval    |
|                    |     |                    |     | (Optional)         |
+--------------------+     +--------------------+     +--------------------+
                                                            |
                                                            v
                                               +--------------------+
                                               | Write Back to CRM  |
                                               | - Standardized     |
                                               | - Deduplicated     |
                                               | - Enriched         |
                                               +--------------------+
```

**n8n Node Configuration:**

```yaml
Schedule:
  rule: everyDay
  hour: 2
  minute: 0

Module C Config:
  task_type: "data_clean"
  config:
    fuzzy_threshold: 0.85
    standardize_phone: true
    enrich_missing: false
  reference_data:
    dedupe_fields: ["email", "company_name"]
    merge_strategy: "prefer_complete"

Output Fields:
  - status: "processed"
  - duplicates_found: int
  - fields_standardized: int
  - merge_decisions: array
```

---

## 7. Technical Implementation

### 7.1 Apify Actor Structure

```
entryai-actor/
├── requirements.txt
├── main.py
├── config.py
├── models/
│   ├── __init__.py
│   ├── schemas.py          # Pydantic models
│   ├── tasks.py            # Task router
│   └── validators.py       # Business logic validators
├── modules/
│   ├── __init__.py
│   ├── input_clerk.py      # Module A
│   ├── compliance.py       # Module B
│   └── janitor.py          # Module C
└── utils/
    ├── __init__.py
    ├── pdf_processor.py
    └── fuzzy_matching.py
```

### 7.2 Task Router Implementation

```python
# main.py (simplified)
import asyncio
from apify import Actor
from modules.input_clerk import InputClerk
from modules.compliance import ComplianceOfficer
from modules.janitor import Janitor

TASK_ROUTER = {
    "document_extract": InputClerk,
    "data_verify": ComplianceOfficer,
    "data_clean": Janitor,
}

async def main():
    async with Actor:
        input_data = await Actor.get_input() or {}

        task_type = input_data.get("task_type")
        if not task_type:
            await Actor.fail("No task_type specified")
            return

        handler_class = TASK_ROUTER.get(task_type)
        if not handler_class:
            await Actor.fail(f"Unknown task_type: {task_type}")
            return

        handler = handler_class(input_data)
        result = await handler.execute()
        await Actor.push_data(result)

if __name__ == "__main__":
    asyncio.run(main())
```

### 7.3 Dependencies

```txt
# requirements.txt
apify==1.8.0
google-genai==1.0.0
pydantic==2.10.5
python-magic==0.4.27
pypdf==5.4.0
thefuzz==0.20.0
phonenumbers==8.13.50
aiofiles==24.1.0
```

### 7.4 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Yes | Google Gemini API key |
| `APIFY_TOKEN` | Yes (local dev) | Apify API token |
| `ENRICHMENT_API_KEY` | No | External data enrichment API |

---

## 8. Security Considerations

### 8.1 Data Handling

- **In Transit:** All API calls use HTTPS/TLS 1.3
- **At Rest:** No sensitive data stored in Apify; transient processing only
- **Secrets:** API keys stored in Apify secrets, never in code

### 8.2 Validation Layers

1. **Input Validation:** Pydantic schemas validate all inputs before processing
2. **File Validation:** Magic byte checks, virus scanning (future)
3. **Output Sanitization:** Sensitive fields masked in logs

### 8.3 Privacy

- Documents processed in memory, not persisted
- API keys isolated per Actor run
- Audit logging for compliance tracking

---

## 9. Roadmap & Phases

### Phase 1: Foundation (v1.0) - Current

**Timeline:** January 2026

**Scope:**
- Module A core: Document extraction (invoices, forms)
- Module B core: Math verification, date validation
- Basic n8n integration templates
- Single Apify Actor deployment

**Deliverables:**
- [ ] Production Apify Actor
- [ ] Test suite (50+ test cases)
- [ ] Documentation (README, API docs)
- [ ] 3 n8n workflow templates

**Success Metrics:**
- 95%+ extraction accuracy on clean documents
- <5 second average processing time
- 90%+ of invoices fully automated (no human review)

### Phase 2: Enhancement (v1.1)

**Timeline:** February 2026

**Scope:**
- Module A: Handwriting support, multi-language
- Module B: Vendor list integration, GL code validation
- Module C: Core deduplication (beta)

**Deliverables:**
- Handwriting accuracy target: 85%
- Spanish language support
- Deduplication engine

### Phase 3: Scale (v1.2)

**Timeline:** March 2026

**Scope:**
- Module C: Full enrichment capabilities
- Batch processing for large datasets
- Custom rule builder (no-code)
- Webhook integrations

**Deliverables:**
- Enrichment API integrations
- Batch processing UI
- Rule management interface

### Future Considerations (v2.0)

- Custom model fine-tuning for domain-specific documents
- On-premise deployment option
- Multi-tenant architecture
- Enterprise SSO and audit logging

---

## 10. Appendix

### 10.1 Document Type Matrix

| Document Type | Module | Extraction | Verification | Cleaning |
|---------------|--------|------------|--------------|----------|
| Invoice | A | Full | Math, Date | N/A |
| Receipt | A | Full | Math | N/A |
| Lease | A | Full | Date | N/A |
| COI | A | Full | Expiration | N/A |
| Quote | A | Full | Math | N/A |
| Handwritten Form | A | Partial | Date | N/A |
| Contract | A | Clauses | N/A | N/A |
| Vendor List | C | N/A | N/A | Dedupe, Format |
| Contact Database | C | N/A | N/A | Dedupe, Enrich |

### 10.2 Error Codes

| Code | Meaning | Action |
|------|---------|--------|
| `ERR_INVALID_INPUT` | Malformed request | Fix request format |
| `ERR_INVALID_FILE` | Cannot process file type | Convert and retry |
| `ERR_EXTRACTION_FAILED` | Vision model error | Try fallback OCR |
| `ERR_VERIFICATION_FAILED` | Business rule violation | Manual review |
| `ERR_TIMEOUT` | Processing exceeded limit | Reduce scope/retry |

### 10.3 Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-01-07 | Initial PRD for EntryAI Platform |

---

## 11. Data Contract Enforcer (n8n Integration)

### 11.1 The "Weakest Link" Problem

This is the exact reason most Zapier/n8n agencies fail. If n8n receives `{ "cost": "1,000" }` (string with comma) but Airtable expects `1000.00` (number), the automation breaks **silently**.

**Solution:** Delegate the **"Data Contract Enforcer"** to Apify. Never trust n8n to format data.

### 11.2 The Three Rules of Output

| Rule | Description | Implementation |
|------|-------------|----------------|
| **Rule 1** | Pydantic is the Gatekeeper | No data leaves `main.py` unless it passes the Pydantic Schema |
| **Rule 2** | Flat JSON Only | n8n hates nested arrays. Complex data is flattened or JSON-stringified |
| **Rule 3** | Explicit Typing | Dates = ISO8601, Numbers = Floats, Booleans = true/false |

### 11.3 Serialization Layer Code

```python
def normalize_for_n8n(data: dict) -> dict:
    """
    Converts extracted data to n8n-compatible flat JSON.

    Guarantees:
    1. Dates -> ISO8601 Strings (YYYY-MM-DD)
    2. Floats -> Rounded to 2 decimals (no 10.000000001)
    3. Nested Lists -> JSON Strings (so Airtable doesn't split rows)
    4. None -> null (explicit, never omitted)
    """
    result = {}

    for key, value in data.items():
        if value is None:
            result[key] = None
            continue

        # Floats rounded to 2 decimals
        if isinstance(value, float):
            result[key] = round(value, 2)
            continue

        # Nested lists -> JSON strings
        if isinstance(value, list):
            if value and isinstance(value[0], (dict, list)):
                result[key] = json.dumps(value, default=str)
            else:
                result[key] = value
            continue

        # Nested dicts -> flattened key paths
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                if sub_value is None:
                    result[f"{key}_{sub_key}"] = None
                elif isinstance(sub_value, float):
                    result[f"{key}_{sub_key}"] = round(sub_value, 2)
                else:
                    result[f"{key}_{sub_key}"] = sub_value
            continue

        result[key] = value

    return result
```

### 11.4 Schema Test (CI/CD for Automation)

Before connecting to n8n, run this validation:

| Test | Input | Expected Output | Fail Condition |
|------|-------|-----------------|----------------|
| Date Format | "Jan 5th, 26" | `"2026-01-05"` (String) | `"01/05/26"` or `"Jan 5"` |
| Currency | "$1,500.75" | `1500.75` (Float) | `"$1,500.75"` (String) |
| Empty Field | Missing | `null` | Field omitted or `""` |
| Nested Data | `line_items: [...]` | `line_items: "[...]"` (String) | Array splitting rows |

### 11.5 Handling n8n "Drift"

What if Airtable changes a column name?

**Solution:** Use **"Mapping Nodes"** in n8n as a buffer.

```
# DON'T:
{{ $json.total }} -> Airtable "Total Cost"

# DO:
Set Node:
  Final_Total = {{ $json.total }}
  Final_Date = {{ $json.invoice_date }}
  Final_Vendor = {{ $json.vendor_name }}

Then map Final_* to Airtable
```

This buffer layer means if Actor code changes, you only update the Set node, not the entire workflow.

### 11.6 Final Integrity Checklist

| Check | Required Format | Verified |
|-------|-----------------|----------|
| Dates | YYYY-MM-DD | `date.isoformat()` |
| Currency | Raw number (150.50) | `clean_money_value()` |
| Empty Fields | `null` | Pydantic default |
| Nested Lists | JSON string | `json.dumps()` |
| Floats | 2 decimals max | `round(value, 2)` |

---

**Document Status:** Ready for Review
**Next Review:** 2026-01-14
**Owner:** Product Engineering
