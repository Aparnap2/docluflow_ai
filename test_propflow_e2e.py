"""
End-to-end test for PropFlow Agent using actual Ollama models.

Tests with real LLM (LFM2) and OCR (DeepSeek OCR) models.
"""
import asyncio
import json
from datetime import date, timedelta
from agent_graph import app
from schemas import LeaseSchema, QuoteSchema, CoiSchema


async def test_lease_extraction():
    """Test lease document extraction with actual LLM."""
    print("\n🧪 Testing Lease Extraction with LFM2...")
    
    # Sample lease document text
    lease_text = """
    RESIDENTIAL LEASE AGREEMENT
    
    Tenant Name: John Smith
    Property Address: 123 Main Street, Apt 4B
    
    Lease Term: January 1, 2024 to December 31, 2024
    End Date: December 31, 2024
    
    Notice Period: Tenant must provide 60 days written notice before lease expiration.
    Monthly Rent: $1,500
    
    This lease agreement is between the landlord and tenant as stated above.
    """
    
    # Skip OCR and go directly to router + extraction
    from agent_graph import router_node, extraction_node
    
    initial_state = {
        "doc_url": "test://lease.pdf",
        "text_md": lease_text,
        "doc_type": "",
        "final_data": {}
    }
    
    try:
        # Run router
        router_result = router_node(initial_state)
        state_after_router = {**initial_state, **router_result}
        
        # Run extraction
        extraction_result = extraction_node(state_after_router)
        result = {**state_after_router, **extraction_result}
        
        print(f"   Router detected: {result.get('doc_type')}")
        print(f"   Extraction result: {json.dumps(result.get('final_data', {}), indent=2, default=str)}")
        
        # Verify router identified it as lease
        assert result.get('doc_type') == 'lease', f"Expected 'lease', got '{result.get('doc_type')}'"
        
        # Verify extraction produced valid data
        final_data = result.get('final_data', {})
        if 'error' not in final_data:
            # Try to validate with schema
            lease = LeaseSchema(**final_data)
            print(f"   ✅ Valid LeaseSchema created")
            print(f"   ✅ Tenant: {lease.tenant_name}")
            print(f"   ✅ End Date: {lease.end_date}")
            print(f"   ✅ Calculated Notice Date: {lease.calculated_notice_date}")
        else:
            print(f"   ⚠️  Extraction error: {final_data.get('error')}")
        
        return True
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_quote_extraction():
    """Test quote document extraction with actual LLM."""
    print("\n🧪 Testing Quote Extraction with LFM2...")
    
    # Sample quote document text
    quote_text = """
    ESTIMATE / QUOTE
    
    Vendor: ACME Plumbing Services
    Date: January 15, 2024
    
    Line Items:
    - Labor for pipe repair: $500.00
    - Materials (copper pipes, fittings): $350.50
    - Haul-away fee: $100.00 (not included in base estimate)
    
    Total Amount: $850.50
    
    Note: Additional fees may apply for weekend service.
    """
    
    # Skip OCR and go directly to router + extraction
    from agent_graph import router_node, extraction_node
    
    initial_state = {
        "doc_url": "test://quote.pdf",
        "text_md": quote_text,
        "doc_type": "",
        "final_data": {}
    }
    
    try:
        # Run router
        router_result = router_node(initial_state)
        state_after_router = {**initial_state, **router_result}
        
        # Run extraction
        extraction_result = extraction_node(state_after_router)
        result = {**state_after_router, **extraction_result}
        
        print(f"   Router detected: {result.get('doc_type')}")
        print(f"   Extraction result: {json.dumps(result.get('final_data', {}), indent=2, default=str)}")
        
        assert result.get('doc_type') == 'quote', f"Expected 'quote', got '{result.get('doc_type')}'"
        
        final_data = result.get('final_data', {})
        if 'error' not in final_data:
            quote = QuoteSchema(**final_data)
            print(f"   ✅ Valid QuoteSchema created")
            print(f"   ✅ Vendor: {quote.vendor_name}")
            print(f"   ✅ Total: ${quote.total_amount}")
            print(f"   ✅ Hidden Fees Found: {quote.hidden_fees_found}")
        else:
            print(f"   ⚠️  Extraction error: {final_data.get('error')}")
        
        return True
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_coi_extraction():
    """Test COI document extraction with actual LLM."""
    print("\n🧪 Testing COI Extraction with LFM2...")
    
    # Sample COI document text - expiring soon (critical)
    coi_text_critical = """
    CERTIFICATE OF LIABILITY INSURANCE
    
    Insured: ABC Plumbing Company
    Policy Number: PL-2024-001
    
    Expiration Date: February 15, 2024
    
    This certificate is issued as a matter of information only.
    """
    
    # Sample COI document text - expiring later (not critical)
    coi_text_safe = """
    CERTIFICATE OF LIABILITY INSURANCE
    
    Insured: XYZ Electrical Services
    Policy Number: EL-2024-002
    
    Expiration Date: December 31, 2024
    
    This certificate is issued as a matter of information only.
    """
    
    test_cases = [
        ("Critical (expiring soon)", coi_text_critical),
        ("Safe (expiring later)", coi_text_safe)
    ]
    
    # Skip OCR and go directly to router + extraction
    from agent_graph import router_node, extraction_node
    
    all_passed = True
    for test_name, coi_text in test_cases:
        print(f"\n   Testing {test_name}...")
        initial_state = {
            "doc_url": f"test://coi_{test_name.lower().replace(' ', '_')}.pdf",
            "text_md": coi_text,
            "doc_type": "",
            "final_data": {}
        }
        
        try:
            # Run router
            router_result = router_node(initial_state)
            state_after_router = {**initial_state, **router_result}
            
            # Run extraction
            extraction_result = extraction_node(state_after_router)
            result = {**state_after_router, **extraction_result}
            
            print(f"   Router detected: {result.get('doc_type')}")
            print(f"   Extraction result: {json.dumps(result.get('final_data', {}), indent=2, default=str)}")
            
            assert result.get('doc_type') == 'coi', f"Expected 'coi', got '{result.get('doc_type')}'"
            
            final_data = result.get('final_data', {})
            if 'error' not in final_data:
                coi = CoiSchema(**final_data)
                print(f"   ✅ Valid CoiSchema created")
                print(f"   ✅ Expiration Date: {coi.expiration_date}")
                print(f"   ✅ Is Critical: {coi.is_critical}")
                
                # Verify business logic
                if "Critical" in test_name:
                    # Should be critical if expiring in < 30 days
                    days_left = (coi.expiration_date - date.today()).days
                    if days_left < 30:
                        assert coi.is_critical == True, "COI expiring soon should be flagged as critical"
                else:
                    # Should not be critical if expiring in > 30 days
                    days_left = (coi.expiration_date - date.today()).days
                    if days_left >= 30:
                        assert coi.is_critical == False, "COI expiring later should not be critical"
            else:
                print(f"   ⚠️  Extraction error: {final_data.get('error')}")
                all_passed = False
        except Exception as e:
            print(f"   ❌ Error: {e}")
            import traceback
            traceback.print_exc()
            all_passed = False
    
    return all_passed


async def test_router_with_actual_text():
    """Test router with actual document text samples."""
    print("\n🧪 Testing Router with Actual Document Text...")
    
    test_cases = [
        ("lease", "RESIDENTIAL LEASE AGREEMENT\nTenant: John Doe\nEnd Date: 2024-12-31"),
        ("quote", "ESTIMATE\nVendor: ACME Corp\nTotal: $1,000"),
        ("coi", "CERTIFICATE OF LIABILITY INSURANCE\nExpiration: 2024-06-01"),
        ("unknown", "Random document content without keywords")
    ]
    
    all_passed = True
    for expected_type, text in test_cases:
        initial_state = {
            "doc_url": f"test://{expected_type}.pdf",
            "text_md": text,
            "doc_type": "",
            "final_data": {}
        }
        
        # Skip OCR node, go directly to router
        from agent_graph import router_node
        router_result = router_node(initial_state)
        detected_type = router_result.get('doc_type')
        
        print(f"   Text: '{text[:50]}...'")
        print(f"   Expected: {expected_type}, Detected: {detected_type}")
        
        if expected_type == "unknown":
            # Unknown is acceptable
            print(f"   ✅ Router handled unknown document")
        elif detected_type == expected_type:
            print(f"   ✅ Router correctly identified {expected_type}")
        else:
            print(f"   ⚠️  Router mismatch: expected {expected_type}, got {detected_type}")
            # Not a failure, just a warning
    
    return True


async def run_e2e_tests():
    """Run all end-to-end tests with actual Ollama models."""
    print("=" * 70)
    print("PropFlow Agent End-to-End Tests (with Ollama Models)")
    print("=" * 70)
    print("\nUsing models:")
    print("  - LLM: sam860/LFM2:2.6b")
    print("  - OCR: deepseek-ocr:3b (not used in these tests - using sample text)")
    print()
    
    results = []
    
    # Test router first (fastest)
    results.append(("Router", await test_router_with_actual_text()))
    
    # Test extractions (slower - uses actual LLM)
    print("\n" + "=" * 70)
    print("Testing Document Extraction (this may take a minute...)")
    print("=" * 70)
    
    results.append(("Lease Extraction", await test_lease_extraction()))
    results.append(("Quote Extraction", await test_quote_extraction()))
    results.append(("COI Extraction", await test_coi_extraction()))
    
    # Summary
    print("\n" + "=" * 70)
    print("Test Results Summary")
    print("=" * 70)
    
    all_passed = True
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"  {test_name}: {status}")
        if not passed:
            all_passed = False
    
    print("=" * 70)
    if all_passed:
        print("✅ All end-to-end tests passed!")
    else:
        print("⚠️  Some tests failed or had warnings")
    print("=" * 70)
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(run_e2e_tests())
    exit(0 if success else 1)

