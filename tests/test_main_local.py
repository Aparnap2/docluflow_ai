"""
Tests for main_local.py - Local Development Server

Tests the FastAPI server endpoints and stub extraction logic
for n8n integration without requiring Apify Cloud or Gemini API.
"""
import base64
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_pdf_base64() -> str:
    """Generate a sample base64-encoded 'PDF' for testing."""
    # This is just a text file encoded as base64 (not a real PDF)
    sample_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>
endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer
<< /Size 4 /Root 1 0 R >>
startxref
149
%%EOF
Invoice from Acme Corp
Invoice Number: INV-2024-001
Total Amount: $1,500.00
"""
    return base64.b64encode(sample_content).decode("utf-8")


@pytest.fixture
def sample_invoice_base64(sample_pdf_base64) -> str:
    """Sample invoice content for classification."""
    content = b"""%PDF-1.4
INVOICE
Invoice Number: INV-2024-001
Invoice Date: 2024-01-15
Total Amount: $1,500.00
Vendor: Acme Corp
Bill To: John Doe
Subtotal: $1,350.00
Tax: $150.00
"""
    return base64.b64encode(content).decode("utf-8")


@pytest.fixture
def sample_coi_base64() -> str:
    """Sample COI content for classification."""
    content = b"""%PDF-1.4
CERTIFICATE OF INSURANCE
Policy Number: GL-2024-1234
Insured Name: ABC Corporation
Insurance Company: XYZ Insurance Co
Expiration Date: 2025-12-31
Coverage Limit: $2,000,000.00
"""
    return base64.b64encode(content).decode("utf-8")


@pytest.fixture
def sample_lease_base64() -> str:
    """Sample lease content for classification."""
    content = b"""%PDF-1.4
RESIDENTIAL LEASE AGREEMENT
Tenant: John Doe
Landlord: Property Management Inc
Monthly Rent: $2,500.00
Security Deposit: $5,000.00
Start Date: 2024-01-01
End Date: 2024-12-31
"""
    return base64.b64encode(content).decode("utf-8")


@pytest.fixture
def sample_quote_base64() -> str:
    """Sample quote content for classification."""
    content = b"""%PDF-1.4
VENDOR QUOTE - PROPOSAL
Quote Number: Q-2024-001
Vendor Name: Tech Solutions LLC
Quote Date: 2024-01-10
Valid Until: 2024-02-10
Estimate Total: $5,500.00
This is a pricing proposal for your review.
"""
    return base64.b64encode(content).decode("utf-8")


# =============================================================================
# Test Client Setup
# =============================================================================

@pytest.fixture
def client():
    """Create test client for the FastAPI app."""
    from main_local import app
    return TestClient(app)


# =============================================================================
# Health Check Tests
# =============================================================================

class TestHealthCheck:
    """Tests for health check endpoint."""

    def test_health_check_returns_healthy(self, client):
        """Health check should return healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "entryai-local"

    def test_root_endpoint_returns_info(self, client):
        """Root endpoint should return service info."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "EntryAI Local Server"
        assert data["mode"] == "stub"


# =============================================================================
# Classification Tests
# =============================================================================

class TestClassification:
    """Tests for document classification."""

    def test_classify_invoice(self, sample_invoice_base64):
        """Invoice content should be classified as invoice."""
        from main_local import classify_document

        file_bytes = base64.b64decode(sample_invoice_base64)
        text_preview = file_bytes[:2048].decode("utf-8", errors="ignore")

        doc_type = classify_document(text_preview)
        assert doc_type == "invoice"

    def test_classify_coi(self, sample_coi_base64):
        """COI content should be classified as coi."""
        from main_local import classify_document

        file_bytes = base64.b64decode(sample_coi_base64)
        text_preview = file_bytes[:2048].decode("utf-8", errors="ignore")

        doc_type = classify_document(text_preview)
        assert doc_type == "coi"

    def test_classify_lease(self, sample_lease_base64):
        """Lease content should be classified as lease."""
        from main_local import classify_document

        file_bytes = base64.b64decode(sample_lease_base64)
        text_preview = file_bytes[:2048].decode("utf-8", errors="ignore")

        doc_type = classify_document(text_preview)
        assert doc_type == "lease"

    def test_classify_quote(self, sample_quote_base64):
        """Quote content should be classified as quote."""
        from main_local import classify_document

        file_bytes = base64.b64decode(sample_quote_base64)
        text_preview = file_bytes[:2048].decode("utf-8", errors="ignore")

        doc_type = classify_document(text_preview)
        assert doc_type == "quote"


# =============================================================================
# Stub Extraction Tests
# =============================================================================

class TestStubExtraction:
    """Tests for stub extraction functions."""

    @pytest.mark.asyncio
    async def test_extract_invoice_stub(self, sample_invoice_base64):
        """Invoice stub extraction should return invoice data."""
        from main_local import extract_invoice_stub

        file_bytes = base64.b64decode(sample_invoice_base64)
        result = await extract_invoice_stub(file_bytes, "invoice")

        assert result.status == "success"
        assert result.doc_type == "invoice"
        assert result.payload["invoice_number"] == "INV-STUB-001"
        assert result.payload["vendor_name"] == "Acme Corp (Stub)"
        assert result.payload["total_amount"] == 1500.00
        assert "warnings" in result.model_dump()
        assert len(result.warnings) > 0

    @pytest.mark.asyncio
    async def test_extract_coi_stub(self, sample_coi_base64):
        """COI stub extraction should return COI data."""
        from main_local import extract_coi_stub

        file_bytes = base64.b64decode(sample_coi_base64)
        result = await extract_coi_stub(file_bytes, "coi")

        assert result.status == "success"
        assert result.doc_type == "coi"
        assert result.payload["policy_number"] == "GL-2024-1234"
        assert result.payload["policy_limit"] == 2000000.00
        assert result.payload["days_until_expiry"] == 358

    @pytest.mark.asyncio
    async def test_extract_lease_stub(self, sample_lease_base64):
        """Lease stub extraction should return lease data."""
        from main_local import extract_lease_stub

        file_bytes = base64.b64decode(sample_lease_base64)
        result = await extract_lease_stub(file_bytes, "lease")

        assert result.status == "success"
        assert result.doc_type == "lease"
        assert result.payload["monthly_rent"] == 2500.00
        assert result.payload["security_deposit"] == 5000.00

    @pytest.mark.asyncio
    async def test_extract_quote_stub(self, sample_quote_base64):
        """Quote stub extraction should return quote data."""
        from main_local import extract_quote_stub

        file_bytes = base64.b64decode(sample_quote_base64)
        result = await extract_quote_stub(file_bytes, "quote")

        assert result.status == "success"
        assert result.doc_type == "quote"
        assert result.payload["quote_number"] == "Q-2024-001"
        assert result.payload["total_amount"] == 5500.00


# =============================================================================
# Endpoint Tests
# =============================================================================

class TestRunSyncEndpoint:
    """Tests for /run-sync endpoint."""

    def test_run_sync_success(self, client, sample_invoice_base64):
        """Valid request should return extraction result."""
        response = client.post(
            "/run-sync",
            json={
                "data": sample_invoice_base64,
                "task_type": "extract_invoice"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["doc_type"] == "invoice"
        assert "payload" in data
        assert "invoice_number" in data["payload"]

    def test_run_sync_missing_data(self, client):
        """Missing data field should return 400 error."""
        response = client.post(
            "/run-sync",
            json={"task_type": "extract_invoice"}
        )

        assert response.status_code == 400
        # The actual error message from handle_extraction
        detail = response.json()["detail"]
        assert "data" in detail.lower()

    def test_run_sync_invalid_base64(self, client):
        """Invalid base64 should return 400 error."""
        response = client.post(
            "/run-sync",
            json={
                "data": "not-valid-base64!!!",
                "task_type": "extract_invoice"
            }
        )

        assert response.status_code == 400
        assert "Invalid base64" in response.json()["detail"]

    def test_run_sync_auto_classification(self, client, sample_coi_base64):
        """ COI should be auto-classified from content."""
        response = client.post(
            "/run-sync",
            json={"data": sample_coi_base64}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["doc_type"] == "coi"


class TestProcessEndpoint:
    """Tests for /process endpoint (n8n workflow)."""

    def test_process_success(self, client, sample_invoice_base64):
        """Valid request to /process should work."""
        response = client.post(
            "/process",
            json={
                "data": sample_invoice_base64,
                "task_type": "extract_invoice"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["doc_type"] == "invoice"

    def test_process_lease(self, client, sample_lease_base64):
        """Lease extraction via /process."""
        response = client.post(
            "/process",
            json={
                "data": sample_lease_base64,
                "task_type": "extract_lease"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["doc_type"] == "lease"
        assert data["payload"]["monthly_rent"] == 2500.00


class TestSimplifiedEndpoints:
    """Tests for simplified extraction endpoints."""

    def test_extract_invoice_endpoint(self, client, sample_invoice_base64):
        """Direct invoice extraction endpoint."""
        response = client.post(
            "/extract/invoice",
            json={"data": sample_invoice_base64}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["doc_type"] == "invoice"
        assert data["payload"]["total_amount"] == 1500.00

    def test_extract_coi_endpoint(self, client, sample_coi_base64):
        """Direct COI extraction endpoint."""
        response = client.post(
            "/extract/coi",
            json={"data": sample_coi_base64}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["doc_type"] == "coi"

    def test_extract_lease_endpoint(self, client, sample_lease_base64):
        """Direct lease extraction endpoint."""
        response = client.post(
            "/extract/lease",
            json={"data": sample_lease_base64}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["doc_type"] == "lease"

    def test_extract_quote_endpoint(self, client, sample_quote_base64):
        """Direct quote extraction endpoint."""
        response = client.post(
            "/extract/quote",
            json={"data": sample_quote_base64}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["doc_type"] == "quote"


class TestClassifyEndpoint:
    """Tests for /classify endpoint."""

    def test_classify_endpoint_invoice(self, client, sample_invoice_base64):
        """Classification endpoint should identify invoice."""
        response = client.post(
            "/classify",
            json={"data": sample_invoice_base64}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["doc_type"] == "invoice"
        assert "confidence" in data

    def test_classify_endpoint_coi(self, client, sample_coi_base64):
        """Classification endpoint should identify COI."""
        response = client.post(
            "/classify",
            json={"data": sample_coi_base64}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["doc_type"] == "coi"


# =============================================================================
# Normalization Tests
# =============================================================================

class TestNormalization:
    """Tests for n8n output normalization."""

    def test_normalize_success_result(self):
        """Success result should normalize correctly."""
        from main_local import ExtractionResult, normalize_for_n8n

        result = ExtractionResult(
            status="success",
            doc_type="invoice",
            summary="Test extraction",
            payload={"total": 100},
            is_urgent=False,
            warnings=["test warning"],
        )

        normalized = normalize_for_n8n(result)

        assert normalized["status"] == "success"
        assert normalized["doc_type"] == "invoice"
        assert normalized["summary"] == "Test extraction"
        assert normalized["payload"]["total"] == 100
        assert normalized["is_urgent"] is False
        assert normalized["warnings"] == ["test warning"]
        assert normalized["error"] is None

    def test_normalize_error_result(self):
        """Error result should normalize correctly."""
        from main_local import ExtractionResult, normalize_for_n8n

        result = ExtractionResult(
            status="error",
            doc_type="unknown",
            summary="Test error",
            error="Something went wrong",
        )

        normalized = normalize_for_n8n(result)

        assert normalized["status"] == "error"
        assert normalized["doc_type"] == "unknown"
        assert normalized["error"] == "Something went wrong"


# =============================================================================
# Schema Validation Tests
# =============================================================================

class TestSchemaValidation:
    """Tests for Pydantic schema validation."""

    def test_document_binary_input_valid(self):
        """Valid base64 should pass validation."""
        from main_local import DocumentBinaryInput

        input_data = DocumentBinaryInput(data="SGVsbG8gV29ybGQ=")
        assert input_data.data == "SGVsbG8gV29ybGQ="

    def test_document_binary_input_too_short(self):
        """Base64 shorter than 10 chars should fail."""
        from main_local import DocumentBinaryInput
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DocumentBinaryInput(data="abc")

    def test_actor_input_valid(self):
        """Valid ActorInput should pass validation."""
        from main_local import ActorInput, DocumentBinaryInput

        input_data = ActorInput(
            task_type="extract_invoice",
            doc_binary=DocumentBinaryInput(data="SGVsbG8gV29ybGQ="),
        )

        assert input_data.task_type == "extract_invoice"
        assert input_data.doc_binary is not None

    def test_actor_input_task_types(self):
        """All task types should be valid."""
        from main_local import ActorInput, DocumentBinaryInput

        valid_types = [
            "extract_invoice", "extract_lease", "extract_quote",
            "extract_coi", "verify_data", "clean_crm"
        ]

        for task_type in valid_types:
            input_data = ActorInput(task_type=task_type)
            assert input_data.task_type == task_type
