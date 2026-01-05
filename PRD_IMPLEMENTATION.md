# PropFlow Agent - PRD Implementation Documentation

## Overview

PropFlow Agent implements **Autonomous Intelligence** through a three-layer architecture:
1. **Router** - Intelligent document type detection
2. **Reasoning** - LLM-powered extraction with business logic
3. **Validation** - Pydantic schemas with embedded business rules

This document explains how each schema enforces business rules and implements the PRD requirements.

---

## Architecture: The "Autonomous Intelligence" Layer

### Philosophy

> "Apify is the Brain (Heavy Lift). n8n is the Limbs (Connectivity)."

The PropFlow Agent processes property documents and outputs **actionable data**, not just extracted text. Business logic is embedded directly in Pydantic schemas, ensuring that:

- **Compliance checks** happen automatically
- **Calculations** are verified or corrected
- **Critical flags** are set based on business rules
- **Data quality** is enforced at the schema level

### Processing Flow

```
PDF Document → OCR (Docling) → Router → Extraction (LLM) → Schema Validation → Actionable JSON
                                                              ↓
                                                    Business Logic Validators
                                                    (Rent Cap, True Cost, Policy Limits)
```

---

## Schema Business Logic Validators

### 1. LeaseSchema - Lease Auditor

**PRD Requirement:** "Calculate Notice Date = End Date - Notice Period. Flag Rent Cap %."

#### Fields

- `tenant_name: Optional[str]` - Name of the tenant (Optional to prevent hallucination)
- `end_date: Optional[date]` - Lease expiration date (Optional to prevent hallucination)
- `notice_period_days: Optional[int]` - Days of notice required (e.g., 60)
- `calculated_notice_date: Optional[date]` - Auto-calculated notice deadline
- `rent_cap_percentage: Optional[float]` - Rent increase cap percentage (e.g., 5.0 for 5%)
- `rent_cap_flagged: bool` - Auto-flag if rent cap is missing
- `warnings: List[str]` - Warnings about missing or uncertain data (prevents silent failures)

#### Business Logic Validators

**1. Notice Date Calculation (`calc_date_and_flag_rent_cap`)**
```python
@model_validator(mode='after')
def calc_date_and_flag_rent_cap(self):
    # Prevent silent failures - warn if critical fields are missing
    if self.tenant_name is None:
        self.warnings.append("Tenant name not found - Manual Review Needed")
    if self.end_date is None:
        self.warnings.append("Lease end date not found - Manual Review Needed")
    
    # Calculate notice date if we have the required fields
    if self.end_date is not None and self.notice_period_days is not None:
        if self.calculated_notice_date is None:
            self.calculated_notice_date = self.end_date - timedelta(days=self.notice_period_days)
    elif self.end_date is not None and self.notice_period_days is None:
        self.warnings.append("Notice period not found - Manual Review Needed. Cannot calculate notice date.")
    
    # Flag if rent cap is missing (important for compliance)
    if self.rent_cap_percentage is None:
        self.rent_cap_flagged = True
        self.warnings.append("Rent cap percentage not found - Compliance Risk")
    
    return self
```

**What it does:**
- **Prevents hallucination**: Fields are Optional, missing fields generate warnings
- Ensures `calculated_notice_date` is calculated when possible
- Flags leases without rent cap information (compliance risk)
- Adds warnings for missing critical data (no silent failures)
- Enables n8n to create calendar events: "Notice Due: Unit 4B" on `calculated_notice_date`

**Example Output:**
```json
{
  "doc_type": "lease",
  "tenant_name": "John Smith",
  "end_date": "2024-12-31",
  "notice_period_days": 60,
  "calculated_notice_date": "2024-11-01",
  "rent_cap_percentage": null,
  "rent_cap_flagged": true,
  "warnings": ["Rent cap percentage not found - Compliance Risk"]
}
```

**Example with Missing Fields:**
```json
{
  "doc_type": "lease",
  "tenant_name": null,
  "end_date": "2024-12-31",
  "notice_period_days": null,
  "calculated_notice_date": null,
  "rent_cap_percentage": null,
  "rent_cap_flagged": true,
  "warnings": [
    "Tenant name not found - Manual Review Needed",
    "Notice period not found - Manual Review Needed. Cannot calculate notice date.",
    "Rent cap percentage not found - Compliance Risk"
  ]
}
```

---

### 2. QuoteSchema - Bid Leveler

**PRD Requirement:** "Find hidden fees. Standardize line items. Rank by 'True Cost'."

#### Fields

- `vendor_name: Optional[str]` - Name of the vendor (Optional to prevent hallucination)
- `total_amount: Optional[float]` - Base quote amount (Optional to prevent hallucination)
- `hidden_fees_found: bool` - True if fees like 'haul-away' are excluded
- `line_items_standardized: List[str]` - Standardized line items
- `true_cost: Optional[float]` - Calculated total including hidden fees
- `warnings: List[str]` - Warnings about missing or uncertain data

#### Business Logic Validators

**1. True Cost Calculation (`calc_true_cost`)**
```python
@model_validator(mode='after')
def calc_true_cost(self):
    # Prevent silent failures - warn if critical fields are missing
    if self.vendor_name is None:
        self.warnings.append("Vendor name not found - Manual Review Needed")
    if self.total_amount is None:
        self.warnings.append("Total amount not found - Manual Review Needed")
        self.true_cost = None
        return self
    
    # Calculate true cost including hidden fees for bid comparison
    if self.true_cost is None:
        if self.hidden_fees_found:
            # Estimate hidden fees as 10% of total (conservative estimate)
            estimated_hidden = self.total_amount * 0.10
            self.true_cost = self.total_amount + estimated_hidden
        else:
            self.true_cost = self.total_amount
    return self
```

**What it does:**
- Calculates the "true cost" including estimated hidden fees
- Enables **bid ranking** functionality: compare quotes by `true_cost`, not just `total_amount`
- Standardizes comparison across vendors with different fee structures
- Enables n8n to create comparison tables: "Rank by True Cost"

**Example Output:**
```json
{
  "doc_type": "quote",
  "vendor_name": "ACME Plumbing",
  "total_amount": 1000.0,
  "hidden_fees_found": true,
  "line_items_standardized": ["Labor: $500", "Materials: $500"],
  "true_cost": 1100.0
}
```

**Bid Ranking Example:**
```python
quotes = [quote1, quote2, quote3]  # All QuoteSchema instances
sorted_by_true_cost = sorted(quotes, key=lambda q: q.true_cost)
# Now you can rank bids accurately, accounting for hidden fees
```

---

### 3. CoiSchema - COI Watchdog

**PRD Requirement:** "Check if Expiration < Today + 30. Check Policy Limit > $1M."

#### Fields

- `expiration_date: Optional[date]` - Insurance expiration date (Optional to prevent hallucination)
- `policy_limit: Optional[float]` - Policy limit in dollars
- `is_critical: bool` - Auto-flag if expiring soon OR policy limit too low
- `policy_limit_flagged: bool` - Auto-flag if policy limit < $1M
- `warnings: List[str]` - Warnings about missing or uncertain data

#### Business Logic Validators

**1. Critical Status & Policy Limit Check (`check_critical_and_policy_limit`)**
```python
@model_validator(mode='after')
def check_critical_and_policy_limit(self):
    # Prevent silent failures - warn if critical fields are missing
    if self.expiration_date is None:
        self.warnings.append("Expiration date not found - Manual Review Needed")
        self.is_critical = True  # Mark as critical if we can't verify expiration
        return self
    
    # PRD: "Check if Expiration < Today + 30. Check Policy Limit > $1M"
    days_left = (self.expiration_date - date.today()).days
    
    # Auto-flag if expiring in < 30 days
    if days_left < 30:
        self.is_critical = True
    
    # Check policy limit - flag if below $1M
    if self.policy_limit is None:
        self.warnings.append("Policy limit not found - Manual Review Needed")
    elif self.policy_limit < 1_000_000:
        self.policy_limit_flagged = True
        self.is_critical = True  # Also mark as critical if policy limit too low
    
    return self
```

**What it does:**
- **Prevents hallucination**: Fields are Optional, missing fields generate warnings
- Flags COIs expiring within 30 days (urgent renewal needed)
- Flags COIs with policy limits below $1M (inadequate coverage)
- Sets `is_critical = True` for either condition
- Adds warnings for missing critical data (no silent failures)
- Enables n8n to send Slack alerts: "CRITICAL: Plumber insurance expiring!"

**Example Outputs:**

**Expiring Soon:**
```json
{
  "doc_type": "coi",
  "expiration_date": "2024-02-15",
  "policy_limit": 2000000.0,
  "is_critical": true,
  "policy_limit_flagged": false
}
```

**Low Policy Limit:**
```json
{
  "doc_type": "coi",
  "expiration_date": "2024-12-31",
  "policy_limit": 500000.0,
  "is_critical": true,
  "policy_limit_flagged": true
}
```

---

## Router Logic

The router uses simple heuristics to identify document types:

```python
def router_node(state):
    text = state['text_md'].lower()[:1000]
    if "lease" in text or "tenant" in text: 
        return {"doc_type": "lease"}
    if "estimate" in text or "quote" in text: 
        return {"doc_type": "quote"}
    if "certificate of liability" in text: 
        return {"doc_type": "coi"}
    return {"doc_type": "unknown"}
```

**Why this works:**
- Property management documents have distinct keywords
- Fast and reliable (no LLM call needed)
- Can be enhanced with mini-LLM call if needed for edge cases

---

## Extraction Node Pattern

The extraction node follows the PRD pattern, structured for easy migration from Ollama (dev) to DeepInfra (production):

**Current (Dev):** Ollama with manual JSON parsing  
**Future (Prod):** DeepInfra with `with_structured_output`

### Critical: ValidationError Handling

**Important**: The extraction node now catches `ValidationError` specifically to prevent crashes:

```python
try:
    validated = target_schema(**data)
    return {"final_data": validated.model_dump(mode='json')}
except ValidationError as e:
    # Return validation errors as structured data, don't crash
    return {
        "final_data": {
            "status": "validation_error",
            "doc_type": state['doc_type'],
            "errors": e.errors(),
            "partial_data": data,  # Include what we did extract
            "message": "Schema validation failed - some fields may be missing or invalid"
        }
    }
```

This ensures:
- ✅ Partial success instead of complete failure
- ✅ Error details included for debugging
- ✅ Partial data preserved (what was successfully extracted)
- ✅ No silent crashes

**Model Selection (PRD Pattern):**
- Complex docs (lease, quote): `deepseek-ai/DeepSeek-V3`
- Simple docs (COI): `google/gemma-3-12b-it` (cheaper)

---

## n8n Integration Examples

> ⚠️ **CRITICAL**: Set n8n Apify Node timeout to **300000ms** (5 minutes) for large documents.  
> See [N8N_INTEGRATION_GUIDE.md](N8N_INTEGRATION_GUIDE.md) for complete setup instructions.

### Lease → Google Calendar

**Trigger:** `doc_type == "lease"`  
**Status Check:** `status == "success"` (handle `partial_success` separately)

**Action:** Create calendar event
- Title: `"Lease Renewal: {{tenant_name}}"`
- Date: `{{calculated_notice_date}}`
- Alert if: `rent_cap_flagged == true`
- **Warnings**: Check `warnings` array - if not empty, flag for manual review

### Quote → Google Sheets

**Trigger:** `doc_type == "quote"`
**Action:** Add row to comparison sheet
- Columns: `vendor_name`, `total_amount`, `true_cost`, `hidden_fees_found`
- Sort by: `true_cost` (ascending)

### COI → Slack Alert

**Trigger:** `doc_type == "coi" AND is_critical == true`  
**Status Check:** `status == "success"` OR `status == "partial_success"`

**Action:** Send Slack message
- Channel: `#urgent-alerts`
- Message: `"CRITICAL: {{vendor_name}} insurance expiring on {{expiration_date}}!"`
- If `policy_limit_flagged`: Include policy limit warning
- **Warnings**: Include `warnings` array in message if present

### Handling Partial Success

**Status:** `partial_success` (validation errors but some data extracted)

**Action:** 
- Send to manual review workflow
- Include `warnings` and `partial_data` for review
- Don't create calendar events or alerts (data incomplete)

---

## Testing

All business logic validators are tested in `test_prd_features.py`:

- ✅ Rent cap flagging
- ✅ True cost calculation
- ✅ Policy limit validation
- ✅ Critical status flags

Run tests:
```bash
uv run python test_prd_features.py
```

---

## Migration Path: Ollama → DeepInfra

The code is structured for easy migration:

1. **Replace Ollama LLM** with `ChatOpenAI` (DeepInfra endpoint)
2. **Use `with_structured_output`** instead of manual JSON parsing
3. **Update model names** per PRD specification

See comments in `agent_graph.py` extraction_node for migration guide.

---

## Key Differentiators

1. **Business Logic in Schemas** - Not just extraction, but validation and calculation
2. **Autonomous Actions** - Outputs actionable data, not just text
3. **Compliance Built-In** - Rent caps, policy limits checked automatically
4. **Bid Ranking** - True cost calculation enables fair comparison

This is not a prototype; it's a **defensible, logic-driven Vertical AI product**.

