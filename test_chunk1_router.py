"""
Chunk 1: Test Router Logic (Fast - no LLM calls)
Tests document type detection in isolation.
"""
import sys
sys.path.insert(0, "/home/aparna/Desktop/docuflow-headless")

from agent_graph import router_node

# Test cases for router
test_cases = [
    # COI documents
    ("coi_text", "Certificate of Insurance - Policy Period: 01/01/2025 to 12/31/2025\nNamed Insured: John Smith\nCertificate Holder: ABC Corp", "coi"),
    ("coi_text2", "LIABILITY INSURANCE CERTIFICATE\nPolicy Number: GL-2024-1234", "coi"),

    # Lease documents
    ("lease_text", "RESIDENTIAL LEASE AGREEMENT\nTenant Name: Jane Doe\nLandlord: Property Management Inc\nLease Term: 12 months", "lease"),
    ("lease_text2", "APARTMENT LEASE\nSecurity Deposit: $1500\nMonthly Rent: $2500", "lease"),

    # Quote documents
    ("quote_text", "QUOTE #12345\nPacific Flooring Solutions\nTotal Amount: $5,865.00", "quote"),
    ("quote_text2", "BID PROPOSAL\nEstimate for flooring work\nVendor: ABC Construction", "quote"),
]

print("="*50)
print("CHUNK 1: ROUTER LOGIC TEST")
print("="*50)

passed = 0
failed = 0

for name, text, expected in test_cases:
    result = router_node({"text_md": text})
    actual = result["doc_type"]
    status = "✓" if actual == expected else "✗"
    if actual == expected:
        passed += 1
    else:
        failed += 1
    print(f"{status} {name}: expected '{expected}', got '{actual}'")

print(f"\nResult: {passed}/{passed+failed} passed")
print(f"Router logic is {'WORKING' if failed == 0 else 'NEEDS FIXES'}")
