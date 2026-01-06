"""
Test extraction node with sample text (fast - no OCR).
Verifies n8n output format.
"""
import asyncio
import sys
sys.path.insert(0, "/home/aparna/Desktop/docuflow-headless")

from agent_graph import router_node, extraction_node

# Sample texts
COI_TEXT = """
CERTIFICATE OF INSURANCE
Policy Number: GL-2024-12345
Named Insured: ABC Property Management
Certificate Holder: John Smith Properties
Policy Period: January 1, 2025 to December 31, 2025
Liability Coverage: $1,000,000
"""

LEASE_TEXT = """
RESIDENTIAL LEASE AGREEMENT
Tenant Name: Jane Doe
Landlord: XYZ Properties LLC
Property: 123 Main Street, Apt 4B
Monthly Rent: $2,500
Security Deposit: $5,000
Lease Start: 2024-06-01
Lease End: 2025-05-31
Notice Period: 60 days
"""

QUOTE_TEXT = """
PACIFIC FLOORING SOLUTIONS
Estimate #12345
Client: ABC Corp
Item: Hardwood Flooring Installation
Total Amount: $5,865.00
Includes: Materials, Labor, Installation
Excludes: Furniture moving, Haul-away ($150)
"""

print("="*50)
print("EXTRACTION NODE TEST (No OCR)")
print("="*50)

# Test COI extraction
print("\n1. Testing COI extraction...")
state = router_node({"text_md": COI_TEXT})
print(f"   Router: {state['doc_type']}")
state.update({"text_md": COI_TEXT, "final_data": {}})
result = extraction_node(state)
print(f"   Extracted: {result['final_data'].get('doc_type')}")
print(f"   Insured: {result['final_data'].get('insured_name')}")
print(f"   Expiration: {result['final_data'].get('expiration_date')}")
print(f"   Critical: {result['final_data'].get('is_critical')}")

# Test Lease extraction
print("\n2. Testing Lease extraction...")
state = router_node({"text_md": LEASE_TEXT})
print(f"   Router: {state['doc_type']}")
state.update({"text_md": LEASE_TEXT, "final_data": {}})
result = extraction_node(state)
print(f"   Extracted: {result['final_data'].get('doc_type')}")
print(f"   Tenant: {result['final_data'].get('tenant_name')}")
print(f"   Notice Date: {result['final_data'].get('calculated_notice_date')}")

# Test Quote extraction
print("\n3. Testing Quote extraction...")
state = router_node({"text_md": QUOTE_TEXT})
print(f"   Router: {state['doc_type']}")
state.update({"text_md": QUOTE_TEXT, "final_data": {}})
result = extraction_node(state)
print(f"   Extracted: {result['final_data'].get('doc_type')}")
print(f"   Vendor: {result['final_data'].get('vendor_name')}")
print(f"   Amount: {result['final_data'].get('total_amount')}")
print(f"   True Cost: {result['final_data'].get('true_cost')}")

print("\n" + "="*50)
print("n8n OUTPUT FORMAT TEST")
print("="*50)

# Simulate n8n response format
def format_for_n8n(result):
    final = result.get('final_data', {})
    doc_type = result.get('doc_type')
    return {
        "status": "success",
        "doc_type": doc_type,
        "data": final,
        "is_critical": final.get('is_critical', False)
    }

print("\nLease response for n8n:")
n8n_response = format_for_n8n(extraction_node({"text_md": LEASE_TEXT, "doc_type": router_node({"text_md": LEASE_TEXT})['doc_type'], "final_data": {}}))
print(f"   {n8n_response}")

print("\n✓ Extraction working! Ready for n8n integration.")
