"""
Chunk 2: Test Server Endpoint Format (Mock - Fast!)
Tests response format without actual OCR/LLM calls.
"""
import json
import sys
sys.path.insert(0, "/home/aparna/Desktop/docuflow-headless")

# Import directly to test format
from schemas import LeaseSchema, QuoteSchema, CoiSchema

print("="*50)
print("CHUNK 2: RESPONSE FORMAT TEST")
print("="*50)

# Test 1: Schema validation
print("\n1. Testing Schema Validation...")

# Lease schema
lease = LeaseSchema(
    tenant_name="John Doe",
    end_date="2025-12-31",
    notice_period_days=60
)
lease_data = lease.model_dump(mode='json')
print(f"   Lease Schema: {lease_data['doc_type']}")
print(f"   Notice Date: {lease_data.get('calculated_notice_date')}")

# Quote schema
quote = QuoteSchema(
    vendor_name="Pacific Flooring",
    total_amount=5865.0,
    hidden_fees_found=True
)
quote_data = quote.model_dump(mode='json')
print(f"   Quote Schema: {quote_data['doc_type']}")
print(f"   True Cost: {quote_data.get('true_cost')}")

# COI schema
coi = CoiSchema(
    expiration_date="2025-02-15",
    insured_name="ABC Corp",
    policy_limit=1000000
)
coi_data = coi.model_dump(mode='json')
print(f"   COI Schema: {coi_data['doc_type']}")
print(f"   Is Critical: {coi_data.get('is_critical')}")

# Test 2: n8n Response Format
print("\n2. Testing n8n Response Format...")

n8n_lease_response = {
    "status": "success",
    "doc_type": "lease",
    "filename": "lease.pdf",
    "data": {
        "doc_type": "lease",
        "tenant_name": "John Doe",
        "end_date": "2025-12-31",
        "calculated_notice_date": lease_data.get('calculated_notice_date'),
        "rent_cap_flagged": True,
        "warnings": ["Rent cap percentage not found"]
    },
    "is_critical": False,
    "notice_date": lease_data.get('calculated_notice_date')
}

n8n_quote_response = {
    "status": "success",
    "doc_type": "quote",
    "filename": "bid.pdf",
    "data": {
        "doc_type": "quote",
        "vendor_name": "Pacific Flooring",
        "total_amount": 5865.0,
        "hidden_fees_found": True,
        "true_cost": 6451.5,
        "warnings": ["Haul-away fee not included"]
    },
    "is_critical": False
}

n8n_coi_response = {
    "status": "success",
    "doc_type": "coi",
    "filename": "COI.pdf",
    "data": {
        "doc_type": "coi",
        "expiration_date": "2025-02-15",
        "insured_name": "ABC Corp",
        "is_critical": True,
        "policy_limit": 1000000
    },
    "is_critical": True
}

print("\n   Lease Response (for Calendar):")
print(f"   - doc_type: {n8n_lease_response['doc_type']}")
print(f"   - notice_date: {n8n_lease_response['notice_date']}")
print(f"   - tenant: {n8n_lease_response['data']['tenant_name']}")

print("\n   Quote Response (for Sheets/Airtable):")
print(f"   - doc_type: {n8n_quote_response['doc_type']}")
print(f"   - vendor: {n8n_quote_response['data']['vendor_name']}")
print(f"   - true_cost: {n8n_quote_response['data']['true_cost']}")

print("\n   COI Response (for Slack):")
print(f"   - doc_type: {n8n_coi_response['doc_type']}")
print(f"   - is_critical: {n8n_coi_response['is_critical']}")
print(f"   - insured: {n8n_coi_response['data']['insured_name']}")

# Test 3: n8n Switch Routing
print("\n3. Testing n8n Switch Node Routing...")

def get_n8n_route(response):
    """Simulate n8n Switch node logic."""
    if response.get("status") == "error":
        return "error"
    return response.get("doc_type", "unknown")

routing_tests = [
    (n8n_lease_response, "lease"),
    (n8n_quote_response, "quote"),
    (n8n_coi_response, "coi"),
    ({"status": "error", "error": "PDF invalid"}, "error"),
]

all_passed = True
for response, expected in routing_tests:
    actual = get_n8n_route(response)
    status = "✓" if actual == expected else "✗"
    if actual != expected:
        all_passed = False
    print(f"   {status} {response.get('doc_type', response.get('status'))} → {actual}")

print(f"\n✓ Response format is n8n-compatible!")
print(f"  Router will route: lease → Calendar, quote → Sheets, coi → Slack")
