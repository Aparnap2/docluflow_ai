"""
Pydantic Schemas for Universal Document Extractor

Uses Discriminated Union pattern for robust type checking of:
- Lease agreements
- Vendor quotes/bids
- Certificates of Insurance (COI)

Each schema includes bounding box coordinates (0-1000 scale) for key fields
to enable verification and audit trails.
"""
from typing import Literal, List, Optional, Annotated, Union
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from datetime import date, timedelta
import re


# =============================================================================
# Utility Types
# =============================================================================

def clean_money(v: str | float | int) -> float:
    """Clean money string to float. Handles '$1,200.00' format automatically."""
    if isinstance(v, float):
        return v
    if isinstance(v, int):
        return float(v)
    if v is None:
        return 0.0

    clean = str(v).replace('$', '').replace(',', '').replace(' ', '').strip()
    try:
        return float(clean)
    except (ValueError, TypeError):
        return 0.0


Money = Annotated[float, Field(validate_default=True), BeforeValidator(clean_money)]


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

        # Calculate true cost
        if self.true_cost is None:
            if self.hidden_fees_found:
                # Conservative 10% estimate for hidden fees
                self.true_cost = self.total_amount * 1.10
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
# Master Document Extraction Model (Discriminated Union)
# =============================================================================

class DocumentExtraction(BaseModel):
    """Master model for document extraction results.

    Uses discriminated union via `doc_type` field to enforce strict type
    checking and ensure only one document type is populated at a time.
    """
    model_config = ConfigDict(strict=True)

    # Classification
    doc_type: Literal["lease", "quote", "coi", "unknown"] = "unknown"

    # Summary generated by Gemini
    summary: str = Field(
        "",
        description="Brief 1-2 sentence summary of the document"
    )

    # Document-specific payload (discriminated union)
    payload: Union[LeaseData, QuoteData, CoiData, None] = Field(
        None,
        description="Extracted data specific to document type"
    )

    # Confidence scores (0.0 - 1.0)
    extraction_confidence: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score for the extraction"
    )
    classification_confidence: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score for document type classification"
    )

    # Processing metadata
    model_used: str = Field(
        "gemini-2.0-flash-exp",
        description="AI model used for extraction"
    )
    processing_time_ms: Optional[int] = None

    # Status
    status: Literal["success", "partial_success", "error"] = "success"
    error_message: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_output(self):
        """Ensure payload matches doc_type."""
        if self.payload is not None:
            expected_type = self.doc_type.upper()
            actual_type = self.payload.doc_type.upper()
            if actual_type != expected_type:
                self.warnings.append(
                    f"Type mismatch: doc_type={self.doc_type} but payload type={actual_type}"
                )
        return self


# =============================================================================
# Input/Output Models for Apify
# =============================================================================

class DocumentBinaryInput(BaseModel):
    """Input format from n8n - base64 encoded document."""
    data: str = Field(..., description="Base64 encoded document (PDF/Image)")


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
