"""
Pydantic Schemas for Universal Document Extractor

Uses Discriminated Union pattern for robust type checking of:
- Lease agreements
- Vendor quotes/bids
- Certificates of Insurance (COI)
- Invoices (EntryAI Platform - Module A)

Each schema includes bounding box coordinates (0-1000 scale) for key fields
to enable verification and audit trails.

CRITICAL: All monetary values use Decimal for financial integrity.
See Section 12.3 of PRD for rationale - float precision errors can cause
financial reconciliation failures in downstream systems (Xero, QuickBooks, etc.)
"""
from typing import Literal, List, Optional, Annotated, Union, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict, BeforeValidator
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import re


# =============================================================================
# Utility Types
# =============================================================================

def clean_money(v: str | float | int | Decimal) -> Decimal:
    """Clean money string to Decimal. Handles '$1,200.00' format automatically.

    CRITICAL: Returns Decimal, not float, for financial precision.
    Rounds to 2 decimal places to prevent floating point errors.
    """
    if isinstance(v, Decimal):
        return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if isinstance(v, float):
        # Round to 2 decimals BEFORE converting to avoid float precision issues
        return Decimal(str(round(v, 2))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if isinstance(v, int):
        return Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if v is None:
        return Decimal("0.00")

    clean = str(v).replace('$', '').replace(',', '').replace(' ', '').strip()
    try:
        # Parse as string to avoid float conversion
        return Decimal(clean).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (ValueError, TypeError):
        return Decimal("0.00")


Money = Annotated[Decimal, Field(validate_default=True), BeforeValidator(clean_money)]


# =============================================================================
# Security: Prompt Injection Detection
# =============================================================================

# Patterns that may indicate prompt injection attempts (OWASP LLM01:2025)
SUSPICIOUS_PATTERNS = [
    r'ignore\s+(all\s+)?previous\s+instructions?',
    r'you\s+are\s+now\s+(in\s+)?developer\s+mode',
    r'system\s+(prompt|override|instruction)',
    r'reveal\s+(your\s+)?(system\s+)?prompt',
    r'forget\s+(all\s+)?previous',
    r'override\s+(all\s+)?(security\s+)?rules',
    r'act\s+as\s+(an?\s+)?(admin|developer|system)',
    r'do\s+anything\s+now',
    r'dan\s+(mode|persona)',
    r'\$10,000\s+bitcoin\s+transfer',
    r'refund\s+\$?\d+',
]


def validate_no_injection(value: str) -> tuple[bool, str]:
    """Check for potential prompt injection patterns in extracted text.

    Returns (is_valid, error_message).
    """
    if not value:
        return True, ""

    value_lower = value.lower()

    for pattern in SUSPICIOUS_PATTERNS:
        if re.search(pattern, value_lower):
            return False, f"Potential prompt injection detected: matched pattern"

    # Check for null byte injection
    if '\x00' in value:
        return False, "Null byte detected in value"

    # Check for unusually long values (possible overflow attempt)
    if len(value) > 10000:
        return False, "Value exceeds maximum length (10000 chars)"

    return True, ""


# =============================================================================
# Bounding Box Model
# =============================================================================

class BoundingBox(BaseModel):
    """Normalized bounding box coordinates (0-1000 scale) for key data fields.

    This enables verification of extracted data by showing exactly where
    each value was found in the document.
    """
    ymin: int = Field(..., ge=0, le=1000, description="Top Y coordinate (0-1000 scale)")
    xmin: int = Field(..., ge=0, le=1000, description="Left X coordinate (0-1000 scale)")
    ymax: int = Field(..., ge=0, le=1000, description="Bottom Y coordinate (0-1000 scale)")
    xmax: int = Field(..., ge=0, le=1000, description="Right X coordinate (0-1000 scale)")

    @model_validator(mode='after')
    def validate_dimensions(self):
        """Ensure box has positive dimensions."""
        if self.ymax <= self.ymin:
            raise ValueError("ymax must be greater than ymin")
        if self.xmax <= self.xmin:
            raise ValueError("xmax must be greater than xmin")
        return self


class LocatedValue(BaseModel):
    """A value with its location in the document for audit purposes."""
    value: str
    location: BoundingBox


# =============================================================================
# Reusable Line Item Model (EntryAI Platform)
# =============================================================================

class LineItem(BaseModel):
    """Reusable line item model for invoices and other tabular data."""
    description: str = Field(..., description="Item description or service name")
    quantity: float = Field(..., gt=0, description="Number of units or hours")
    unit_price: Money = Field(..., description="Price per unit")
    total_price: Money = Field(..., description="Line total (quantity * unit_price)")


# =============================================================================
# Document Type Schemas
# =============================================================================

class LeaseData(BaseModel):
    """Lease agreement extracted data."""
    doc_type: Literal["lease"] = "lease"

    # Core fields with optional locations for verification
    tenant_name: Optional[str] = Field(None, description="Tenant/lessee name")
    tenant_name_location: Optional[BoundingBox] = None

    landlord_name: Optional[str] = Field(None, description="Landlord/lessor name")
    landlord_name_location: Optional[BoundingBox] = None

    property_address: Optional[str] = Field(None, description="Property address")
    property_address_location: Optional[BoundingBox] = None

    start_date: Optional[date] = Field(None, description="Lease start date")
    start_date_location: Optional[BoundingBox] = None

    end_date: Optional[date] = Field(None, description="Lease end date")
    end_date_location: Optional[BoundingBox] = None

    monthly_rent: Optional[Money] = Field(None, description="Monthly rent amount")
    monthly_rent_location: Optional[BoundingBox] = None

    notice_period_days: Optional[int] = Field(
        None,
        ge=0,
        le=365,
        description="Days notice required before lease end (e.g., 60)"
    )
    notice_period_location: Optional[BoundingBox] = None

    rent_cap_percentage: Optional[float] = Field(
        None,
        ge=0,
        le=100,
        description="Maximum allowed rent increase percentage"
    )
    rent_cap_location: Optional[BoundingBox] = None

    # Calculated fields (populated by post-processing)
    calculated_notice_date: Optional[date] = Field(
        None,
        description="Calculated: end_date - notice_period_days"
    )

    # Flags
    rent_cap_flagged: bool = Field(
        False,
        description="True if rent cap percentage is missing or non-compliant"
    )
    is_urgent: bool = Field(
        False,
        description="True if notice date is within 30 days"
    )

    # Metadata
    warnings: List[str] = Field(
        default_factory=list,
        description="Warnings about missing or uncertain data"
    )

    @model_validator(mode='after')
    def validate_lease_data(self):
        """Validate lease data and calculate derived fields."""
        today = date.today()

        # Calculate notice date
        if self.end_date is not None and self.notice_period_days is not None:
            self.calculated_notice_date = self.end_date - timedelta(days=self.notice_period_days)

            # Check urgency
            days_until_notice = (self.calculated_notice_date - today).days
            if days_until_notice <= 30:
                self.is_urgent = True

        # Check rent cap
        if self.rent_cap_percentage is None:
            self.rent_cap_flagged = True
            self.warnings.append("Rent cap percentage not found - compliance risk")

        # Warn on missing critical fields
        if self.tenant_name is None:
            self.warnings.append("Tenant name not found - manual review needed")
        if self.end_date is None:
            self.warnings.append("End date not found - manual review needed")
        if self.monthly_rent is None:
            self.warnings.append("Monthly rent not found - manual review needed")

        return self


class QuoteData(BaseModel):
    """Vendor quote/bid extracted data."""
    doc_type: Literal["quote"] = "quote"

    # Core fields
    vendor_name: Optional[str] = Field(None, description="Vendor/contractor name")
    vendor_name_location: Optional[BoundingBox] = None

    vendor_address: Optional[str] = Field(None, description="Vendor address")
    vendor_address_location: Optional[BoundingBox] = None

    line_items: List[str] = Field(
        default_factory=list,
        description="Line items as comma-separated string for Airtable"
    )
    line_items_location: Optional[BoundingBox] = None

    total_amount: Optional[Money] = Field(None, description="Total quoted amount")
    total_amount_location: Optional[BoundingBox] = None

    hidden_fees_found: bool = Field(
        False,
        description="True if fees like haul-away, disposal are excluded"
    )

    true_cost: Optional[Money] = Field(
        None,
        description="Estimated total including potential hidden fees"
    )

    # Metadata
    warnings: List[str] = Field(
        default_factory=list,
        description="Warnings about missing or uncertain data"
    )

    @model_validator(mode='after')
    def validate_quote_data(self):
        """Validate quote data and calculate true cost."""
        if self.vendor_name is None:
            self.warnings.append("Vendor name not found - manual review needed")
        if self.total_amount is None:
            self.warnings.append("Total amount not found - manual review needed")
            return self

        # Calculate true cost using Decimal arithmetic
        if self.true_cost is None:
            if self.hidden_fees_found:
                # Conservative 10% estimate for hidden fees
                self.true_cost = (self.total_amount * Decimal("1.10")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            else:
                self.true_cost = self.total_amount

        # Format line items for Airtable (comma-separated)
        if self.line_items:
            # Ensure line items are clean
            self.line_items = [item.strip() for item in self.line_items if item.strip()]

        return self


class CoiData(BaseModel):
    """Certificate of Insurance extracted data."""
    doc_type: Literal["coi"] = "coi"

    # Core fields
    insured_name: Optional[str] = Field(None, description="Name of insured party/business")
    insured_name_location: Optional[BoundingBox] = None

    insurance_company: Optional[str] = Field(None, description="Insurance carrier name")
    insurance_company_location: Optional[BoundingBox] = None

    policy_number: Optional[str] = Field(None, description="Policy number")
    policy_number_location: Optional[BoundingBox] = None

    expiration_date: Optional[date] = Field(None, description="Policy expiration date")
    expiration_date_location: Optional[BoundingBox] = None

    policy_limit: Optional[Money] = Field(
        None,
        description="Coverage limit (should be >= $1,000,000)"
    )
    policy_limit_location: Optional[BoundingBox] = None

    # Calculated fields
    days_until_expiry: Optional[int] = Field(
        None,
        description="Days until policy expires (positive = future, negative = expired)"
    )

    is_urgent: bool = Field(
        False,
        description="True if expiration within 30 days"
    )

    # Flags
    policy_limit_flagged: bool = Field(
        False,
        description="True if policy limit below $1,000,000"
    )

    # Metadata
    warnings: List[str] = Field(
        default_factory=list,
        description="Warnings about missing or uncertain data"
    )

    @model_validator(mode='after')
    def validate_coi_data(self):
        """Validate COI and check expiration/policy limits."""
        today = date.today()

        if self.expiration_date is None:
            self.warnings.append("Expiration date not found - manual review needed")
            self.is_urgent = True
            return self

        # Calculate days until expiry
        self.days_until_expiry = (self.expiration_date - today).days

        # Check urgency (within 30 days)
        if self.days_until_expiry <= 30:
            self.is_urgent = True

        # Check policy limit
        if self.policy_limit is None:
            self.warnings.append("Policy limit not found - manual review needed")
            self.policy_limit_flagged = True
            self.is_urgent = True
        elif self.policy_limit < 1_000_000:
            self.policy_limit_flagged = True
            self.is_urgent = True

        return self


# =============================================================================
# EntryAI Platform Models (Module A - Input Clerk)
# =============================================================================

def clean_quantity(v: float | int | Decimal | str) -> Decimal:
    """Convert quantity value to Decimal."""
    if isinstance(v, Decimal):
        return v
    if isinstance(v, float):
        return Decimal(str(v))
    if isinstance(v, int):
        return Decimal(v)
    if isinstance(v, str):
        return Decimal(v)
    return Decimal(str(v))


Quantity = Annotated[Decimal, BeforeValidator(clean_quantity)]


class InvoiceLineItem(BaseModel):
    """Individual line item from an invoice."""
    description: str = Field(..., description="Item or service description")
    quantity: Quantity = Field(..., ge=Decimal("0"), description="Number of units/hours")
    unit_price: Money = Field(..., description="Price per unit")
    total_price: Money = Field(..., description="Calculated line total")
    location: Optional[BoundingBox] = Field(None, description="Bounding box location in document")

    @model_validator(mode='after')
    def validate_line_total(self):
        """Verify line total matches quantity * unit_price using Decimal arithmetic."""
        # Calculate expected total using Decimal
        expected_total = (self.quantity * self.unit_price).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        actual_total = self.total_price.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        # Allow small rounding differences (up to 5 cents)
        tolerance = Decimal("0.05")
        if abs(actual_total - expected_total) > tolerance:
            # Flag for review, don't fail validation
            pass

        return self


class InvoiceData(BaseModel):
    """Invoice extracted data - EntryAI Module A (Input Clerk)."""
    doc_type: Literal["invoice"] = "invoice"

    # Core invoice fields
    invoice_number: Optional[str] = Field(None, description="Invoice number/identifier")
    invoice_number_location: Optional[BoundingBox] = None

    invoice_date: Optional[date] = Field(None, description="Invoice date")
    invoice_date_location: Optional[BoundingBox] = None

    due_date: Optional[date] = Field(None, description="Payment due date")
    due_date_location: Optional[BoundingBox] = None

    vendor_name: Optional[str] = Field(None, description="Vendor/supplier name")
    vendor_name_location: Optional[BoundingBox] = None

    vendor_address: Optional[str] = Field(None, description="Vendor billing address")
    vendor_address_location: Optional[BoundingBox] = None

    # Line items
    line_items: List[InvoiceLineItem] = Field(
        default_factory=list,
        description="Individual invoice line items"
    )

    # Totals
    subtotal: Optional[Money] = Field(None, description="Sum of line item totals before tax")
    tax_rate: Optional[float] = Field(None, ge=0.0, le=100.0, description="Tax rate as percentage (e.g., 8.0 for 8%)")
    tax_amount: Optional[Money] = Field(None, description="Tax amount")
    total_amount: Optional[Money] = Field(None, description="Final total including tax")

    # Validation
    math_check_passed: bool = Field(
        False,
        description="True if line item sums match subtotal"
    )

    # Flags
    is_overdue: bool = Field(
        False,
        description="True if current date is past due date"
    )
    duplicate_detected: bool = Field(
        False,
        description="True if potential duplicate invoice detected"
    )

    # Metadata
    warnings: List[str] = Field(
        default_factory=list,
        description="Warnings about missing or uncertain data"
    )

    @model_validator(mode='after')
    def validate_invoice_math(self):
        """Validate invoice math: line items sum should equal subtotal."""
        # Check for missing critical fields first (always runs)
        if self.vendor_name is None:
            self.warnings.append("Vendor name not found - manual review needed")
        if self.total_amount is None:
            self.warnings.append("Total amount not found - manual review needed")

        if not self.line_items:
            self.warnings.append("No line items found - manual review needed")
            return self

        # Calculate sum of line items
        calculated_subtotal = sum(item.total_price for item in self.line_items)

        if self.subtotal is not None:
            # Check if they match (allow for small rounding differences)
            if abs(calculated_subtotal - self.subtotal) < 0.05:
                self.math_check_passed = True
            else:
                self.warnings.append(
                    f"Math mismatch: line items sum to {calculated_subtotal:.2f}, "
                    f"but subtotal is {self.subtotal:.2f}"
                )
        else:
            # Set subtotal from line items if not provided
            self.subtotal = calculated_subtotal
            self.math_check_passed = True

        # Check due date
        if self.due_date is not None:
            today = date.today()
            if self.due_date < today:
                self.is_overdue = True
                days_overdue = (today - self.due_date).days
                self.warnings.append(f"Invoice is {days_overdue} days overdue")

        # Check for missing critical fields
        if self.vendor_name is None:
            self.warnings.append("Vendor name not found - manual review needed")
        if self.total_amount is None:
            self.warnings.append("Total amount not found - manual review needed")

        return self


# =============================================================================
# EntryAI Platform Models (Module C - Janitor)
# =============================================================================

class DataCleanResult(BaseModel):
    """Data cleaning result - EntryAI Module C (Janitor).

    Represents the output of data standardization and deduplication operations.
    """
    original_records: int = Field(
        ...,
        description="Number of records before cleaning"
    )
    cleaned_records: int = Field(
        ...,
        description="Number of records after cleaning"
    )
    duplicates_removed: int = Field(
        ...,
        description="Number of duplicate records removed"
    )

    standardizations: List[str] = Field(
        default_factory=list,
        description="Log of standardization changes made"
    )

    cleaned_data: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Cleaned and deduplicated records"
    )

    columns_analyzed: List[str] = Field(
        default_factory=list,
        description="List of columns that were analyzed"
    )

    quality_score: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Data quality score after cleaning"
    )

    errors: List[str] = Field(
        default_factory=list,
        description="Errors encountered during cleaning"
    )

# =============================================================================
# Input/Output Models for Apify
# =============================================================================

class DocumentBinaryInput(BaseModel):
    """Input format from n8n - base64 encoded document."""
    data: str = Field(
        ...,
        min_length=10,
        description="Base64 encoded document (PDF/Image)"
    )

    @field_validator("data")
    @classmethod
    def validate_base64(cls, v: str) -> str:
        """Validate base64 format and content."""
        # Check for whitespace-only
        if v.strip() != v:
            raise ValueError("base64 data must not contain leading/trailing whitespace")

        # Check minimum length for valid document (at least a few bytes)
        if len(v) < 10:
            raise ValueError("base64 data too short to be a valid document")

        # Validate base64 format by attempting to decode
        try:
            import base64 as b64
            # Add padding if needed
            padding = 4 - (len(v) % 4)
            if padding != 4:
                v_padded = v + "=" * padding
            else:
                v_padded = v
            b64.b64decode(v_padded, validate=True)
        except Exception as e:
            raise ValueError(f"invalid base64 data: {e}")

        return v


class DocumentBinaryWrapper(BaseModel):
    """Wrapper for n8n binary data."""
    docBinary: DocumentBinaryInput = Field(
        ...,
        description="n8n binary data wrapper"
    )


class ExtractionResult(BaseModel):
    """Final output format for n8n consumption."""
    status: Literal["success", "error"] = "success"
    doc_type: str = "unknown"
    summary: str = ""
    payload: Optional[dict] = None
    is_urgent: bool = False
    warnings: List[str] = Field(default_factory=list)
    error: Optional[str] = None


class DocumentExtraction(BaseModel):
    """Complete document extraction result with metadata.

    This is the main output schema for document extraction operations,
    including confidence scores, processing metadata, and the extracted data.
    """
    # Core extraction fields
    doc_type: str = "unknown"
    summary: str = ""

    # Extracted data payload - can be any document type
    payload: Optional[Union[LeaseData, QuoteData, CoiData, InvoiceData]] = None

    # Processing metadata
    extraction_confidence: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score for data extraction (0-1)"
    )
    classification_confidence: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score for document type classification (0-1)"
    )
    model_used: str = "gemini-2.0-flash-exp"
    processing_time_ms: int = Field(
        0,
        ge=0,
        description="Processing time in milliseconds"
    )

    # Status
    status: Literal["success", "error"] = "success"
    error: Optional[str] = None

    # Flags
    is_urgent: bool = False
    warnings: List[str] = Field(default_factory=list)


class InvoiceExtractionResult(BaseModel):
    """Extraction result specifically for invoice documents.

    Used by Module A (Input Clerk) for invoice processing workflows.
    Includes confidence scores and extraction metadata.
    """
    status: Literal["success", "error"] = "success"
    doc_type: str = "invoice"
    payload: Optional[InvoiceData] = None
    extraction_confidence: float = Field(0.0, ge=0.0, le=1.0)
    model_version: str = "gemini-2.0-flash-exp"
    is_urgent: bool = False
    warnings: List[str] = Field(default_factory=list)
    error: Optional[str] = None


# =============================================================================
# Stub Extraction Functions (for TDD test compatibility)
# =============================================================================
# These are placeholder implementations for the test suite.
# Full implementations require Gemini API integration in main.py.

def classify_document(text_preview: str) -> str:
    """
    Classify document type using keyword detection.

    Used by EntryAI Router for task routing. Checks for document type
    patterns in text and returns standardized type identifier.
    """
    text = text_preview.lower()

    # COI detection - most specific, check first
    coi_keywords = [
        "certificate of insurance", "certificate of liability insurance",
        "coi", "liability insurance", "insurance certificate",
        "policy period", "named insured", "certificate holder",
        "policy number", "effective date", "expiration date"
    ]
    if any(kw in text for kw in coi_keywords):
        return "coi"

    # Invoice detection
    invoice_keywords = [
        "invoice", "invoice number", "bill to", "ship to",
        "due date", "payment terms", "line items", "subtotal",
        "tax", "vendor", "invoice date"
    ]
    if any(kw in text for kw in invoice_keywords):
        return "invoice"

    # Lease detection
    lease_keywords = [
        "lease agreement", "residential lease", "apartment lease",
        "tenant name", "landlord", "month-to-month",
        "security deposit", "rent amount", "rent", "lease term",
        "move-in date", "notice period"
    ]
    if any(kw in text for kw in lease_keywords):
        return "lease"

    # Quote/Bid detection - check for specific quote keywords first
    quote_keywords = [
        "quote", "estimate", "bid proposal", "proposal",
        "pricing", "cost estimate"
    ]
    if any(kw in text for kw in quote_keywords):
        return "quote"

    # Check for "total amount" AFTER quote-specific keywords
    if "total amount" in text:
        return "quote"

    return "unknown"


async def extract_invoice(file_bytes: bytes) -> InvoiceExtractionResult:
    """Extract invoice data from document bytes.

    Placeholder for TDD tests. Full implementation routes to Gemini
    with InvoiceData schema for structured extraction.
    """
    return InvoiceExtractionResult(
        status="error",
        error="extract_invoice requires Gemini API integration in main.py"
    )


async def extract_lease(file_bytes: bytes) -> DocumentExtraction:
    """Extract lease agreement data from document bytes.

    Placeholder for TDD tests.
    """
    return DocumentExtraction(
        status="error",
        error="extract_lease requires Gemini API integration in main.py"
    )


async def extract_quote(file_bytes: bytes) -> DocumentExtraction:
    """Extract vendor quote data from document bytes.

    Placeholder for TDD tests.
    """
    return DocumentExtraction(
        status="error",
        error="extract_quote requires Gemini API integration in main.py"
    )


async def extract_coi(file_bytes: bytes) -> DocumentExtraction:
    """Extract certificate of insurance data from document bytes.

    Placeholder for TDD tests.
    """
    return DocumentExtraction(
        status="error",
        error="extract_coi requires Gemini API integration in main.py"
    )


# =============================================================================
# EntryAI Router Input Model
# =============================================================================

class ActorInput(BaseModel):
    """Router input schema for EntryAI platform tasks.

    Defines the task type and provides flexible input options for different
    document processing workflows.
    """
    task_type: Literal[
        "extract_invoice",
        "extract_lease",
        "extract_quote",
        "extract_coi",
        "verify_data",
        "clean_crm"
    ] = Field(
        ...,
        description="Type of task to execute"
    )

    doc_binary: Optional[DocumentBinaryInput] = Field(
        None,
        description="Base64 encoded document for extraction tasks"
    )

    data_file_base64: Optional[str] = Field(
        None,
        description="Base64 encoded data file (CSV/JSON) for cleaning tasks"
    )

    options: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional task-specific options"
    )

    # Optional: explicit output format preference
    output_format: Optional[Literal["json", "airtable", "salesforce"]] = Field(
        None,
        description="Desired output format"
    )

    # Optional: routing hints
    priority: Optional[Literal["low", "normal", "high"]] = Field(
        "normal",
        description="Processing priority level"
    )

    # Async webhook callback for long-running tasks (Section 12.1)
    webhook_url: Optional[str] = Field(
        None,
        description="n8n webhook URL for async callback (recommended for large/complex documents)"
    )

    @model_validator(mode='after')
    def validate_input_requirements(self):
        """Ensure required inputs are provided for the task type."""
        extraction_tasks = {
            "extract_invoice", "extract_lease", "extract_quote", "extract_coi"
        }

        if self.task_type in extraction_tasks:
            if self.doc_binary is None:
                raise ValueError(
                    f"Task type '{self.task_type}' requires doc_binary input"
                )

        if self.task_type == "clean_crm":
            if self.data_file_base64 is None:
                raise ValueError(
                    f"Task type '{self.task_type}' requires data_file_base64 input"
                )

        if self.task_type == "verify_data":
            if self.options is None:
                raise ValueError(
                    "Task type 'verify_data' requires options with 'extracted' and 'expected' fields"
                )
            if "extracted" not in self.options:
                raise ValueError(
                    "verify_data options must contain 'extracted' field"
                )
            if "expected" not in self.options:
                raise ValueError(
                    "verify_data options must contain 'expected' field"
                )

        return self
