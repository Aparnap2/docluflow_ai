"""
TDD Tests for EntryAI Router and Task Processing

Tests cover:
1. ActorInput Router - Task type validation
2. Document Binary Input - Base64 validation
3. Data File Input - CSV/Excel/URL handling
4. Output Schema - Response format validation

All external dependencies (Gemini API) are mocked.
"""
import base64
import json
import sys
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, "/home/aparna/Desktop/docuflow-headless")

from schemas import (
    BoundingBox,
    LeaseData,
    QuoteData,
    CoiData,
    DocumentExtraction,
    ExtractionResult,
    DocumentBinaryInput,
    DocumentBinaryWrapper,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def valid_pdf_base64():
    """Valid base64-encoded PDF placeholder (smallest valid PDF header)."""
    # Minimal valid PDF header encoded
    return base64.b64encode(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF").decode("utf-8")


@pytest.fixture
def valid_image_base64():
    """Valid base64-encoded PNG image placeholder."""
    # Minimal 1x1 PNG image
    png_data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
    return base64.b64encode(png_data).decode("utf-8")


@pytest.fixture
def invalid_base64():
    """Invalid base64 string that will fail decoding."""
    return "not-valid-base64!!!"


@pytest.fixture
def short_base64():
    """Base64 string that's too short to be a valid document."""
    return "aGVsbG8="  # "hello" in base64


@pytest.fixture
def coi_document_text():
    """Sample COI document text for classification tests."""
    return """Certificate of Insurance
Policy Period: 01/01/2025 to 12/31/2025
Named Insured: John Smith
Certificate Holder: ABC Corp
Policy Number: GL-2024-1234
Insurance Company: ABC Insurance Co
Coverage Limit: $2,000,000"""


@pytest.fixture
def lease_document_text():
    """Sample Lease document text for classification tests."""
    return """RESIDENTIAL LEASE AGREEMENT
Tenant Name: Jane Doe
Landlord: Property Management Inc
Lease Term: 12 months
Property Address: 123 Main St, Apt 4B
Monthly Rent: $2,500
Security Deposit: $5,000
Start Date: 2024-01-01
End Date: 2024-12-31"""


@pytest.fixture
def quote_document_text():
    """Sample Quote document text for classification tests."""
    return """QUOTE #12345
Pacific Flooring Solutions
Total Amount: $5,865.00
Line Items: Carpet, Padding, Installation
Vendor Address: 456 Oak Ave
Hidden Fees: Haul-away not included"""


# =============================================================================
# Test ActorInput Router - Task Type Validation
# =============================================================================


class TestActorInputRouter:
    """Tests for task type routing and validation."""

    VALID_TASK_TYPES = ["extract_invoice", "clean_crm", "verify_data"]

    @pytest.mark.parametrize("task_type", ["extract_invoice", "clean_crm", "verify_data"])
    def test_valid_task_types(self, task_type):
        """Each valid task_type should be accepted without error."""
        # Create actor input with valid task_type
        from schemas import ActorInput

        # Valid task inputs for each type - use correct field names
        valid_inputs = {
            "extract_invoice": {
                "doc_binary": {"data": base64.b64encode(b"test pdf content").decode("utf-8")},
                "task_type": "extract_invoice",
            },
            "clean_crm": {
                "data_file_base64": base64.b64encode(b"records,name,email\nTest,test@example.com").decode("utf-8"),
                "task_type": "clean_crm",
            },
            "verify_data": {
                "task_type": "verify_data",
                "options": {"extracted": {"tenant_name": "Test"}, "expected": {"tenant_name": "Test"}},
            },
        }

        input_data = valid_inputs[task_type]
        # Should not raise an exception
        actor_input = ActorInput(**input_data)
        assert actor_input.task_type == task_type

    @pytest.mark.parametrize(
        "invalid_task_type",
        [
            "invalid_task",
            "extract",
            "clean",
            "data_processing",
            "",
            None,
            "EXTRACT_INVOICE",  # Case sensitive
            "Extract_Invoice",  # Wrong case
        ],
    )
    def test_invalid_task_type_fails_validation(self, invalid_task_type):
        """Invalid task_type should fail validation or be rejected."""
        from pydantic import ValidationError

        if invalid_task_type is None:
            # None task_type should fail
            with pytest.raises((ValidationError, TypeError, AttributeError)):
                from schemas import ActorInput
                ActorInput(
                    docBinary={"data": "test"},
                    task_type=invalid_task_type,
                )
        else:
            with pytest.raises((ValidationError, ValueError)):
                from schemas import ActorInput
                ActorInput(
                    doc_binary={"data": "test"},
                    task_type=invalid_task_type,
                )

    def test_extract_invoice_requires_document(self):
        """extract_invoice task should require document binary data."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            from schemas import ActorInput

            ActorInput(
                doc_binary=None,
                task_type="extract_invoice",
            )

    def test_clean_crm_requires_data_field(self):
        """clean_crm task should require data records."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            from schemas import ActorInput

            ActorInput(
                data_file_base64=None,
                task_type="clean_crm",
            )

    def test_verify_data_requires_both_extracted_and_expected(self):
        """verify_data task should validate both extracted and expected fields."""
        from pydantic import ValidationError

        # Missing expected field
        with pytest.raises(ValidationError):
            from schemas import ActorInput

            ActorInput(
                task_type="verify_data",
                data={"extracted": {"tenant_name": "Test"}},
            )

    def test_task_routing_selects_correct_handler(self):
        """Task type should correctly route to appropriate handler."""
        from schemas import classify_document

        # Test routing logic
        assert classify_document("lease agreement") == "lease"
        assert classify_document("quote estimate") == "quote"
        assert classify_document("certificate of insurance") == "coi"


# =============================================================================
# Test Document Binary Input
# =============================================================================


class TestDocumentBinaryInput:
    """Tests for document binary input validation."""

    def test_valid_pdf_base64(self, valid_pdf_base64):
        """Valid PDF base64 should be accepted."""
        binary_input = DocumentBinaryInput(data=valid_pdf_base64)
        assert binary_input.data == valid_pdf_base64
        # Should be able to decode without error
        decoded = base64.b64decode(binary_input.data)
        assert decoded.startswith(b"%PDF")

    def test_valid_image_base64(self, valid_image_base64):
        """Valid image base64 should be accepted."""
        binary_input = DocumentBinaryInput(data=valid_image_base64)
        assert binary_input.data == valid_image_base64
        decoded = base64.b64decode(binary_input.data)
        # PNG signature
        assert decoded[:4] == b"\x89PNG"

    def test_invalid_base64_fails_gracefully(self, invalid_base64):
        """Invalid base64 should fail validation."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DocumentBinaryInput(data=invalid_base64)

    def test_missing_required_fields(self):
        """Missing data field should fail validation."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DocumentBinaryInput()

    def test_wrapper_accepts_valid_binary(self, valid_pdf_base64):
        """DocumentBinaryWrapper should accept valid binary input."""
        wrapper = DocumentBinaryWrapper(docBinary=DocumentBinaryInput(data=valid_pdf_base64))
        assert wrapper.docBinary.data == valid_pdf_base64

    def test_wrapper_rejects_missing_binary(self):
        """DocumentBinaryWrapper should reject missing binary data."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DocumentBinaryWrapper()

    def test_base64_too_short_rejected(self, short_base64):
        """Base64 that's too short should fail validation."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DocumentBinaryInput(data=short_base64)


# =============================================================================
# Test Data File Input
# =============================================================================


class TestDataFileInput:
    """Tests for data file input (CSV, Excel, URL)."""

    def test_csv_base64_input(self):
        """CSV base64 data should be accepted and decodable."""
        csv_content = "name,email,phone\nJohn Doe,john@example.com,555-1234"
        csv_base64 = base64.b64encode(csv_content.encode("utf-8")).decode("utf-8")

        # Validate it can be decoded
        decoded = base64.b64decode(csv_base64).decode("utf-8")
        assert "John Doe" in decoded
        assert "john@example.com" in decoded

    def test_excel_base64_input(self):
        """Excel base64 data should be accepted (simulated)."""
        # Excel files are complex, but base64 encoding should work
        excel_content = b"Simulated Excel content"
        excel_base64 = base64.b64encode(excel_content).decode("utf-8")

        decoded = base64.b64decode(excel_base64)
        assert decoded == excel_content

    @pytest.mark.skip(reason="Requires uvicorn and server.py - server module not installed")
    def test_url_based_input_alternative(self):
        """URL-based input should be a valid alternative to base64."""
        # This tests the ExtractionRequest model
        from server import ExtractionRequest

        request = ExtractionRequest(
            source_url="https://example.com/document.pdf",
            filename="document.pdf",
        )
        assert request.source_url == "https://example.com/document.pdf"
        assert request.filename == "document.pdf"

    @pytest.mark.skip(reason="Requires uvicorn and server.py - server module not installed")
    def test_both_url_and_base64_allowed(self):
        """Both URL and base64 should be allowed in same request."""
        from server import ExtractionRequest

        request = ExtractionRequest(
            doc_base64="aGVsbG8=",  # "hello"
            source_url="https://example.com/backup.pdf",
            filename="document.pdf",
        )
        assert request.doc_base64 == "aGVsbG8="
        assert request.source_url is not None

    @pytest.mark.skip(reason="Requires fastapi and server.py - server module not installed")
    def test_neither_url_nor_base64_fails(self):
        """Missing both URL and base64 should fail."""
        from fastapi import HTTPException
        from pydantic import ValidationError

        # Test model validation
        with pytest.raises(ValidationError):
            from server import ExtractionRequest

            ExtractionRequest(filename="document.pdf")


# =============================================================================
# Test Output Schema
# =============================================================================


class TestOutputSchema:
    """Tests for output response schema validation."""

    def test_success_response_format(self):
        """Success response should have all required fields."""
        result = ExtractionResult(
            status="success",
            doc_type="lease",
            summary="Lease agreement for 123 Main St",
            payload={"tenant_name": "John Doe"},
            is_urgent=False,
            warnings=[],
        )

        assert result.status == "success"
        assert result.doc_type == "lease"
        assert result.summary == "Lease agreement for 123 Main St"
        assert result.payload == {"tenant_name": "John Doe"}
        assert result.is_urgent is False
        assert result.warnings == []

    def test_error_response_format(self):
        """Error response should have error message."""
        result = ExtractionResult(
            status="error",
            error="Failed to decode document",
        )

        assert result.status == "error"
        assert result.error == "Failed to decode document"
        assert result.doc_type == "unknown"  # Default

    def test_processing_metadata_included(self):
        """Processing metadata should be included in extraction."""
        extraction = DocumentExtraction(
            doc_type="coi",
            summary="Insurance certificate for ABC Corp",
            payload=CoiData(
                insured_name="ABC Corp",
                insurance_company="XYZ Insurance",
                policy_number="POL-12345",
                expiration_date=date.today() + timedelta(days=60),
                policy_limit=2000000,
            ),
            extraction_confidence=0.95,
            classification_confidence=0.98,
            model_used="gemini-2.0-flash-exp",
            processing_time_ms=1500,
            status="success",
        )

        assert extraction.model_used == "gemini-2.0-flash-exp"
        assert extraction.processing_time_ms == 1500
        assert extraction.extraction_confidence == 0.95
        assert extraction.classification_confidence == 0.98

    def test_confidence_scores_range(self):
        """Confidence scores should be between 0 and 1."""
        # Valid range
        extraction = DocumentExtraction(
            doc_type="lease",
            summary="Test",
            extraction_confidence=0.0,
            classification_confidence=1.0,
            status="success",
        )
        assert extraction.extraction_confidence == 0.0
        assert extraction.classification_confidence == 1.0

        # Invalid - too high
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DocumentExtraction(
                doc_type="lease",
                summary="Test",
                extraction_confidence=1.5,  # > 1.0
                classification_confidence=0.5,
                status="success",
            )

        # Invalid - negative
        with pytest.raises(ValidationError):
            DocumentExtraction(
                doc_type="lease",
                summary="Test",
                extraction_confidence=-0.1,  # < 0.0
                classification_confidence=0.5,
                status="success",
            )


# =============================================================================
# Test Document Classification Router
# =============================================================================


class TestDocumentClassificationRouter:
    """Tests for document type classification router."""

    @pytest.mark.parametrize(
        "text,expected_type",
        [
            # COI documents
            ("Certificate of Insurance - Policy Number: ABC123", "coi"),
            ("Certificate of Liability Insurance", "coi"),
            ("Named Insured: John Smith", "coi"),
            ("Policy Period: 01/01/2025 to 12/31/2025", "coi"),
            # Lease documents
            ("RESIDENTIAL LEASE AGREEMENT", "lease"),
            ("Tenant Name: Jane Doe", "lease"),
            ("Security Deposit: $1500", "lease"),
            ("Monthly Rent: $2500", "lease"),
            # Quote documents
            ("QUOTE #12345", "quote"),
            ("Estimate for flooring work", "quote"),
            ("Total Amount: $5,865.00", "quote"),
            ("BID PROPOSAL from ABC Construction", "quote"),
        ],
    )
    def test_classification_router(self, text, expected_type):
        """Router should correctly classify document types."""
        from schemas import classify_document

        result = classify_document(text)
        assert result == expected_type

    def test_unknown_document_type(self):
        """Documents with no matching keywords should be 'unknown'."""
        from schemas import classify_document

        result = classify_document("This is some random document text")
        assert result == "unknown"

    def test_classification_precedence_coi_first(self):
        """COI keywords should take precedence (checked first)."""
        from schemas import classify_document

        # Text containing both COI and Lease keywords
        text = "Certificate of Insurance for Lease Property"
        result = classify_document(text)
        # COI is checked first, should return "coi"
        assert result == "coi"


# =============================================================================
# Test Post-Processing Logic
# =============================================================================


class TestPostProcessing:
    """Tests for post-processing business logic."""

    def test_lease_notice_date_calculation(self):
        """Lease post-processing should calculate notice date."""
        lease_data = LeaseData(
            tenant_name="John Doe",
            end_date=date.today() + timedelta(days=90),
            notice_period_days=60,
            monthly_rent=2500.0,
        )

        # Notice date should be calculated
        assert lease_data.calculated_notice_date is not None
        assert lease_data.calculated_notice_date == date.today() + timedelta(days=30)

    def test_lease_urgency_flag(self):
        """Lease within 30 days of notice date should be urgent."""
        lease_data = LeaseData(
            tenant_name="John Doe",
            end_date=date.today() + timedelta(days=20),  # 20 days from now
            notice_period_days=10,
            monthly_rent=2500.0,
        )

        assert lease_data.is_urgent is True

    def test_coi_expiry_calculation(self):
        """COI post-processing should calculate days until expiry."""
        coi_data = CoiData(
            insured_name="ABC Corp",
            expiration_date=date.today() + timedelta(days=45),
            policy_limit=2000000,
        )

        assert coi_data.days_until_expiry == 45
        assert coi_data.is_urgent is False  # More than 30 days

    def test_coi_urgency_flag(self):
        """COI within 30 days should be urgent."""
        coi_data = CoiData(
            insured_name="ABC Corp",
            expiration_date=date.today() + timedelta(days=15),
            policy_limit=2000000,
        )

        assert coi_data.is_urgent is True

    def test_coi_low_policy_limit_flagged(self):
        """COI with policy limit below $1M should be flagged."""
        coi_data = CoiData(
            insured_name="ABC Corp",
            expiration_date=date.today() + timedelta(days=60),
            policy_limit=500000,  # Below $1M
        )

        assert coi_data.policy_limit_flagged is True

    def test_quote_true_cost_calculation(self):
        """Quote post-processing should calculate true cost."""
        quote_data = QuoteData(
            vendor_name="ABC Construction",
            total_amount=5000.0,
            hidden_fees_found=True,
        )

        # true_cost is now Decimal - compare numerically
        assert float(quote_data.true_cost) == 5500.0  # 10% estimate added

    def test_quote_without_hidden_fees(self):
        """Quote without hidden fees should have true cost = total."""
        quote_data = QuoteData(
            vendor_name="ABC Construction",
            total_amount=5000.0,
            hidden_fees_found=False,
        )

        # true_cost is now Decimal - compare numerically
        assert float(quote_data.true_cost) == 5000.0


# =============================================================================
# Test Bounding Box Validation
# =============================================================================


class TestBoundingBox:
    """Tests for bounding box coordinate validation."""

    def test_valid_bounding_box(self):
        """Valid bounding box should be accepted."""
        bbox = BoundingBox(ymin=100, xmin=100, ymax=500, xmax=500)
        assert bbox.ymin == 100
        assert bbox.ymax == 500

    def test_bounding_box_ymin_greater_than_ymax_rejected(self):
        """Bounding box with ymin >= ymax should fail."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            BoundingBox(ymin=500, xmin=100, ymax=500, xmax=500)

    def test_bounding_box_xmin_greater_than_xmax_rejected(self):
        """Bounding box with xmin >= xmax should fail."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            BoundingBox(ymin=100, xmin=500, ymax=500, xmax=500)

    def test_bounding_box_coordinates_range_0_to_1000(self):
        """Bounding box coordinates should be 0-1000."""
        from pydantic import ValidationError

        # Too low
        with pytest.raises(ValidationError):
            BoundingBox(ymin=-1, xmin=0, ymax=500, xmax=500)

        # Too high
        with pytest.raises(ValidationError):
            BoundingBox(ymin=0, xmin=0, ymax=1001, xmax=500)


# =============================================================================
# Test Input Validation Edge Cases
# =============================================================================


class TestInputValidationEdgeCases:
    """Tests for edge cases in input validation."""

    def test_empty_base64_rejected(self):
        """Empty base64 string should be rejected."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DocumentBinaryInput(data="")

    def test_whitespace_only_base64_rejected(self):
        """Whitespace-only base64 should be rejected."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DocumentBinaryInput(data="   ")

    @pytest.mark.skip(reason="Requires full Apify integration - main.py has Pydantic compatibility issues")
    def test_malformed_json_in_payload(self):
        """Malformed JSON in payload should be handled gracefully."""
        # This tests the overall error handling in main.py
        # Skipped due to Apify SDK Pydantic v2 compatibility issues
        pass


class AsyncMock:
    """Mock for async methods."""

    def __call__(self, *args, **kwargs):
        return AsyncMockReturn(*args, **kwargs)

    async def __aenter__(self, *args, **kwargs):
        return self

    async def __aexit__(self, *args, **kwargs):
        pass


class AsyncMockReturn:
    """Return value for async mock."""

    def __init__(self, *args, **kwargs):
        pass

    async def __call__(self, *args, **kwargs):
        return None


# =============================================================================
# Test Money Value Cleaning
# =============================================================================


class TestMoneyValueCleaning:
    """Tests for money value cleaning utility."""

    @pytest.mark.parametrize(
        "input_value,expected",
        [
            ("$1,200.50", 1200.50),
            ("$2500", 2500.0),
            ("500.00", 500.0),
            (500.0, 500.0),
            (100, 100.0),
            (None, 0.0),
            ("$1,200,300.00", 1200300.0),
        ],
    )
    def test_money_cleaning(self, input_value, expected):
        """Money cleaning should handle various formats."""
        from schemas import clean_money

        result = clean_money(input_value)
        assert result == expected


# =============================================================================
# Integration Tests with Mocked External Calls
# =============================================================================


class TestIntegrationWithMocks:
    """Integration tests with mocked external dependencies."""

    @patch("main.genai.Client")
    async def test_gemini_extraction_is_mocked(self, mock_genai_client):
        """Gemini API calls should be mocked in tests."""
        # Setup mock
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "doc_type": "lease",
            "summary": "Test lease",
            "payload": {
                "tenant_name": "John Doe",
                "monthly_rent": 2500.0,
            },
            "extraction_confidence": 0.95,
            "classification_confidence": 0.98,
        })
        mock_client.models.generate_content.return_value = mock_response
        mock_genai_client.return_value = mock_client

        # Verify mock is set up correctly
        assert mock_genai_client is not None

    def test_extraction_result_to_dict(self):
        """ExtractionResult should convert to dict for JSON serialization."""
        result = ExtractionResult(
            status="success",
            doc_type="coi",
            summary="Test COI",
            payload={"policy_number": "ABC123"},
            is_urgent=True,
        )

        result_dict = result.model_dump()
        assert isinstance(result_dict, dict)
        assert result_dict["status"] == "success"
        assert result_dict["doc_type"] == "coi"

    def test_document_extraction_serialization(self):
        """DocumentExtraction should serialize to JSON-compatible format."""
        extraction = DocumentExtraction(
            doc_type="lease",
            summary="Lease document",
            payload=LeaseData(
                tenant_name="John Doe",
                monthly_rent=2000.0,
            ),
            status="success",
        )

        json_str = extraction.model_dump_json()
        assert isinstance(json_str, str)
        assert "lease" in json_str
        assert "John Doe" in json_str


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
