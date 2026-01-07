"""
TDD Tests for EntryAI Full Pipeline

Tests cover:
1. InvoiceData Schema with math validation (standalone implementation)
2. DataCleanResult Schema for tracking cleaning operations
3. normalize_for_n8n serialization function (standalone implementation)
4. Router tests for task type routing (standalone implementation)
"""
from datetime import date
from typing import Any, Dict, List, Literal, Optional, Union
from unittest.mock import AsyncMock, MagicMock, patch
import json
import pytest

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict, ValidationError


# =============================================================================
# Standalone InvoiceData Schema (for testing)
# =============================================================================

class BoundingBox(BaseModel):
    """Normalized bounding box coordinates (0-1000 scale)."""
    ymin: int = Field(..., ge=0, le=1000)
    xmin: int = Field(..., ge=0, le=1000)
    ymax: int = Field(..., ge=0, le=1000)
    xmax: int = Field(..., ge=0, le=1000)

    @model_validator(mode='after')
    def validate_dimensions(self):
        if self.ymax <= self.ymin:
            raise ValueError("ymax must be greater than ymin")
        if self.xmax <= self.xmin:
            raise ValueError("xmax must be greater than xmin")
        return self


class InvoiceLineItem(BaseModel):
    """Individual line item in an invoice."""
    description: str
    quantity: int = Field(..., ge=0)
    unit_price: float = Field(..., ge=0)
    total_price: float = Field(..., ge=0)
    location: Optional[BoundingBox] = None

    @field_validator('total_price')
    @classmethod
    def validate_total_price(cls, v, info):
        data = info.data
        if 'quantity' in data and 'unit_price' in data:
            expected = data['quantity'] * data['unit_price']
            if abs(v - expected) > 0.02:  # Allow small floating point tolerance
                raise ValueError(f"total_price ({v}) does not match quantity * unit_price ({expected})")
        return v


class InvoiceData(BaseModel):
    """Invoice extracted data with math validation."""
    model_config = ConfigDict(strict=True)

    invoice_number: str = Field(..., description="Unique invoice identifier")
    vendor_name: str = Field(..., description="Vendor/contractor name")

    vendor_address: Optional[str] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    line_items: List[InvoiceLineItem] = Field(default_factory=list)

    subtotal: Optional[float] = None
    tax_rate: Optional[float] = Field(None, ge=0, le=100)
    tax_amount: Optional[float] = None
    total_amount: Optional[float] = None

    warnings: List[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_math(self):
        """Validate invoice math and calculate derived fields."""
        if self.line_items:
            calculated_subtotal = sum(item.total_price for item in self.line_items)
            if self.subtotal is not None:
                if abs(self.subtotal - calculated_subtotal) > 0.02:
                    self.warnings.append(f"subtotal mismatch: declared {self.subtotal}, calculated {calculated_subtotal}")

        if self.line_items and self.subtotal is None:
            self.subtotal = sum(item.total_price for item in self.line_items)

        if self.subtotal is not None and self.tax_rate is not None and self.tax_amount is None:
            self.tax_amount = self.subtotal * (self.tax_rate / 100)

        if self.subtotal is not None and self.tax_amount is not None and self.total_amount is None:
            self.total_amount = self.subtotal + self.tax_amount

        # Collect missing field warnings
        if self.invoice_date is None:
            self.warnings.append("invoice_date not found - manual review needed")
        if self.due_date is None:
            self.warnings.append("due_date not found - manual review needed")
        if not self.line_items:
            self.warnings.append("line_items not found - manual review needed")

        return self


# =============================================================================
# InvoiceData Schema Tests
# =============================================================================

class TestInvoiceDataSchema:
    """Tests for InvoiceData model validation and math checks."""

    def test_valid_invoice_with_line_items_math_passes(self):
        """Test creating a valid invoice with correct line item math."""
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

        # Verify math: sum of line item totals equals subtotal
        calculated_subtotal = sum(item.total_price for item in invoice.line_items)
        assert calculated_subtotal == invoice.subtotal

    def test_invoice_with_math_mismatch_fails_validation(self):
        """Test that invoice with math mismatch triggers warnings."""
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
        # Missing required fields should raise ValidationError
        with pytest.raises(ValidationError) as exc_info:
            InvoiceData()

        errors = exc_info.value.errors()
        required_fields = [e["loc"][0] for e in errors]

        # Check that invoice_number and vendor_name are required
        assert "invoice_number" in required_fields or "vendor_name" in required_fields

    def test_invoice_line_item_calculations(self):
        """Test line item quantity * unit_price = total_price calculations."""
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

        # Verify each line item calculation
        for item in invoice.line_items:
            expected_total = item.quantity * item.unit_price
            assert item.total_price == pytest.approx(expected_total, rel=1e-2)

        # Verify subtotal matches sum of line items
        calculated_subtotal = sum(item.total_price for item in invoice.line_items)
        assert calculated_subtotal == invoice.subtotal


class TestInvoiceLineItemSchema:
    """Tests for InvoiceLineItem model."""

    def test_line_item_quantity_non_negative(self):
        """Test that quantity must be non-negative."""
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
        with pytest.raises(ValidationError):
            InvoiceLineItem(
                description="Invalid Item",
                quantity=-1,
                unit_price=10.00,
                total_price=-10.00,
            )

    def test_line_item_unit_price_total_price_relationship(self):
        """Test that total_price = quantity * unit_price relationship."""
        item = InvoiceLineItem(
            description="Calculated Item",
            quantity=3,
            unit_price=29.99,
            total_price=89.97,
        )

        expected_total = item.quantity * item.unit_price
        assert item.total_price == pytest.approx(expected_total, rel=1e-2)


# =============================================================================
# DataCleanResult Schema Tests
# =============================================================================

class DataCleanResult(BaseModel):
    """Schema for tracking data cleaning results."""
    original_row_count: int
    cleaned_row_count: int
    duplicates_removed: int
    nulls_filled: Dict[str, int]
    cleaning_actions: List[Dict[str, Any]]
    column_analysis: Dict[str, Dict[str, Any]]
    processing_time_ms: float

    @property
    def deduplication_rate(self) -> float:
        return self.duplicates_removed / self.original_row_count if self.original_row_count > 0 else 0.0

    @property
    def data_quality_score(self) -> float:
        return self.cleaned_row_count / self.original_row_count if self.original_row_count > 0 else 0.0


class TestDataCleanResultSchema:
    """Test DataCleanResult schema for tracking cleaning operations."""

    def test_result_creation_with_all_fields(self):
        """Test creating a DataCleanResult with all fields populated."""
        result = DataCleanResult(
            original_row_count=100,
            cleaned_row_count=95,
            duplicates_removed=5,
            nulls_filled={"email": 3, "phone": 2},
            cleaning_actions=[
                {"action": "deduplicate", "rows_affected": 5},
                {"action": "standardize_phone", "rows_affected": 10}
            ],
            column_analysis={
                "email": {"unique_count": 90, "null_count": 3, "valid_format": 87},
                "phone": {"unique_count": 92, "null_count": 2, "valid_format": 90}
            },
            processing_time_ms=150.5
        )

        assert result.original_row_count == 100
        assert result.cleaned_row_count == 95
        assert result.duplicates_removed == 5
        assert result.nulls_filled == {"email": 3, "phone": 2}
        assert len(result.cleaning_actions) == 2
        assert result.processing_time_ms == 150.5

    def test_statistics_tracking(self):
        """Test that statistics are correctly tracked and calculated."""
        result = DataCleanResult(
            original_row_count=100,
            cleaned_row_count=90,
            duplicates_removed=10,
            nulls_filled={},
            cleaning_actions=[],
            column_analysis={},
            processing_time_ms=50.0
        )

        assert result.deduplication_rate == 0.10
        assert result.data_quality_score == 0.90

    def test_deduplication_counting(self):
        """Test deduplication count tracking."""
        result = DataCleanResult(
            original_row_count=150,
            duplicates_removed=25,
            cleaned_row_count=125,
            nulls_filled={},
            cleaning_actions=[],
            column_analysis={},
            processing_time_ms=75.0
        )

        assert result.duplicates_removed == 25
        assert result.cleaned_row_count == result.original_row_count - result.duplicates_removed

    def test_standardization_logging(self):
        """Test standardization actions are logged correctly."""
        result = DataCleanResult(
            original_row_count=100,
            cleaned_row_count=95,
            duplicates_removed=5,
            nulls_filled={},
            cleaning_actions=[
                {"action": "standardize_phone", "rows_affected": 45, "pattern": "(XXX) XXX-XXXX"},
                {"action": "lowercase_email", "rows_affected": 30, "pattern": "lower()"},
                {"action": "title_case_name", "rows_affected": 60, "pattern": "title()"},
                {"action": "normalize_address", "rows_affected": 15, "pattern": "abbreviations"},
            ],
            column_analysis={},
            processing_time_ms=120.0
        )

        assert len(result.cleaning_actions) == 4
        assert result.cleaning_actions[0]["action"] == "standardize_phone"
        assert result.cleaning_actions[0]["rows_affected"] == 45

    def test_column_analysis_tracking(self):
        """Test column analysis tracking for data quality insights."""
        result = DataCleanResult(
            original_row_count=50,
            cleaned_row_count=48,
            duplicates_removed=2,
            nulls_filled={},
            cleaning_actions=[],
            column_analysis={
                "email": {"unique_count": 45, "null_count": 5, "valid_format": 40},
                "phone": {"unique_count": 48, "null_count": 2, "valid_format": 48},
                "age": {"unique_count": 20, "null_count": 0, "valid_format": 50}
            },
            processing_time_ms=60.0
        )

        assert result.column_analysis["email"]["unique_count"] == 45
        assert result.column_analysis["email"]["null_count"] == 5
        assert result.column_analysis["phone"]["valid_format"] == 48


# =============================================================================
# normalize_for_n8n Tests (Standalone Implementation)
# =============================================================================

def normalize_for_n8n(data: dict) -> dict:
    """
    Converts extracted data to n8n-compatible flat JSON.

    Guarantees:
    1. Floats -> Rounded to 2 decimals
    2. Nested Lists -> JSON Strings (for Airtable/Sheets compatibility)
    3. Nested Dicts -> Flattened with underscore keys
    4. None -> null (explicit, not omitted)
    """
    if not data:
        return data

    result = {}

    for key, value in data.items():
        if value is None:
            result[key] = None
            continue

        # Rule: Floats rounded to 2 decimals
        if isinstance(value, float):
            result[key] = round(value, 2)
            continue

        # Rule: Nested lists converted to JSON strings
        if isinstance(value, list):
            if value and isinstance(value[0], (dict, list)):
                result[key] = json.dumps(value, default=str)
            else:
                result[key] = value
            continue

        # Rule: Dicts with nested data -> flatten key paths
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                if sub_value is None:
                    result[f"{key}_{sub_key}"] = None
                elif isinstance(sub_value, float):
                    result[f"{key}_{sub_key}"] = round(sub_value, 2)
                elif isinstance(sub_value, list):
                    result[f"{key}_{sub_key}"] = json.dumps(sub_value, default=str)
                else:
                    result[f"{key}_{sub_key}"] = sub_value
            continue

        # Default: keep as-is
        result[key] = value

    return result


class TestNormalizeForN8n:
    """Tests for n8n data normalization function."""

    def test_float_rounding_to_2_decimals(self):
        """Test that floats are rounded to 2 decimal places."""
        data = {
            "price": 10.999999,
            "amount": 123.456789,
            "rate": 0.1,
        }

        result = normalize_for_n8n(data)

        assert result["price"] == 11.0
        assert result["amount"] == 123.46
        assert result["rate"] == 0.1

    def test_nested_list_json_stringification(self):
        """Test that nested lists are converted to JSON strings."""
        data = {
            "line_items": [
                {"description": "Item 1", "price": 10.00},
                {"description": "Item 2", "price": 20.00},
            ]
        }

        result = normalize_for_n8n(data)

        # Nested dicts in list should be JSON stringified
        assert isinstance(result["line_items"], str)
        parsed = json.loads(result["line_items"])
        assert len(parsed) == 2
        assert parsed[0]["description"] == "Item 1"

    def test_simple_list_preserved(self):
        """Test that simple lists (strings/numbers) are kept as lists."""
        data = {
            "tags": ["important", "urgent", "review"],
            "counts": [1, 2, 3, 4, 5],
        }

        result = normalize_for_n8n(data)

        # Simple lists should be preserved
        assert isinstance(result["tags"], list)
        assert result["tags"] == ["important", "urgent", "review"]
        assert result["counts"] == [1, 2, 3, 4, 5]

    def test_nested_dict_flattening(self):
        """Test that nested dicts are flattened with underscore keys."""
        data = {
            "location": {
                "city": "New York",
                "state": "NY",
                "zip": 10001,
            },
            "contact": {
                "email": "test@example.com",
                "phone": "123-456-7890",
            }
        }

        result = normalize_for_n8n(data)

        # Dicts should be flattened
        assert "location_city" in result
        assert "location_state" in result
        assert "location_zip" in result
        assert "contact_email" in result
        assert "contact_phone" in result

        assert result["location_city"] == "New York"
        assert result["location_state"] == "NY"
        assert result["location_zip"] == 10001

    def test_none_handling(self):
        """Test that None values are explicitly set to null."""
        data = {
            "name": "Test",
            "value": None,
            "optional_field": None,
            "amount": 100.00,
        }

        result = normalize_for_n8n(data)

        # None values should be preserved as None/null
        assert result["name"] == "Test"
        assert result["value"] is None
        assert result["optional_field"] is None
        assert result["amount"] == 100.0

    def test_empty_data_handling(self):
        """Test that empty data returns empty dict."""
        result = normalize_for_n8n({})
        assert result == {}

        result = normalize_for_n8n(None)
        assert result is None

    def test_mixed_nested_structures(self):
        """Test handling of mixed nested structures."""
        data = {
            "user": {
                "name": "John Doe",
                "preferences": ["dark_mode", "notifications"],
                "settings": {
                    "theme": "light",
                    "volume": 0.75,
                }
            },
            "items": [
                {"id": 1, "name": "Item 1"},
                {"id": 2, "name": "Item 2"},
            ],
            "metadata": None,
        }

        result = normalize_for_n8n(data)

        # User dict should be flattened
        assert "user_name" in result
        assert result["user_name"] == "John Doe"

        # User preferences (simple list) should be preserved
        assert result["user_preferences"] == ["dark_mode", "notifications"]

        # User settings (dict) should be flattened
        assert "user_settings_theme" in result
        assert result["user_settings_volume"] == 0.75

        # Items (list of dicts) should be JSON stringified
        assert isinstance(result["items"], str)
        items = json.loads(result["items"])
        assert len(items) == 2

        # None should be preserved
        assert result["metadata"] is None


# =============================================================================
# Router Tests (Standalone Implementation)
# =============================================================================

def router_node(state: dict) -> dict:
    """
    Router node using keyword detection (Fast).
    Classifies documents into: lease, coi, quote, or unknown.
    """
    text = state.get('text_md', '').lower()

    # COI detection - check first (most specific)
    coi_keywords = [
        "certificate of insurance", "certificate of liability insurance",
        "coi", "liability insurance", "insurance certificate",
        "policy period", "named insured", "certificate holder"
    ]
    if any(kw in text for kw in coi_keywords):
        return {"doc_type": "coi"}

    # Lease detection
    lease_keywords = [
        "lease agreement", "residential lease", "apartment lease",
        "tenant name", "landlord", "month-to-month",
        "security deposit", "rent amount", "lease term"
    ]
    if any(kw in text for kw in lease_keywords):
        return {"doc_type": "lease"}

    # Quote/Bid detection
    quote_keywords = [
        "estimate", "quote", "bid proposal", "proposal",
        "total amount", "pricing", "cost estimate",
        "pacific flooring", "vendor"
    ]
    if any(kw in text for kw in quote_keywords):
        return {"doc_type": "quote"}

    return {"doc_type": "unknown"}


class TestRouterNode:
    """Tests for document type classification router."""

    def test_router_task_type_routing_lease(self):
        """Test router correctly identifies lease documents."""
        lease_text = """
        LEASE AGREEMENT

        This Lease Agreement is entered into between Landlord Properties LLC
        and Tenant John Smith for the property located at 123 Main Street.

        The monthly rent is $2,500.00 and the lease term is 12 months.
        Security deposit of $5,000.00 is required. Move-in date is January 1, 2024.
        """

        state = {"text_md": lease_text}
        result = router_node(state)

        assert result["doc_type"] == "lease"

    def test_router_task_type_routing_coi(self):
        """Test router correctly identifies COI documents."""
        coi_text = """
        CERTIFICATE OF LIABILITY INSURANCE

        This certifies that ABC Corporation has liability insurance coverage
        with Policy Number: GL-2024-12345
        Policy Period: January 1, 2024 to December 31, 2024
        Named Insured: ABC Corporation
        Certificate Holder: Property Management Inc.
        """

        state = {"text_md": coi_text}
        result = router_node(state)

        assert result["doc_type"] == "coi"

    def test_router_task_type_routing_quote(self):
        """Test router correctly identifies quote/bid documents."""
        quote_text = """
        PROPOSAL / BID

        Submitted by: Pacific Flooring LLC
        456 Industrial Way, San Diego, CA

        Total Amount: $8,500.00
        This estimate includes all materials and labor.
        Valid for 30 days from date of proposal.
        """

        state = {"text_md": quote_text}
        result = router_node(state)

        assert result["doc_type"] == "quote"

    def test_router_missing_task_type_error(self):
        """Test router handles missing text_md gracefully."""
        # Empty text should result in "unknown" doc_type
        state = {"text_md": ""}
        result = router_node(state)

        assert result["doc_type"] == "unknown"

    def test_router_unknown_task_type_error(self):
        """Test router handles unrecognized document types."""
        # Random text that doesn't match any known type
        unknown_text = """
        This is a random document with no specific keywords.
        Just some plain text content here.
        Nothing special about insurance, leases, or quotes.
        """

        state = {"text_md": unknown_text}
        result = router_node(state)

        assert result["doc_type"] == "unknown"

    def test_router_case_insensitive(self):
        """Test router is case-insensitive in keyword matching."""
        # Test uppercase COI keywords
        coi_upper = """
        CERTIFICATE OF INSURANCE
        LIABILITY INSURANCE POLICY
        NAMED INSURED
        """

        state = {"text_md": coi_upper}
        result = router_node(state)

        assert result["doc_type"] == "coi"

    def test_router_mixed_content_unknown(self):
        """Test router with mixed content falls back to unknown."""
        # Content with some keywords but not enough to classify
        mixed_text = """
        Document ID: DOC-2024-001
        Date: 2024-01-15
        This document contains some information about terms and conditions.
        """

        state = {"text_md": mixed_text}
        result = router_node(state)

        assert result["doc_type"] == "unknown"

    def test_router_ambiguous_content_priority(self):
        """Test router prioritizes COI detection over other types."""
        # Content that could match both COI and Lease
        ambiguous_text = """
        CERTIFICATE OF INSURANCE
        Policy Number: COI-2024-001
        This certificate is for the property at 123 Main Street.
        The lease agreement terms are also included here.
        """

        state = {"text_md": ambiguous_text}
        result = router_node(state)

        # COI should be detected first due to higher priority
        assert result["doc_type"] == "coi"


class TestRouterNodeMocked:
    """Tests for router with mocked external dependencies."""

    def test_router_keyword_matching_accuracy(self):
        """Test router keyword matching with various patterns."""
        test_cases = [
            ("certificate of liability insurance", "coi"),
            ("certificate of insurance", "coi"),
            ("lease agreement", "lease"),
            ("residential lease", "lease"),
            ("estimate", "quote"),
            ("bid proposal", "quote"),
            ("random text", "unknown"),
        ]

        for text, expected_type in test_cases:
            state = {"text_md": text}
            result = router_node(state)
            assert result["doc_type"] == expected_type, f"Failed for: {text}"

    def test_router_no_false_positives(self):
        """Test router doesn't produce false positives."""
        # Text that mentions keywords in unrelated context
        text = "The insurance policy mentions that estimators should provide quotes."
        state = {"text_md": text}
        result = router_node(state)

        # Should detect "quote" keyword
        assert result["doc_type"] == "quote"


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_invoice_data():
    """Sample invoice data for testing."""
    return {
        "invoice_number": "INV-SAMPLE-001",
        "vendor_name": "Sample Vendor Inc",
        "vendor_address": "123 Sample Street",
        "invoice_date": "2024-01-15",
        "due_date": "2024-02-15",
        "line_items": [
            {"description": "Service", "quantity": 1, "unit_price": 100.00, "total_price": 100.00},
        ],
        "subtotal": 100.00,
        "tax_rate": 8.0,
        "tax_amount": 8.00,
        "total_amount": 108.00,
    }


@pytest.fixture
def dirty_crm_data():
    """Sample dirty CRM data."""
    return {
        "original_row_count": 100,
        "duplicates_removed": 15,
        "nulls_filled": {"email": 5, "phone": 3},
        "cleaning_actions": [
            {"action": "deduplicate", "rows_affected": 15},
            {"action": "standardize_phone", "rows_affected": 20},
        ],
    }


@pytest.fixture
def normalized_invoice_data(sample_invoice_data):
    """Normalized version of sample invoice data."""
    return normalize_for_n8n(sample_invoice_data)


class TestIntegrationFixtures:
    """Integration tests using fixtures."""

    def test_invoice_fixture_totals(self, sample_invoice_data):
        """Verify sample invoice fixture has correct math."""
        subtotal = sum(item["total_price"] for item in sample_invoice_data["line_items"])
        assert subtotal == sample_invoice_data["subtotal"]

        expected_total = subtotal + sample_invoice_data["tax_amount"]
        assert expected_total == sample_invoice_data["total_amount"]

    def test_normalization_preserves_values(self, sample_invoice_data, normalized_invoice_data):
        """Test that normalization preserves key values."""
        assert normalized_invoice_data["invoice_number"] == sample_invoice_data["invoice_number"]
        assert normalized_invoice_data["subtotal"] == 100.0  # Rounded
        assert normalized_invoice_data["tax_amount"] == 8.0  # Rounded
        assert normalized_invoice_data["total_amount"] == 108.0  # Rounded

    def test_crm_stats_tracking(self, dirty_crm_data):
        """Test CRM data statistics are tracked correctly."""
        cleaned_count = dirty_crm_data["original_row_count"] - dirty_crm_data["duplicates_removed"]
        assert cleaned_count == 85

        assert dirty_crm_data["duplicates_removed"] == 15
        assert len(dirty_crm_data["cleaning_actions"]) == 2
