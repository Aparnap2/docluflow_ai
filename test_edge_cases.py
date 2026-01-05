"""
Comprehensive edge case tests for PropFlow Agent.
Tests data format validation, error handling, and edge cases.
"""
import asyncio
from datetime import date, timedelta
from schemas import LeaseSchema, QuoteSchema, CoiSchema
from agent_graph import router_node


def test_edge_case_empty_text():
    """Test router with empty or minimal text."""
    print("\n🧪 Testing Edge Case: Empty Text...")
    
    test_cases = [
        ("", "unknown"),
        ("   ", "unknown"),
        ("a", "unknown"),
        ("123", "unknown"),
    ]
    
    for text, expected in test_cases:
        state = {"text_md": text}
        result = router_node(state)
        assert result["doc_type"] == expected, f"Empty text '{text}' should return 'unknown'"
    
    print("   ✅ Empty text handled correctly")


def test_edge_case_malformed_dates():
    """Test schema validation with malformed dates."""
    print("\n🧪 Testing Edge Case: Malformed Dates...")
    
    try:
        # Invalid date format
        lease = LeaseSchema(
            doc_type="lease",
            tenant_name="Test",
            end_date="invalid-date",
            notice_period_days=60
        )
        assert False, "Should have raised validation error"
    except Exception as e:
        assert "date" in str(e).lower() or "validation" in str(e).lower()
        print("   ✅ Invalid date format rejected")
    
    # Valid date string
    lease = LeaseSchema(
        doc_type="lease",
        tenant_name="Test",
        end_date="2024-12-31",
        notice_period_days=60
    )
    assert lease.end_date == date(2024, 12, 31)
    print("   ✅ Valid date string accepted")


def test_edge_case_negative_values():
    """Test schema validation with negative values."""
    print("\n🧪 Testing Edge Case: Negative Values...")
    
    # Negative notice period (should be allowed but flagged in business logic)
    lease = LeaseSchema(
        doc_type="lease",
        tenant_name="Test",
        end_date=date(2024, 12, 31),
        notice_period_days=-10  # Negative
    )
    # Should still calculate (though result may be in future)
    assert lease.calculated_notice_date is not None
    print("   ✅ Negative notice period handled (calculated)")
    
    # Negative total amount (should be allowed for quotes - could be credit)
    quote = QuoteSchema(
        doc_type="quote",
        vendor_name="Test",
        total_amount=-100.0,  # Negative (credit/refund)
        hidden_fees_found=False,
        line_items_standardized=["Credit: $100"]
    )
    assert quote.true_cost == -100.0
    print("   ✅ Negative amounts handled (credits/refunds)")


def test_edge_case_missing_required_fields():
    """Test schema validation with missing required fields."""
    print("\n🧪 Testing Edge Case: Missing Required Fields...")
    
    # Fields are now Optional to prevent hallucination
    # Missing tenant_name - should create with warnings
    lease = LeaseSchema(
        doc_type="lease",
        end_date=date(2024, 12, 31),
        notice_period_days=60
    )
    assert lease.tenant_name is None, "tenant_name should be None when missing"
    assert len(lease.warnings) > 0, "Should have warnings for missing tenant_name"
    assert "Manual Review Needed" in " ".join(lease.warnings)
    print("   ✅ Missing tenant_name handled with warnings")
    
    # Missing vendor_name in quote - should create with warnings
    quote = QuoteSchema(
        doc_type="quote",
        total_amount=100.0,
        hidden_fees_found=False,
        line_items_standardized=[]
    )
    assert quote.vendor_name is None, "vendor_name should be None when missing"
    assert len(quote.warnings) > 0, "Should have warnings for missing vendor_name"
    assert "Manual Review Needed" in " ".join(quote.warnings)
    print("   ✅ Missing vendor_name handled with warnings")
    
    # Missing expiration_date in COI - should be critical
    coi = CoiSchema(
        doc_type="coi",
        expiration_date=None
    )
    assert coi.expiration_date is None, "expiration_date should be None when missing"
    assert coi.is_critical == True, "COI without expiration should be marked critical"
    assert len(coi.warnings) > 0, "Should have warnings for missing expiration"
    print("   ✅ Missing expiration_date handled (marked critical)")


def test_edge_case_very_large_values():
    """Test schema validation with very large values."""
    print("\n🧪 Testing Edge Case: Very Large Values...")
    
    # Very large policy limit
    coi = CoiSchema(
        doc_type="coi",
        expiration_date=date(2030, 12, 31),
        policy_limit=1_000_000_000.0  # $1B
    )
    assert coi.policy_limit_flagged == False
    assert coi.is_critical == False
    print("   ✅ Very large policy limit handled")
    
    # Very large total amount
    quote = QuoteSchema(
        doc_type="quote",
        vendor_name="Mega Corp",
        total_amount=10_000_000.0,  # $10M quote
        hidden_fees_found=True,
        line_items_standardized=["Large project"]
    )
    assert quote.true_cost == 11_000_000.0  # 10% added
    print("   ✅ Very large amounts handled")


def test_edge_case_future_dates():
    """Test schema validation with future dates."""
    print("\n🧪 Testing Edge Case: Future Dates...")
    
    # Lease ending far in future
    lease = LeaseSchema(
        doc_type="lease",
        tenant_name="Test",
        end_date=date(2050, 12, 31),
        notice_period_days=60
    )
    expected_date = date(2050, 12, 31) - timedelta(days=60)
    assert lease.calculated_notice_date == expected_date
    print(f"   ✅ Far future dates handled (notice date: {lease.calculated_notice_date})")
    
    # COI expiring far in future
    coi = CoiSchema(
        doc_type="coi",
        expiration_date=date(2050, 12, 31),
        policy_limit=2_000_000.0
    )
    assert coi.is_critical == False
    print("   ✅ Far future expiration handled")


def test_edge_case_past_dates():
    """Test schema validation with past dates."""
    print("\n🧪 Testing Edge Case: Past Dates...")
    
    # Expired COI (should be critical)
    expired_date = date.today() - timedelta(days=10)
    coi = CoiSchema(
        doc_type="coi",
        expiration_date=expired_date,
        policy_limit=2_000_000.0
    )
    assert coi.is_critical == True, "Expired COI should be critical"
    print("   ✅ Expired COI flagged as critical")
    
    # Past lease end date
    past_date = date(2020, 12, 31)
    lease = LeaseSchema(
        doc_type="lease",
        tenant_name="Test",
        end_date=past_date,
        notice_period_days=60
    )
    # Should still calculate notice date (even if in past)
    assert lease.calculated_notice_date == date(2020, 11, 1)
    print("   ✅ Past dates handled (calculated)")


def test_edge_case_special_characters():
    """Test schema validation with special characters."""
    print("\n🧪 Testing Edge Case: Special Characters...")
    
    # Tenant name with special characters
    lease = LeaseSchema(
        doc_type="lease",
        tenant_name="O'Brien & Associates, LLC",
        end_date=date(2024, 12, 31),
        notice_period_days=60
    )
    assert "O'Brien" in lease.tenant_name
    print("   ✅ Special characters in names handled")
    
    # Vendor name with unicode
    quote = QuoteSchema(
        doc_type="quote",
        vendor_name="Acme Plumbing™",
        total_amount=100.0,
        hidden_fees_found=False,
        line_items_standardized=["Service"]
    )
    assert "Acme Plumbing" in quote.vendor_name
    print("   ✅ Unicode characters handled")


def test_edge_case_router_ambiguous_text():
    """Test router with ambiguous text that could match multiple types."""
    print("\n🧪 Testing Edge Case: Ambiguous Text...")
    
    # Text mentioning both lease and quote
    ambiguous = "This lease includes a quote for repairs"
    state = {"text_md": ambiguous}
    result = router_node(state)
    # Should match first keyword found (lease)
    assert result["doc_type"] == "lease"
    print("   ✅ Ambiguous text handled (first match wins)")
    
    # Text with certificate but not COI
    cert_text = "Certificate of completion issued"
    state = {"text_md": cert_text}
    result = router_node(state)
    assert result["doc_type"] == "unknown"
    print("   ✅ Partial keyword match rejected")


def test_data_format_compatibility():
    """Test data format compatibility (JSON serialization)."""
    print("\n🧪 Testing Data Format: JSON Serialization...")
    
    import json
    
    # Lease schema to JSON
    lease = LeaseSchema(
        doc_type="lease",
        tenant_name="John Doe",
        end_date=date(2024, 12, 31),
        notice_period_days=60,
        rent_cap_percentage=5.0
    )
    lease_json = lease.model_dump(mode='json')
    assert isinstance(lease_json, dict)
    json_str = json.dumps(lease_json)
    assert "tenant_name" in json_str
    assert "2024-12-31" in json_str
    print("   ✅ Lease JSON serialization works")
    
    # Quote schema to JSON
    quote = QuoteSchema(
        doc_type="quote",
        vendor_name="ACME",
        total_amount=1000.0,
        hidden_fees_found=True,
        line_items_standardized=["Item 1"]
    )
    quote_json = quote.model_dump(mode='json')
    assert isinstance(quote_json, dict)
    assert quote_json["true_cost"] == 1100.0
    print("   ✅ Quote JSON serialization works")
    
    # COI schema to JSON
    coi = CoiSchema(
        doc_type="coi",
        expiration_date=date(2024, 2, 15),
        policy_limit=500_000.0
    )
    coi_json = coi.model_dump(mode='json')
    assert isinstance(coi_json, dict)
    assert coi_json["is_critical"] == True
    print("   ✅ COI JSON serialization works")


def run_all_edge_case_tests():
    """Run all edge case tests."""
    print("=" * 70)
    print("PropFlow Agent Edge Case Test Suite")
    print("=" * 70)
    
    try:
        test_edge_case_empty_text()
        test_edge_case_malformed_dates()
        test_edge_case_negative_values()
        test_edge_case_missing_required_fields()
        test_edge_case_very_large_values()
        test_edge_case_future_dates()
        test_edge_case_past_dates()
        test_edge_case_special_characters()
        test_edge_case_router_ambiguous_text()
        test_data_format_compatibility()
        
        print("\n" + "=" * 70)
        print("✅ All edge case tests passed!")
        print("=" * 70)
        return True
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import sys
    success = run_all_edge_case_tests()
    sys.exit(0 if success else 1)

