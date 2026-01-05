"""
Test script to verify PropFlow Agent transformation matches PRD requirements.

Tests:
1. Router correctly identifies lease, quote, and COI documents
2. Schemas validate correctly with business logic
3. Both docUrl and docUrls input formats work
"""
import asyncio
from datetime import date, timedelta
from schemas import LeaseSchema, QuoteSchema, CoiSchema
from agent_graph import router_node


def test_lease_schema_business_logic():
    """Test LeaseSchema calculates notice date correctly."""
    print("\n🧪 Testing LeaseSchema business logic...")
    
    lease_data = {
        "doc_type": "lease",
        "tenant_name": "John Doe",
        "end_date": "2024-12-31",
        "notice_period_days": 60
    }
    
    lease = LeaseSchema(**lease_data)
    
    # Verify calculated_notice_date is set
    assert lease.calculated_notice_date is not None, "calculated_notice_date should be calculated"
    expected_date = date(2024, 12, 31) - timedelta(days=60)
    assert lease.calculated_notice_date == expected_date, f"Expected {expected_date}, got {lease.calculated_notice_date}"
    
    print(f"   ✅ calculated_notice_date: {lease.calculated_notice_date}")
    print("   ✅ LeaseSchema business logic works correctly")


def test_coi_schema_business_logic():
    """Test CoiSchema flags critical expiration correctly."""
    print("\n🧪 Testing CoiSchema business logic...")
    
    # Test critical (expiring in < 30 days)
    coi_critical = CoiSchema(
        doc_type="coi",
        expiration_date=date.today() + timedelta(days=15)
    )
    assert coi_critical.is_critical == True, "COI expiring in 15 days should be critical"
    print(f"   ✅ Critical COI flagged: is_critical={coi_critical.is_critical}")
    
    # Test non-critical (expiring in > 30 days)
    coi_safe = CoiSchema(
        doc_type="coi",
        expiration_date=date.today() + timedelta(days=60)
    )
    assert coi_safe.is_critical == False, "COI expiring in 60 days should not be critical"
    print(f"   ✅ Non-critical COI: is_critical={coi_safe.is_critical}")
    
    print("   ✅ CoiSchema business logic works correctly")


def test_quote_schema():
    """Test QuoteSchema structure."""
    print("\n🧪 Testing QuoteSchema...")
    
    quote_data = {
        "doc_type": "quote",
        "vendor_name": "ACME Plumbing",
        "total_amount": 1250.50,
        "hidden_fees_found": True,
        "line_items_standardized": ["Labor: $500", "Materials: $750.50"]
    }
    
    quote = QuoteSchema(**quote_data)
    assert quote.vendor_name == "ACME Plumbing"
    assert quote.total_amount == 1250.50
    assert quote.hidden_fees_found == True
    
    print("   ✅ QuoteSchema validates correctly")


def test_router_logic():
    """Test router_node identifies document types correctly."""
    print("\n🧪 Testing router logic...")
    
    test_cases = [
        ("This is a lease agreement for tenant John Doe", "lease"),
        ("Tenant agreement signed", "lease"),
        ("Quote for plumbing services", "quote"),
        ("Estimate for repair work", "quote"),
        ("Certificate of liability insurance", "coi"),
        ("Random document text", "unknown")
    ]
    
    for text, expected_type in test_cases:
        state = {"text_md": text}
        result = router_node(state)
        assert result["doc_type"] == expected_type, \
            f"Expected {expected_type} for '{text[:50]}...', got {result['doc_type']}"
        print(f"   ✅ '{text[:40]}...' -> {result['doc_type']}")
    
    print("   ✅ Router logic works correctly")


def test_input_format_compatibility():
    """Test that main.py supports both docUrl and docUrls formats."""
    print("\n🧪 Testing input format compatibility...")
    
    # Verify code structure by reading main.py
    with open("main.py", "r") as f:
        main_code = f.read()
    
    # Check that both formats are supported
    assert 'docUrl' in main_code, "main.py should support docUrl (PRD format)"
    assert 'docUrls' in main_code, "main.py should support docUrls (backward compat)"
    assert 'input_data.get("docUrl")' in main_code or 'input_data.get(\'docUrl\')' in main_code, \
        "main.py should check for docUrl"
    assert 'input_data.get("docUrls"' in main_code or 'input_data.get(\'docUrls\'' in main_code, \
        "main.py should check for docUrls"
    
    print("   ✅ Input format compatibility verified (code structure supports both)")
    print("   ✅ Both docUrl and docUrls formats are supported")


async def run_all_tests():
    """Run all transformation verification tests."""
    print("=" * 60)
    print("PropFlow Agent Transformation Verification Tests")
    print("=" * 60)
    
    try:
        test_lease_schema_business_logic()
        test_coi_schema_business_logic()
        test_quote_schema()
        test_router_logic()
        test_input_format_compatibility()
        
        print("\n" + "=" * 60)
        print("✅ All transformation tests passed!")
        print("=" * 60)
        return True
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)

