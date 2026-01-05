"""
Test PRD-specific features: rent cap flagging, true cost calculation, policy limit validation.
"""
from datetime import date, timedelta
from schemas import LeaseSchema, QuoteSchema, CoiSchema


def test_lease_rent_cap_flagging():
    """Test LeaseSchema rent cap flagging logic (PRD requirement)."""
    print("\n🧪 Testing LeaseSchema Rent Cap Flagging...")
    
    # Test 1: Lease without rent cap (should be flagged)
    lease_no_cap = LeaseSchema(
        doc_type="lease",
        tenant_name="John Doe",
        end_date=date(2024, 12, 31),
        notice_period_days=60
    )
    assert lease_no_cap.rent_cap_flagged == True, "Lease without rent cap should be flagged"
    assert "Compliance Risk" in " ".join(lease_no_cap.warnings), "Should warn about missing rent cap"
    print(f"   ✅ Missing rent cap flagged: {lease_no_cap.rent_cap_flagged}")
    
    # Test 2: Lease with rent cap (should not be flagged)
    lease_with_cap = LeaseSchema(
        doc_type="lease",
        tenant_name="Jane Smith",
        end_date=date(2024, 12, 31),
        notice_period_days=60,
        rent_cap_percentage=5.0
    )
    assert lease_with_cap.rent_cap_flagged == False, "Lease with rent cap should not be flagged"
    print(f"   ✅ Rent cap present: {lease_with_cap.rent_cap_percentage}%, flagged: {lease_with_cap.rent_cap_flagged}")
    
    # Test 3: Notice date calculation still works
    assert lease_with_cap.calculated_notice_date == date(2024, 11, 1)
    print(f"   ✅ Notice date calculated: {lease_with_cap.calculated_notice_date}")
    
    # Test 4: Missing notice period (should warn)
    lease_no_notice = LeaseSchema(
        doc_type="lease",
        tenant_name="Test",
        end_date=date(2024, 12, 31),
        notice_period_days=None
    )
    assert len(lease_no_notice.warnings) > 0, "Should warn about missing notice period"
    assert "Manual Review Needed" in " ".join(lease_no_notice.warnings)
    print(f"   ✅ Missing notice period warns: {lease_no_notice.warnings}")
    
    print("   ✅ Rent cap flagging works correctly")


def test_quote_true_cost_calculation():
    """Test QuoteSchema true cost calculation (PRD requirement for bid ranking)."""
    print("\n🧪 Testing QuoteSchema True Cost Calculation...")
    
    # Test 1: Quote without hidden fees (true_cost = total_amount)
    quote_no_hidden = QuoteSchema(
        doc_type="quote",
        vendor_name="ACME Plumbing",
        total_amount=1000.0,
        hidden_fees_found=False,
        line_items_standardized=["Labor: $500", "Materials: $500"]
    )
    assert quote_no_hidden.true_cost == 1000.0, "Quote without hidden fees should have true_cost = total_amount"
    print(f"   ✅ No hidden fees: true_cost = ${quote_no_hidden.true_cost}")
    
    # Test 2: Quote with hidden fees (true_cost = total_amount + 10%)
    quote_with_hidden = QuoteSchema(
        doc_type="quote",
        vendor_name="XYZ Services",
        total_amount=1000.0,
        hidden_fees_found=True,
        line_items_standardized=["Labor: $500", "Materials: $500"]
    )
    expected_true_cost = 1000.0 + (1000.0 * 0.10)  # 10% estimate
    assert quote_with_hidden.true_cost == expected_true_cost, \
        f"Quote with hidden fees should have true_cost = ${expected_true_cost}"
    print(f"   ✅ Hidden fees found: true_cost = ${quote_with_hidden.true_cost} (includes 10% estimate)")
    
    # Test 3: Multiple quotes can be ranked by true_cost
    quotes = [
        QuoteSchema(
            doc_type="quote",
            vendor_name="Vendor A",
            total_amount=1000.0,
            hidden_fees_found=True,
            line_items_standardized=["Item 1"]
        ),
        QuoteSchema(
            doc_type="quote",
            vendor_name="Vendor B",
            total_amount=1100.0,
            hidden_fees_found=False,
            line_items_standardized=["Item 1"]
        )
    ]
    sorted_quotes = sorted(quotes, key=lambda q: q.true_cost)
    assert sorted_quotes[0].vendor_name == "Vendor A", "Vendor A should rank first (lower true cost)"
    print(f"   ✅ Bid ranking works: {sorted_quotes[0].vendor_name} (${sorted_quotes[0].true_cost}) < {sorted_quotes[1].vendor_name} (${sorted_quotes[1].true_cost})")
    
    print("   ✅ True cost calculation works correctly")


def test_coi_policy_limit_validation():
    """Test CoiSchema policy limit validation (PRD requirement: > $1M check)."""
    print("\n🧪 Testing CoiSchema Policy Limit Validation...")
    
    # Test 1: COI with policy limit < $1M (should be flagged and critical)
    coi_low_limit = CoiSchema(
        doc_type="coi",
        expiration_date=date.today() + timedelta(days=60),  # Not expiring soon
        policy_limit=500_000.0  # Below $1M threshold
    )
    assert coi_low_limit.policy_limit_flagged == True, "COI with limit < $1M should be flagged"
    assert coi_low_limit.is_critical == True, "COI with limit < $1M should be critical"
    print(f"   ✅ Low policy limit flagged: ${coi_low_limit.policy_limit:,}, is_critical: {coi_low_limit.is_critical}")
    
    # Test 2: COI with policy limit >= $1M (should not be flagged)
    coi_adequate_limit = CoiSchema(
        doc_type="coi",
        expiration_date=date.today() + timedelta(days=60),
        policy_limit=1_500_000.0  # Above $1M threshold
    )
    assert coi_adequate_limit.policy_limit_flagged == False, "COI with limit >= $1M should not be flagged"
    assert coi_adequate_limit.is_critical == False, "COI with adequate limit and not expiring should not be critical"
    print(f"   ✅ Adequate policy limit: ${coi_adequate_limit.policy_limit:,}, flagged: {coi_adequate_limit.policy_limit_flagged}")
    
    # Test 3: COI expiring soon (< 30 days) should be critical regardless of limit
    coi_expiring_soon = CoiSchema(
        doc_type="coi",
        expiration_date=date.today() + timedelta(days=15),  # Expiring soon
        policy_limit=2_000_000.0  # Adequate limit
    )
    assert coi_expiring_soon.is_critical == True, "COI expiring in < 30 days should be critical"
    print(f"   ✅ Expiring soon flagged: {coi_expiring_soon.is_critical}")
    
    # Test 4: COI with both issues (expiring soon AND low limit)
    coi_both_issues = CoiSchema(
        doc_type="coi",
        expiration_date=date.today() + timedelta(days=15),  # Expiring soon
        policy_limit=500_000.0  # Low limit
    )
    assert coi_both_issues.is_critical == True, "COI with both issues should be critical"
    assert coi_both_issues.policy_limit_flagged == True, "COI with low limit should be flagged"
    print(f"   ✅ Both issues flagged: expiring soon + low limit")
    
    print("   ✅ Policy limit validation works correctly")


def run_all_prd_tests():
    """Run all PRD feature tests."""
    print("=" * 70)
    print("PropFlow Agent PRD Features Test Suite")
    print("=" * 70)
    
    try:
        test_lease_rent_cap_flagging()
        test_quote_true_cost_calculation()
        test_coi_policy_limit_validation()
        
        print("\n" + "=" * 70)
        print("✅ All PRD feature tests passed!")
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
    success = run_all_prd_tests()
    sys.exit(0 if success else 1)

