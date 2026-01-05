from typing import Literal, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import date, timedelta

class LeaseSchema(BaseModel):
    doc_type: Literal["lease"] = "lease"
    tenant_name: Optional[str] = None  # Made Optional to prevent hallucination
    end_date: Optional[date] = None  # Made Optional to prevent hallucination
    notice_period_days: Optional[int] = Field(None, description="Days notice required (e.g., 60)")
    calculated_notice_date: Optional[date] = None
    rent_cap_percentage: Optional[float] = Field(None, description="Rent increase cap percentage (e.g., 5.0 for 5%)")
    rent_cap_flagged: bool = False
    warnings: List[str] = Field(default_factory=list, description="Warnings about missing or uncertain data")

    # LOGIC INSIDE SCHEMA: Differentiator
    @model_validator(mode='after')
    def calc_date_and_flag_rent_cap(self):
        # Prevent silent failures - warn if critical fields are missing
        if self.tenant_name is None:
            self.warnings.append("Tenant name not found - Manual Review Needed")
        if self.end_date is None:
            self.warnings.append("Lease end date not found - Manual Review Needed")
        
        # Calculate notice date if we have the required fields
        if self.end_date is not None and self.notice_period_days is not None:
            if self.calculated_notice_date is None:
                self.calculated_notice_date = self.end_date - timedelta(days=self.notice_period_days)
        elif self.end_date is not None and self.notice_period_days is None:
            self.warnings.append("Notice period not found - Manual Review Needed. Cannot calculate notice date.")
        
        # Flag if rent cap is missing (important for compliance)
        # PRD: "Flag Rent Cap %"
        if self.rent_cap_percentage is None:
            self.rent_cap_flagged = True
            self.warnings.append("Rent cap percentage not found - Compliance Risk")
        
        return self

class QuoteSchema(BaseModel):
    doc_type: Literal["quote"] = "quote"
    vendor_name: Optional[str] = None  # Made Optional to prevent hallucination
    total_amount: Optional[float] = None  # Made Optional to prevent hallucination
    hidden_fees_found: bool = Field(default=False, description="True if fees like 'haul-away' are excluded")
    line_items_standardized: List[str] = Field(default_factory=list)
    true_cost: Optional[float] = None
    warnings: List[str] = Field(default_factory=list, description="Warnings about missing or uncertain data")

    # LOGIC INSIDE SCHEMA: Differentiator
    # PRD: "Rank by 'True Cost'" - Calculate total including hidden fees
    @model_validator(mode='after')
    def calc_true_cost(self):
        # Prevent silent failures - warn if critical fields are missing
        if self.vendor_name is None:
            self.warnings.append("Vendor name not found - Manual Review Needed")
        if self.total_amount is None:
            self.warnings.append("Total amount not found - Manual Review Needed")
            self.true_cost = None
            return self
        
        # Calculate true cost including hidden fees for bid comparison
        if self.true_cost is None:
            if self.hidden_fees_found:
                # Estimate hidden fees as 10% of total (conservative estimate)
                # This enables "Rank by True Cost" functionality
                estimated_hidden = self.total_amount * 0.10
                self.true_cost = self.total_amount + estimated_hidden
            else:
                self.true_cost = self.total_amount
        return self

class CoiSchema(BaseModel):
    doc_type: Literal["coi"] = "coi"
    expiration_date: Optional[date] = None  # Made Optional to prevent hallucination
    policy_limit: Optional[float] = Field(None, description="Policy limit in dollars")
    is_critical: bool = False
    policy_limit_flagged: bool = False
    warnings: List[str] = Field(default_factory=list, description="Warnings about missing or uncertain data")

    @model_validator(mode='after')
    def check_critical_and_policy_limit(self):
        # Prevent silent failures - warn if critical fields are missing
        if self.expiration_date is None:
            self.warnings.append("Expiration date not found - Manual Review Needed")
            self.is_critical = True  # Mark as critical if we can't verify expiration
            return self
        
        # PRD: "Check if Expiration < Today + 30. Check Policy Limit > $1M"
        days_left = (self.expiration_date - date.today()).days
        
        # Auto-flag if expiring in < 30 days
        if days_left < 30:
            self.is_critical = True
        
        # Check policy limit - flag if below $1M
        # PRD: "Check Policy Limit > $1M"
        if self.policy_limit is None:
            self.warnings.append("Policy limit not found - Manual Review Needed")
        elif self.policy_limit < 1_000_000:
            self.policy_limit_flagged = True
            self.is_critical = True  # Also mark as critical if policy limit too low
        
        return self