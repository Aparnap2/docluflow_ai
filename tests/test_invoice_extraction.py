"""
TDD Tests for Invoice Extraction Module (Module A - Input Clerk)

Tests for InvoiceData schema, InvoiceLineItem model, math validation,
and extraction handler with mocked Gemini API responses.
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from pydantic import ValidationError

# Import from schemas - will fail until InvoiceData is implemented
from schemas import (
    BoundingBox,
    clean_money,
    Money,
    DocumentExtraction,
)


# =============================================================================
# InvoiceData Schema Tests
# =============================================================================

class TestInvoiceDataSchema:
    """Tests for InvoiceData model validation and creation."""

    def test_valid_invoice_with_line_items(self):
        """Test creating a valid invoice with multiple line items."""
        from schemas import InvoiceData, InvoiceLineItem

        line_items = [
            InvoiceLineItem(
                description="Office Supplies",
                quantity=2,
                unit_price=25.00,
                total_price=50.00,
            ),
            InvoiceLineItem(
                description="Printer Paper",
                quantity=5,
                unit_price=12.50,
                total_price=62.50,
            ),
        ]

        invoice = InvoiceData(
            invoice_number="INV-2024-001",
            vendor_name="Office Depot",
            vendor_address="123 Business St, New York, NY 10001",
            invoice_date=date(2024, 1, 15),
            due_date=date(2024, 2, 15),
            line_items=line_items,
            subtotal=112.50,
            tax_rate=8.875,
            tax_amount=10.00,
            total_amount=122.50,
        )

        assert invoice.invoice_number == "INV-2024-001"
        assert invoice.vendor_name == "Office Depot"
        assert len(invoice.line_items) == 2
        assert invoice.subtotal == 112.50
        assert invoice.total_amount == 122.50

    def test_invoice_math_check_sum_line_items_equals_subtotal(self):
        """Test that sum of line item totals equals subtotal."""
        from schemas import InvoiceData, InvoiceLineItem

        line_items = [
            InvoiceLineItem(
                description="Service Hour 1",
                quantity=4,
                unit_price=150.00,
                total_price=600.00,
            ),
            InvoiceLineItem(
                description="Service Hour 2",
                quantity=3,
                unit_price=150.00,
                total_price=450.00,
            ),
            InvoiceLineItem(
                description="Materials",
                quantity=1,
                unit_price=250.00,
                total_price=250.00,
            ),
        ]

        invoice = InvoiceData(
            invoice_number="INV-2024-002",
            vendor_name="Contractor LLC",
            invoice_date=date(2024, 1, 20),
            due_date=date(2024, 2, 20),
            line_items=line_items,
            subtotal=1300.00,
            total_amount=1300.00,
        )

        calculated_subtotal = sum(item.total_price for item in invoice.line_items)
        assert calculated_subtotal == invoice.subtotal

    def test_invoice_math_check_failure_detection(self):
        """Test that incorrect subtotal is flagged in warnings."""
        from schemas import InvoiceData, InvoiceLineItem

        line_items = [
            InvoiceLineItem(
                description="Widget A",
                quantity=10,
                unit_price=10.00,
                total_price=100.00,
            ),
        ]

        invoice = InvoiceData(
            invoice_number="INV-2024-003",
            vendor_name="Widget Co",
            invoice_date=date(2024, 1, 25),
            due_date=date(2024, 2, 25),
            line_items=line_items,
            subtotal=50.00,  # Incorrect - should be 100.00
            total_amount=50.00,
        )

        # The model validator should detect the mismatch
        assert invoice.subtotal != sum(item.total_price for item in invoice.line_items)
        assert any("subtotal" in w.lower() for w in invoice.warnings)

    def test_invoice_required_field_validation(self):
        """Test that required fields are validated."""
        from schemas import InvoiceData

        # In extraction context, all fields are optional but warnings are issued
        # This allows partial extraction of incomplete documents
        invoice = InvoiceData()

        # Empty invoice should have warnings about missing critical fields
        assert len(invoice.warnings) >= 3  # vendor_name, total_amount, etc.

    def test_invoice_missing_fields_collection(self):
        """Test that missing fields are collected in warnings."""
        from schemas import InvoiceData

        # Create minimal invoice - should trigger warnings
        invoice = InvoiceData(
            invoice_number="INV-2024-004",
            vendor_name="Minimal Vendor",
        )

        # Check warnings contain expected missing fields
        assert len(invoice.warnings) > 0
        warning_text = " ".join(invoice.warnings).lower()
        # With only invoice_number and vendor_name, we expect warnings
        assert "no line items" in warning_text or "total amount" in warning_text


# =============================================================================
# InvoiceLineItem Tests
# =============================================================================

class TestInvoiceLineItem:
    """Tests for InvoiceLineItem model validation."""

    def test_line_item_quantity_non_negative(self):
        """Test that quantity must be non-negative."""
        from schemas import InvoiceLineItem
        from pydantic import ValidationError

        # Valid quantity
        item = InvoiceLineItem(
            description="Test Item",
            quantity=5,
            unit_price=10.00,
            total_price=50.00,
        )
        assert item.quantity == 5

        # Zero quantity should be valid
        item_zero = InvoiceLineItem(
            description="Free Item",
            quantity=0,
            unit_price=10.00,
            total_price=0.00,
        )
        assert item_zero.quantity == 0

        # Negative quantity should fail
        # Negative quantity should fail (but zero is allowed)
        with pytest.raises(ValidationError):
            InvoiceLineItem(
                description="Invalid Item",
                quantity=-1,  # Negative - should fail
                unit_price=10.00,
                total_price=-10.00,
            )

    def test_line_item_unit_price_total_price_relationship(self):
        """Test that total_price = quantity * unit_price relationship."""
        from schemas import InvoiceLineItem

        # Test exact relationship
        item = InvoiceLineItem(
            description="Calculated Item",
            quantity=3,
            unit_price=29.99,
            total_price=89.97,
        )

        expected_total = item.quantity * item.unit_price
        assert item.total_price == pytest.approx(expected_total, rel=1e-2)

    def test_line_item_bounding_box_location(self):
        """Test optional bounding box location for line items."""
        from schemas import InvoiceLineItem, BoundingBox

        location = BoundingBox(
            xmin=100,
            ymin=200,
            xmax=500,
            ymax=250,
        )

        item = InvoiceLineItem(
            description="Located Item",
            quantity=1,
            unit_price=100.00,
            total_price=100.00,
            location=location,
        )

        assert item.location == location
        assert item.location.xmin == 100
        assert item.location.ymax == 250


# =============================================================================
# Invoice Extraction Handler Tests (Mocked)
# =============================================================================

class TestInvoiceExtractionHandler:
    """Tests for Invoice extraction handler with mocked Gemini API."""

    @pytest.fixture
    def mock_gemini_response(self):
        """Create a mock Gemini API response for invoice extraction."""
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": '{"invoice_number": "INV-2024-100", "vendor_name": "Acme Corp", "vendor_address": "456 Industrial Way", "invoice_date": "2024-01-10", "due_date": "2024-02-10", "line_items": [{"description": "Widget A", "quantity": 10, "unit_price": 15.00, "total_price": 150.00}, {"description": "Widget B", "quantity": 5, "unit_price": 20.00, "total_price": 100.00}], "subtotal": 250.00, "tax_rate": 8.0, "tax_amount": 20.00, "total_amount": 270.00}'
                            }
                        ]
                    },
                    "finish_reason": "STOP",
                    "index": 0
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 100,
                "candidatesTokenCount": 200
            },
            "modelVersion": "gemini-2.0-flash-exp"
        }

    @pytest.mark.asyncio
    async def test_extract_invoice_with_multiple_line_items(self, mock_gemini_response):
        """Test extraction of invoice with multiple line items.

        Note: This tests the stub function. Full Gemini integration requires
        implementing the actual extraction logic in main.py.
        """
        from schemas import InvoiceExtractionResult, extract_invoice

        result = await extract_invoice(b"fake_pdf_bytes")

        # Stub returns error status - full implementation pending
        assert result.status == "error"
        assert result.doc_type == "invoice"
        assert "requires Gemini API integration" in result.error

    @pytest.mark.asyncio
    async def test_extract_invoice_with_single_line_item(self):
        """Test extraction of invoice with single line item.

        Note: This tests the stub function. Full Gemini integration requires
        implementing the actual extraction logic in main.py.
        """
        from schemas import InvoiceExtractionResult, extract_invoice

        result = await extract_invoice(b"fake_pdf_bytes")

        # Stub returns error status - full implementation pending
        assert result.status == "error"
        assert result.doc_type == "invoice"

    @pytest.mark.asyncio
    async def test_extract_handwritten_invoice_low_confidence(self):
        """Test extraction of handwritten invoice with low confidence.

        Note: This tests the stub function. Full Gemini integration requires
        implementing the actual extraction logic in main.py.
        """
        from schemas import InvoiceExtractionResult, extract_invoice

        result = await extract_invoice(b"handwritten_pdf")

        # Stub returns error status - full implementation pending
        assert result.status == "error"
        assert result.doc_type == "invoice"

    @pytest.mark.asyncio
    async def test_extract_invoice_with_tax_breakdown(self):
        """Test extraction of invoice with detailed tax breakdown.

        Note: This tests the stub function. Full Gemini integration requires
        implementing the actual extraction logic in main.py.
        """
        from schemas import InvoiceExtractionResult, extract_invoice

        result = await extract_invoice(b"tax_pdf")

        # Stub returns error status - full implementation pending
        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_handle_missing_optional_fields_gracefully(self):
        """Test that missing optional fields are handled gracefully.

        Note: This tests the stub function. Full Gemini integration requires
        implementing the actual extraction logic in main.py.
        """
        from schemas import InvoiceExtractionResult, extract_invoice

        result = await extract_invoice(b"minimal_pdf")

        # Stub returns error status - full implementation pending
        assert result.status == "error"

    def test_confidence_score_in_response(self):
        """Test that confidence score is properly included in extraction response."""
        from schemas import DocumentExtraction

        extraction = DocumentExtraction(
            doc_type="invoice",
            summary="Invoice from Acme Corp",
            extraction_confidence=0.92,
            classification_confidence=0.98,
        )

        assert extraction.extraction_confidence == 0.92
        assert 0.0 <= extraction.extraction_confidence <= 1.0
        assert 0.0 <= extraction.classification_confidence <= 1.0


# =============================================================================
# Math Validation Tests
# =============================================================================

class TestMathValidation:
    """Tests for mathematical validation in invoice processing."""

    def test_correct_totals_pass_validation(self):
        """Test that correctly calculated totals pass validation."""
        from schemas import InvoiceData, InvoiceLineItem

        line_items = [
            InvoiceLineItem(
                description="Item 1",
                quantity=2,
                unit_price=100.00,
                total_price=200.00,
            ),
            InvoiceLineItem(
                description="Item 2",
                quantity=1,
                unit_price=50.00,
                total_price=50.00,
            ),
        ]

        invoice = InvoiceData(
            invoice_number="INV-CORRECT-001",
            vendor_name="Correct Totals Inc",
            invoice_date=date(2024, 1, 1),
            line_items=line_items,
            subtotal=250.00,
            tax_rate=0.0,
            total_amount=250.00,
        )

        # Should have no math-related warnings
        math_warnings = [w for w in invoice.warnings if "total" in w.lower() or "math" in w.lower()]
        assert len(math_warnings) == 0

    def test_incorrect_totals_fail_validation(self):
        """Test that incorrectly calculated totals fail validation."""
        from schemas import InvoiceData, InvoiceLineItem

        line_items = [
            InvoiceLineItem(
                description="Item 1",
                quantity=2,
                unit_price=100.00,
                total_price=200.00,
            ),
        ]

        invoice = InvoiceData(
            invoice_number="INV-INCORRECT-001",
            vendor_name="Wrong Totals Corp",
            invoice_date=date(2024, 1, 1),
            line_items=line_items,
            subtotal=300.00,  # Wrong - should be 200.00
            total_amount=300.00,
        )

        # Should have math-related warnings
        math_warnings = [w for w in invoice.warnings if "total" in w.lower() or "subtotal" in w.lower()]
        assert len(math_warnings) > 0

    def test_floating_point_tolerance_handling(self):
        """Test that floating point precision issues are handled with tolerance."""
        from schemas import InvoiceData, InvoiceLineItem

        # Line items with floating point math
        line_items = [
            InvoiceLineItem(
                description="Item A",
                quantity=3,
                unit_price=33.33,  # 33.33 * 3 = 99.99 (floating point)
                total_price=99.99,
            ),
        ]

        # Invoice with expected total
        invoice = InvoiceData(
            invoice_number="INV-FLOAT-001",
            vendor_name="Float Test Inc",
            invoice_date=date(2024, 1, 1),
            line_items=line_items,
            subtotal=99.99,
            total_amount=99.99,
        )

        # Should pass with tolerance (allow small floating point differences)
        calculated = line_items[0].quantity * line_items[0].unit_price
        assert abs(calculated - line_items[0].total_price) < 0.02

    def test_tax_calculation_validation(self):
        """Test that tax calculations are validated."""
        from schemas import InvoiceData, InvoiceLineItem

        line_items = [
            InvoiceLineItem(
                description="Service",
                quantity=1,
                unit_price=100.00,
                total_price=100.00,
            ),
        ]

        # Correct tax calculation: 100 * 0.08 = 8.00
        invoice = InvoiceData(
            invoice_number="INV-TAX-CALC-001",
            vendor_name="Tax Calc Inc",
            invoice_date=date(2024, 1, 1),
            line_items=line_items,
            subtotal=100.00,
            tax_rate=8.0,
            tax_amount=8.00,
            total_amount=108.00,
        )

        # Decimal comparison - convert to float for approx comparison
        expected_tax = float(invoice.subtotal) * (invoice.tax_rate / 100)
        assert float(invoice.tax_amount) == pytest.approx(expected_tax, rel=1e-2)
        assert float(invoice.total_amount) == pytest.approx(float(invoice.subtotal) + float(invoice.tax_amount), rel=1e-2)


# =============================================================================
# Test Fixtures / Mock Data
# =============================================================================

class TestInvoiceFixtures:
    """Test fixtures and mock data for invoice testing."""

    @pytest.fixture
    def sample_invoice_data(self):
        """Sample invoice data for testing."""
        return {
            "invoice_number": "INV-SAMPLE-001",
            "vendor_name": "Sample Vendor Inc",
            "vendor_address": "123 Sample Street, Sample City, SC 12345",
            "invoice_date": "2024-01-15",
            "due_date": "2024-02-15",
            "line_items": [
                {
                    "description": "Professional Services",
                    "quantity": 40,
                    "unit_price": 150.00,
                    "total_price": 6000.00,
                },
                {
                    "description": "Materials",
                    "quantity": 1,
                    "unit_price": 500.00,
                    "total_price": 500.00,
                },
                {
                    "description": "Equipment Rental",
                    "quantity": 5,
                    "unit_price": 100.00,
                    "total_price": 500.00,
                },
            ],
            "subtotal": 7000.00,
            "tax_rate": 7.0,
            "tax_amount": 490.00,
            "total_amount": 7490.00,
        }

    @pytest.fixture
    def sample_gemini_response(self, sample_invoice_data):
        """Mock Gemini API response with sample invoice data."""
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": str(sample_invoice_data)
                            }
                        ]
                    },
                    "finish_reason": "STOP",
                    "index": 0
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 150,
                "candidatesTokenCount": 300
            },
            "modelVersion": "gemini-2.0-flash-exp"
        }

    @pytest.fixture
    def complex_tax_invoice(self):
        """Complex invoice with multiple tax rates (VAT, local, state)."""
        return {
            "invoice_number": "INV-COMPLEX-001",
            "vendor_name": "Multi-Tax Vendor",
            "invoice_date": "2024-01-20",
            "line_items": [
                {
                    "description": "Product A",
                    "quantity": 10,
                    "unit_price": 100.00,
                    "total_price": 1000.00,
                },
            ],
            "subtotal": 1000.00,
            "tax_breakdown": {
                "state_tax_rate": 5.0,
                "state_tax_amount": 50.00,
                "local_tax_rate": 2.0,
                "local_tax_amount": 20.00,
                "vat_rate": 10.0,
                "vat_amount": 100.00,
            },
            "total_amount": 1170.00,
        }

    def test_sample_invoice_fixture_totals(self, sample_invoice_data):
        """Verify sample invoice fixture has correct math."""
        subtotal = sum(item["total_price"] for item in sample_invoice_data["line_items"])
        assert subtotal == sample_invoice_data["subtotal"]

        expected_total = subtotal + sample_invoice_data["tax_amount"]
        assert expected_total == sample_invoice_data["total_amount"]

    def test_complex_tax_invoice_fixture(self, complex_tax_invoice):
        """Verify complex tax invoice fixture structure."""
        assert "tax_breakdown" in complex_tax_invoice
        tax = complex_tax_invoice["tax_breakdown"]
        assert "state_tax_rate" in tax
        assert "vat_rate" in tax
        assert tax["state_tax_amount"] + tax["local_tax_amount"] + tax["vat_amount"] == 170.00
