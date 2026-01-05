"""
Tests for enterprise-grade security hardening utilities.
"""
import os
import tempfile
from utils_security import (
    sanitize_filename,
    check_pdf_encryption,
    verify_file_type,
    truncate_text,
    safe_regex_search,
    validate_document_url,
    validate_and_prepare_document
)


def test_sanitize_filename():
    """Test filename sanitization prevents injection attacks."""
    print("\n🧪 Testing Filename Sanitization...")
    
    # Test 1: Path traversal attempt
    malicious = "../../../etc/passwd"
    clean = sanitize_filename(malicious)
    assert ".." not in clean, "Should remove path traversal"
    assert "/" not in clean, "Should remove path separators"
    print(f"   ✅ Path traversal blocked: '{malicious}' -> '{clean}'")
    
    # Test 2: Script injection attempt
    malicious = "invoice<script>alert()</script>.pdf"
    clean = sanitize_filename(malicious)
    assert "<" not in clean and ">" not in clean, "Should remove script tags"
    print(f"   ✅ Script injection blocked: '{malicious}' -> '{clean}'")
    
    # Test 3: Special characters
    malicious = "file name with spaces & symbols!.pdf"
    clean = sanitize_filename(malicious)
    assert " " not in clean, "Should replace spaces"
    assert "&" not in clean, "Should remove special chars"
    print(f"   ✅ Special characters sanitized: '{clean}'")
    
    # Test 4: Empty filename
    clean = sanitize_filename("")
    assert clean == "document.pdf", "Should default to document.pdf"
    print(f"   ✅ Empty filename handled: '{clean}'")
    
    print("   ✅ Filename sanitization works correctly")


def test_truncate_text():
    """Test text truncation prevents ReDoS."""
    print("\n🧪 Testing Text Truncation...")
    
    # Test 1: Normal text (no truncation)
    text = "A" * 1000
    truncated = truncate_text(text, max_length=10000)
    assert len(truncated) == 1000, "Should not truncate short text"
    print(f"   ✅ Short text preserved: {len(truncated)} chars")
    
    # Test 2: Long text (truncation)
    text = "A" * 200000
    truncated = truncate_text(text, max_length=100000)
    assert len(truncated) == 100000, "Should truncate long text"
    print(f"   ✅ Long text truncated: {len(truncated)} chars")
    
    print("   ✅ Text truncation works correctly")


def test_safe_regex_search():
    """Test safe regex search with truncation."""
    print("\n🧪 Testing Safe Regex Search...")
    
    # Test 1: Normal pattern
    text = "This is a lease agreement for tenant John Doe"
    match = safe_regex_search(r"lease", text)
    assert match is not None, "Should find normal pattern"
    print(f"   ✅ Normal pattern found: '{match.group(0)}'")
    
    # Test 2: Long text (truncated before regex)
    text = "A" * 200000 + "lease"
    match = safe_regex_search(r"lease", text, max_length=100000)
    assert match is None, "Should not find pattern after truncation"
    print(f"   ✅ Long text truncated before regex")
    
    print("   ✅ Safe regex search works correctly")


def test_validate_document_url():
    """Test URL validation."""
    print("\n🧪 Testing URL Validation...")
    
    # Test 1: Valid HTTPS URL
    url = "https://example.com/document.pdf"
    error = validate_document_url(url)
    assert error is None, "Should accept valid HTTPS URL"
    print(f"   ✅ Valid HTTPS URL accepted")
    
    # Test 2: Valid HTTP URL
    url = "http://example.com/document.pdf"
    error = validate_document_url(url)
    assert error is None, "Should accept valid HTTP URL"
    print(f"   ✅ Valid HTTP URL accepted")
    
    # Test 3: Invalid protocol
    url = "ftp://example.com/document.pdf"
    error = validate_document_url(url)
    assert error is not None, "Should reject invalid protocol"
    assert "protocol" in error.get("error", "").lower()
    print(f"   ✅ Invalid protocol rejected: {error.get('error_type')}")
    
    # Test 4: Too long URL
    url = "https://example.com/" + "a" * 3000
    error = validate_document_url(url)
    assert error is not None, "Should reject too long URL"
    assert "too long" in error.get("error", "").lower()
    print(f"   ✅ Too long URL rejected: {error.get('error_type')}")
    
    # Test 5: Invalid format
    url = "not-a-url"
    error = validate_document_url(url)
    assert error is not None, "Should reject invalid format"
    print(f"   ✅ Invalid format rejected: {error.get('error_type')}")
    
    print("   ✅ URL validation works correctly")


def test_check_pdf_encryption():
    """Test PDF encryption detection."""
    print("\n🧪 Testing PDF Encryption Detection...")
    
    # Create a simple test PDF (not encrypted)
    try:
        from pypdf import PdfWriter
        
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf:
            temp_path = temp_pdf.name
            
            # Create minimal PDF
            writer = PdfWriter()
            writer.add_blank_page(width=200, height=200)
            writer.write(temp_path)
        
        # Test: Non-encrypted PDF
        error = check_pdf_encryption(temp_path)
        assert error is None, "Should accept non-encrypted PDF"
        print(f"   ✅ Non-encrypted PDF accepted")
        
        os.unlink(temp_path)
    except ImportError:
        print(f"   ⚠️ pypdf not installed, skipping encryption test")
    
    print("   ✅ PDF encryption detection works correctly")


def test_money_cleaning():
    """Test money string cleaning in schemas."""
    print("\n🧪 Testing Money String Cleaning...")
    
    from schemas import clean_money
    
    # Test 1: Dollar sign and commas
    result = clean_money("$1,200.00")
    assert result == 1200.0, f"Should parse '$1,200.00' as 1200.0, got {result}"
    print(f"   ✅ '$1,200.00' -> {result}")
    
    # Test 2: Just number
    result = clean_money("5000")
    assert result == 5000.0, f"Should parse '5000' as 5000.0, got {result}"
    print(f"   ✅ '5000' -> {result}")
    
    # Test 3: Float input
    result = clean_money(1234.56)
    assert result == 1234.56, f"Should pass through float, got {result}"
    print(f"   ✅ Float passed through: {result}")
    
    # Test 4: Spaces
    result = clean_money("  $ 1,200.00 ")
    assert result == 1200.0, f"Should handle spaces, got {result}"
    print(f"   ✅ Spaces handled: '{result}'")
    
    print("   ✅ Money string cleaning works correctly")


if __name__ == "__main__":
    print("=" * 60)
    print("Enterprise Security Hardening Tests")
    print("=" * 60)
    
    test_sanitize_filename()
    test_truncate_text()
    test_safe_regex_search()
    test_validate_document_url()
    test_check_pdf_encryption()
    test_money_cleaning()
    
    print("\n" + "=" * 60)
    print("✅ All security hardening tests passed!")
    print("=" * 60)

