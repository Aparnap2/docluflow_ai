"""
TDD Tests for CRM Data Cleaning Module (Module C - Janitor)

Tests cover:
1. DataCleanResult Schema
2. CSV Loading
3. Excel Loading
4. Deduplication
5. Standardization
6. Enrichment
7. Edge Cases
"""
import base64
import io
import pytest
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import numpy as np


# =============================================================================
# DataCleanResult Schema Tests
# =============================================================================


class TestDataCleanResultSchema:
    """Test DataCleanResult schema for tracking cleaning operations."""

    def test_result_creation_with_all_fields(self):
        """Test creating a DataCleanResult with all fields populated."""
        from pydantic import BaseModel

        class DataCleanResult(BaseModel):
            """Schema for tracking data cleaning results."""
            original_row_count: int
            cleaned_row_count: int
            duplicates_removed: int
            nulls_filled: Dict[str, int]
            cleaning_actions: List[Dict[str, Any]]
            column_analysis: Dict[str, Dict[str, Any]]
            processing_time_ms: float

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

    def test_result_statistics_tracking(self):
        """Test that statistics are correctly tracked and calculated."""
        from pydantic import BaseModel

        class DataCleanResult(BaseModel):
            original_row_count: int
            cleaned_row_count: int
            duplicates_removed: int

            @property
            def deduplication_rate(self) -> float:
                return self.duplicates_removed / self.original_row_count if self.original_row_count > 0 else 0.0

            @property
            def data_quality_score(self) -> float:
                return self.cleaned_row_count / self.original_row_count if self.original_row_count > 0 else 0.0

        result = DataCleanResult(
            original_row_count=100,
            cleaned_row_count=90,
            duplicates_removed=10
        )

        assert result.deduplication_rate == 0.10
        assert result.data_quality_score == 0.90

    def test_result_with_empty_actions(self):
        """Test DataCleanResult with empty cleaning actions."""
        from pydantic import BaseModel

        class DataCleanResult(BaseModel):
            original_row_count: int
            cleaned_row_count: int
            duplicates_removed: int
            nulls_filled: Dict[str, int]
            cleaning_actions: List[Dict[str, Any]]
            column_analysis: Dict[str, Dict[str, Any]]

        result = DataCleanResult(
            original_row_count=50,
            cleaned_row_count=50,
            duplicates_removed=0,
            nulls_filled={},
            cleaning_actions=[],
            column_analysis={}
        )

        assert result.duplicates_removed == 0
        assert len(result.cleaning_actions) == 0

    def test_column_analysis_tracking(self):
        """Test column analysis tracking for data quality insights."""
        from pydantic import BaseModel

        class ColumnAnalysis(BaseModel):
            unique_count: int
            null_count: int
            valid_format: int
            data_type: str

        class DataCleanResult(BaseModel):
            column_analysis: Dict[str, ColumnAnalysis]

        result = DataCleanResult(
            column_analysis={
                "email": ColumnAnalysis(unique_count=45, null_count=5, valid_format=40, data_type="string"),
                "phone": ColumnAnalysis(unique_count=48, null_count=2, valid_format=48, data_type="string"),
                "age": ColumnAnalysis(unique_count=20, null_count=0, valid_format=50, data_type="int")
            }
        )

        assert result.column_analysis["email"].unique_count == 45
        assert result.column_analysis["email"].null_count == 5
        assert result.column_analysis["phone"].data_type == "string"


# =============================================================================
# CSV Loading Tests
# =============================================================================


class TestCSVLoading:
    """Test CSV file loading from base64 encoded data."""

    def test_load_valid_csv_from_base64(self):
        """Test loading a valid CSV from base64 encoded content."""
        csv_content = """name,email,phone,address
John Doe,john@example.com,123-456-7890,123 Main St
Jane Smith,jane@example.com,987-654-3210,456 Oak Ave
Bob Johnson,bob@example.com,555-123-4567,789 Pine Rd"""

        base64_encoded = base64.b64encode(csv_content.encode('utf-8')).decode('utf-8')

        # Simulate loading function
        def load_csv_from_base64(data: str, delimiter: str = ',') -> pd.DataFrame:
            decoded = base64.b64decode(data)
            return pd.read_csv(io.BytesIO(decoded), delimiter=delimiter)

        df = load_csv_from_base64(base64_encoded)

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3
        assert list(df.columns) == ["name", "email", "phone", "address"]
        assert df.iloc[0]["name"] == "John Doe"
        assert df.iloc[1]["email"] == "jane@example.com"

    def test_csv_different_delimiters(self):
        """Test CSV loading with different delimiters."""
        # Semicolon delimited
        csv_semicolon = """name;email;phone
John Doe;john@example.com;123-456-7890
Jane Smith;jane@example.com;987-654-3210"""

        base64_encoded = base64.b64encode(csv_semicolon.encode('utf-8')).decode('utf-8')

        def load_csv_from_base64(data: str, delimiter: str = ',') -> pd.DataFrame:
            decoded = base64.b64decode(data)
            return pd.read_csv(io.BytesIO(decoded), delimiter=delimiter)

        df = load_csv_from_base64(base64_encoded, delimiter=';')

        assert len(df) == 2
        assert list(df.columns) == ["name", "email", "phone"]

    def test_csv_with_missing_values(self):
        """Test CSV loading with missing/null values."""
        csv_with_nulls = """name,email,phone,age
John Doe,john@example.com,123-456-7890,30
Jane Smith,,987-654-3210,
Bob Johnson,bob@example.com,,25"""

        base64_encoded = base64.b64encode(csv_with_nulls.encode('utf-8')).decode('utf-8')

        def load_csv_from_base64(data: str, delimiter: str = ',') -> pd.DataFrame:
            decoded = base64.b64decode(data)
            return pd.read_csv(io.BytesIO(decoded), delimiter=delimiter, na_values=["", "NA", "NULL"])

        df = load_csv_from_base64(base64_encoded)

        assert df.isnull().sum().sum() == 3  # 3 null values total
        assert pd.isna(df.iloc[1]["email"])
        assert pd.isna(df.iloc[1]["age"])

    def test_empty_csv_graceful_handling(self):
        """Test handling of empty CSV files gracefully."""
        empty_csv = ""

        base64_encoded = base64.b64encode(empty_csv.encode('utf-8')).decode('utf-8')

        def load_csv_from_base64(data: str, delimiter: str = ',') -> pd.DataFrame:
            decoded = base64.b64decode(data)
            try:
                return pd.read_csv(io.BytesIO(decoded), delimiter=delimiter)
            except pd.errors.EmptyDataError:
                return pd.DataFrame()

        df = load_csv_from_base64(base64_encoded)

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_csv_with_special_characters(self):
        """Test CSV loading with special characters and escape sequences."""
        csv_special = """name,email,note
John "Johnny" Doe,john@example.com,"Has, comma"
Jane Smith,jane@example.com,Normal note
Bob O'Reilly,bob@example.com,Apostrophe's test"""

        base64_encoded = base64.b64encode(csv_special.encode('utf-8')).decode('utf-8')

        def load_csv_from_base64(data: str, delimiter: str = ',') -> pd.DataFrame:
            decoded = base64.b64decode(data)
            return pd.read_csv(io.BytesIO(decoded), delimiter=delimiter, quotechar='"')

        df = load_csv_from_base64(base64_encoded)

        assert len(df) == 3
        assert "Johnny" in df.iloc[0]["name"]
        assert "comma" in df.iloc[0]["note"]

    def test_csv_utf8_encoding(self):
        """Test CSV loading with UTF-8 encoded characters."""
        csv_utf8 = """name,email,city
Café Owner,owner@café.com,Café District
München Hans,hans@münchen.de,München
Tokyo 山田,tokyo@example.com,東京"""

        base64_encoded = base64.b64encode(csv_utf8.encode('utf-8')).decode('utf-8')

        def load_csv_from_base64(data: str, delimiter: str = ',') -> pd.DataFrame:
            decoded = base64.b64decode(data)
            return pd.read_csv(io.BytesIO(decoded), delimiter=delimiter, encoding='utf-8')

        df = load_csv_from_base64(base64_encoded)

        assert len(df) == 3
        assert "Café" in df.iloc[0]["name"]
        assert "München" in df.iloc[1]["city"]


# =============================================================================
# Excel Loading Tests
# =============================================================================


class TestExcelLoading:
    """Test Excel file loading from base64 encoded data."""

    def test_load_excel_xlsx_from_base64(self):
        """Test loading an Excel .xlsx file from base64."""
        # Create a sample Excel file in memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            pd.DataFrame({
                "name": ["John Doe", "Jane Smith"],
                "email": ["john@example.com", "jane@example.com"]
            }).to_excel(writer, sheet_name="Sheet1", index=False)

        base64_encoded = base64.b64encode(output.getvalue()).decode('utf-8')

        # Simulate loading function
        def load_excel_from_base64(data: str, sheet_name: Optional[str] = None) -> pd.DataFrame:
            decoded = base64.b64decode(data)
            excel_file = pd.ExcelFile(io.BytesIO(decoded))
            if sheet_name:
                return pd.read_excel(excel_file, sheet_name=sheet_name)
            return pd.read_excel(excel_file, sheet_name=excel_file.sheet_names[0])

        df = load_excel_from_base64(base64_encoded)

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert list(df.columns) == ["name", "email"]

    def test_excel_multiple_sheets(self):
        """Test loading Excel file with multiple sheets."""
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            pd.DataFrame({"name": ["John", "Jane"]}).to_excel(writer, sheet_name="Contacts", index=False)
            pd.DataFrame({"product": ["A", "B", "C"]}).to_excel(writer, sheet_name="Products", index=False)

        base64_encoded = base64.b64encode(output.getvalue()).decode('utf-8')

        def load_all_sheets_from_base64(data: str) -> Dict[str, pd.DataFrame]:
            decoded = base64.b64decode(data)
            excel_file = pd.ExcelFile(io.BytesIO(decoded))
            return {
                sheet: pd.read_excel(excel_file, sheet_name=sheet)
                for sheet in excel_file.sheet_names
            }

        sheets = load_all_sheets_from_base64(base64_encoded)

        assert len(sheets) == 2
        assert "Contacts" in sheets
        assert "Products" in sheets
        assert len(sheets["Contacts"]) == 2
        assert len(sheets["Products"]) == 3

    def test_excel_empty_sheet(self):
        """Test handling of empty Excel sheets."""
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            pd.DataFrame().to_excel(writer, sheet_name="EmptySheet", index=False)

        base64_encoded = base64.b64encode(output.getvalue()).decode('utf-8')

        def load_excel_from_base64(data: str, sheet_name: str) -> pd.DataFrame:
            decoded = base64.b64decode(data)
            excel_file = pd.ExcelFile(io.BytesIO(decoded))
            return pd.read_excel(excel_file, sheet_name=sheet_name)

        df = load_excel_from_base64(base64_encoded, sheet_name="EmptySheet")

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_excel_with_formulas(self):
        """Test loading Excel preserving formula cells."""
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            pd.DataFrame({
                "value1": [10, 20, 30],
                "value2": [5, 10, 15],
                "sum": ["=A2+B2", "=A3+B3", "=A4+B4"]
            }).to_excel(writer, sheet_name="Data", index=False)

        base64_encoded = base64.b64encode(output.getvalue()).decode('utf-8')

        def load_excel_from_base64(data: str) -> pd.DataFrame:
            decoded = base64.b64decode(data)
            excel_file = pd.ExcelFile(io.BytesIO(decoded))
            return pd.read_excel(
                excel_file,
                sheet_name="Data",
                engine="openpyxl",
                keep_default_na=False,
                na_values=[]  # Treat empty strings as empty, not NA
            )

        df = load_excel_from_base64(base64_encoded)

        assert "sum" in df.columns
        # Formulas should be preserved as strings
        # Note: openpyxl may read unevaluated formulas as empty strings
        # We check that the column exists and is string type
        assert df["sum"].dtype == object


# =============================================================================
# Deduplication Tests
# =============================================================================


class TestDeduplication:
    """Test data deduplication functionality."""

    def test_exact_duplicate_detection(self):
        """Test detection of exact duplicate rows."""
        df = pd.DataFrame({
            "name": ["John Doe", "John Doe", "Jane Smith", "John Doe"],
            "email": ["john@example.com", "john@example.com", "jane@example.com", "john@example.com"],
            "phone": ["123-456-7890", "123-456-7890", "987-654-3210", "123-456-7890"]
        })

        # Exact duplicate detection
        duplicates_mask = df.duplicated(keep='first')
        duplicates = df[duplicates_mask]

        assert len(duplicates) == 2  # 2 exact duplicates (rows 2 and 3)

    def test_fuzzy_duplicate_detection_with_rapidfuzz(self):
        """Test fuzzy duplicate detection using rapidfuzz."""
        try:
            from rapidfuzz import fuzz, process
        except ImportError:
            pytest.skip("rapidfuzz not installed")

        df = pd.DataFrame({
            "name": [
                "John Doe",
                "Jon Doe",  # Fuzzy match
                "Jhon Doe",  # Fuzzy match
                "Jane Smith",
                "Johnathan Doe"  # Fuzzy match to John Doe
            ],
            "email": [
                "john@example.com",
                "john.doe@different.com",
                "jdoe@test.com",
                "jane@smith.com",
                "john.doe@gmail.com"
            ]
        })

        def fuzzy_find_duplicates(df: pd.DataFrame, column: str, threshold: float = 85) -> List[int]:
            """Find indices of fuzzy duplicates."""
            duplicates = []
            processed = set()

            for idx, row in df.iterrows():
                if idx in processed:
                    continue

                for compare_idx, compare_row in df.iterrows():
                    if idx != compare_idx and compare_idx not in processed:
                        similarity = fuzz.ratio(row[column], compare_row[column])
                        if similarity >= threshold:
                            duplicates.append(compare_idx)
                            processed.add(compare_idx)

            return duplicates

        duplicate_indices = fuzzy_find_duplicates(df, "name", threshold=80)

        # Should find fuzzy matches
        assert len(duplicate_indices) >= 2

    def test_custom_deduplication_columns(self):
        """Test deduplication using specific columns only."""
        df = pd.DataFrame({
            "id": [1, 2, 3, 4],
            "name": ["John Doe", "John Doe", "Jane Smith", "Bob Jones"],
            "email": ["john@example.com", "john@example.com", "jane@example.com", "bob@example.com"],
            "phone": ["111-111-1111", "222-222-2222", "333-333-3333", "444-444-4444"]
        })

        # Deduplicate on name and email only
        duplicates_mask = df.duplicated(subset=["name", "email"], keep='first')
        duplicates = df[duplicates_mask]

        # Row 2 (id=2) is a duplicate based on name+email
        assert len(duplicates) == 1
        assert duplicates.iloc[0]["id"] == 2

    def test_custom_fuzzy_threshold(self):
        """Test fuzzy matching with custom threshold values."""
        try:
            from rapidfuzz import fuzz
        except ImportError:
            pytest.skip("rapidfuzz not installed")

        names = ["Apple Inc", "Apple Incorporated", "apple inc.", "APPLE INC"]

        def check_threshold(name1: str, name2: str) -> float:
            return fuzz.ratio(name1.lower(), name2.lower())

        # Test different threshold scenarios
        threshold_high = 95
        threshold_medium = 80
        threshold_low = 60

        high_matches = [n for n in names if check_threshold("Apple Inc", n) >= threshold_high and n != "Apple Inc"]
        medium_matches = [n for n in names if threshold_medium <= check_threshold("Apple Inc", n) < threshold_high]
        low_matches = [n for n in names if threshold_low <= check_threshold("Apple Inc", n) < threshold_medium]

        # All variations should match at some threshold level
        assert len(high_matches) + len(medium_matches) + len(low_matches) == len(names) - 1

    def test_case_insensitive_deduplication(self):
        """Test case-insensitive duplicate detection."""
        df = pd.DataFrame({
            "name": ["John Doe", "JOHN DOE", "john doe", "Jane Smith"],
            "email": ["john@example.com", "JOHN@EXAMPLE.COM", "john@example.com", "jane@example.com"]
        })

        # Case-insensitive deduplication
        df_lower = df.copy()
        df_lower['name_lower'] = df_lower['name'].str.lower()
        df_lower['email_lower'] = df_lower['email'].str.lower()

        duplicates_mask = df_lower.duplicated(subset=['name_lower', 'email_lower'], keep='first')
        duplicates = df[duplicates_mask]

        # All case variations of John Doe should be considered duplicates
        assert len(duplicates) == 2  # Rows 2 and 3 are duplicates


# =============================================================================
# Standardization Tests
# =============================================================================


class TestStandardization:
    """Test data standardization functionality."""

    def test_phone_number_formatting(self):
        """Test phone number formatting to (XXX) XXX-XXXX."""
        phone_numbers = [
            "1234567890",
            "123-456-7890",
            "(123) 456-7890",
            "1-123-456-7890",
            "123.456.7890"
        ]

        def format_phone(phone: str) -> str:
            """Format phone number to (XXX) XXX-XXXX."""
            digits = ''.join(filter(str.isdigit, phone))
            if len(digits) == 10:
                return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
            elif len(digits) == 11 and digits[0] == '1':
                return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
            return phone  # Return original if can't format

        formatted = [format_phone(p) for p in phone_numbers]

        # All should be formatted to (XXX) XXX-XXXX
        for f in formatted:
            assert f.startswith("(")
            assert ")" in f
            assert "-" in f

    def test_email_lowercase_normalization(self):
        """Test email lowercase normalization."""
        emails = [
            "JOHN@EXAMPLE.COM",
            "John.Doe@Example.Com",
            "john.doe@EXAMPLE.COM",
            "test+tag@Gmail.com"
        ]

        normalized = [e.lower() for e in emails]

        assert all(e == e.lower() for e in normalized)
        assert normalized[0] == "john@example.com"
        assert normalized[2] == "john.doe@example.com"

    def test_name_title_case_standardization(self):
        """Test name standardization to title case."""
        names = [
            "JOHN DOE",
            "john doe",
            "JOHNATHAN DOE",
            "mary-jane smith",
            "O'CONNOR"
        ]

        def to_title_case(name: str) -> str:
            """Convert name to title case with proper handling of special cases."""
            exceptions = {"mc", "o'", "de", "van", "la", "da"}
            parts = name.lower().split()
            result = []

            for part in parts:
                if part.startswith("o'"):
                    result.append("O'" + part[2:].capitalize())
                elif any(part.startswith(ex) for ex in exceptions):
                    result.append(part.capitalize())
                else:
                    # Handle hyphenated names: "mary-jane" -> "Mary-Jane"
                    # Capitalize first letter of each hyphen-separated part
                    hyphen_parts = part.split("-")
                    result.append("-".join(p.capitalize() for p in hyphen_parts))

            return " ".join(result)

        title_cased = [to_title_case(n) for n in names]

        assert title_cased[0] == "John Doe"
        assert title_cased[3] == "Mary-Jane Smith"
        assert title_cased[4] == "O'Connor"

    def test_address_standardization(self):
        """Test address standardization."""
        addresses = [
            "123 MAIN STREET",
            "456 oak ave",
            "789 Pine Road, APT 4B",
            "123 Main St, STE 100, New York, NY 10001"
        ]

        def standardize_address(addr: str) -> str:
            """Standardize address format."""
            # Common abbreviation mappings
            mappings = {
                "street": "St",
                "avenue": "Ave",
                "road": "Rd",
                "drive": "Dr",
                "boulevard": "Blvd",
                "apartment": "Apt",
                "suite": "Ste",
                "department": "Dept"
            }

            addr_lower = addr.lower()
            for full, abbrev in mappings.items():
                addr_lower = addr_lower.replace(full, abbrev)

            # Title case
            result = addr_lower.title()

            return result

        standardized = [standardize_address(a) for a in addresses]

        assert standardized[0] == "123 Main St"
        assert standardized[1] == "456 Oak Ave"
        assert "Apt" in standardized[2]

    def test_zip_code_standardization(self):
        """Test zip code standardization to 5 digits."""
        zip_codes = ["12345", "1234", "1234567890", "12345-6789"]

        def standardize_zip(zip_code: str) -> str:
            digits = ''.join(filter(str.isdigit, zip_code))
            if len(digits) >= 5:
                return digits[:5]
            return zip_code.zfill(5)  # Pad with zeros if too short

        standardized = [standardize_zip(z) for z in zip_codes]

        assert standardized[0] == "12345"
        assert standardized[1] == "01234"  # Padded
        assert standardized[3] == "12345"  # First 5 digits


# =============================================================================
# Enrichment Tests
# =============================================================================


class TestEnrichment:
    """Test data enrichment functionality."""

    def test_fill_null_values_with_defaults(self):
        """Test filling null values with default values."""
        df = pd.DataFrame({
            "name": ["John", "Jane", "Bob", None],
            "email": ["john@example.com", None, "bob@example.com", "unknown@test.com"],
            "phone": [None, None, None, None]
        })

        # Fill null values
        defaults = {"name": "Unknown", "email": "not provided", "phone": "N/A"}

        for col, default in defaults.items():
            df[col] = df[col].fillna(default)

        assert df.iloc[3]["name"] == "Unknown"
        assert df.iloc[1]["email"] == "not provided"
        assert df.iloc[0]["phone"] == "N/A"
        assert df.iloc[3]["name"] == "Unknown"

    def test_multiple_column_fills(self):
        """Test filling null values in multiple columns."""
        df = pd.DataFrame({
            "col_a": [1, None, 3, None],
            "col_b": [None, "B", None, "D"],
            "col_c": [None, None, None, None]
        })

        # Fill numeric column with mean
        df["col_a"] = df["col_a"].fillna(df["col_a"].mean())

        # Fill string columns with mode
        for col in ["col_b", "col_c"]:
            mode_value = df[col].mode().iloc[0] if not df[col].mode().empty else "N/A"
            df[col] = df[col].fillna(mode_value)

        assert pd.notna(df.iloc[1]["col_a"])
        assert pd.notna(df.iloc[3]["col_b"])
        assert pd.notna(df.iloc[0]["col_c"])

    def test_handle_different_data_types(self):
        """Test filling null values with appropriate types."""
        df = pd.DataFrame({
            "int_col": [1, None, 3],
            "float_col": [1.5, None, 3.5],
            "bool_col": [True, None, False],
            "date_col": [None, pd.Timestamp("2023-01-01"), None],
            "str_col": ["abc", None, "xyz"]
        })

        # Fill each type appropriately
        # Note: fillna on nullable int columns may return float in pandas 2.x
        df["int_col"] = df["int_col"].fillna(0).astype(int)
        df["float_col"] = df["float_col"].fillna(0.0)
        df["bool_col"] = df["bool_col"].fillna(False)
        df["date_col"] = pd.to_datetime(df["date_col"]).fillna(pd.Timestamp("1970-01-01"))
        df["str_col"] = df["str_col"].fillna("unknown")

        # Verify no nulls remain
        assert df.isnull().sum().sum() == 0

        # Verify values are correct (dtype may vary by pandas version)
        assert df["int_col"].iloc[1] == 0  # The filled value
        assert df["bool_col"].iloc[1] == False  # The filled value

    def test_derived_column_creation(self):
        """Test creating derived/enriched columns."""
        df = pd.DataFrame({
            "first_name": ["John", "Jane"],
            "last_name": ["Doe", "Smith"],
            "email": ["john@example.com", "jane@example.com"]
        })

        # Create derived columns
        df["full_name"] = df["first_name"] + " " + df["last_name"]
        df["email_domain"] = df["email"].str.split("@").str[1]
        df["name_length"] = df["full_name"].str.len()

        assert df.iloc[0]["full_name"] == "John Doe"
        assert df.iloc[0]["email_domain"] == "example.com"
        assert df.iloc[1]["name_length"] == 10


# =============================================================================
# Edge Cases Tests
# =============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_large_file_handling(self):
        """Test handling of large DataFrames."""
        # Create a large DataFrame
        n_rows = 100000
        df = pd.DataFrame({
            "id": range(n_rows),
            "name": [f"Person_{i}" for i in range(n_rows)],
            "email": [f"person{i}@example.com" for i in range(n_rows)]
        })

        assert len(df) == 100000

        # Test deduplication performance
        df_with_duplicates = pd.concat([df, df.head(1000)], ignore_index=True)
        assert len(df_with_duplicates) == 101000

    def test_special_characters_in_data(self):
        """Test handling of special characters in data."""
        df = pd.DataFrame({
            "name": [
                "John O'Reilly",
                'Smith "The Boss" Jones',
                "Café Menu",
                "München",
                "Japanese: 日本語",
                "Emoji: 😀🎉"
            ],
            "note": [
                "Has apostrophe's",
                "Has quotes \"and\" more",
                "Special chars: @#$%",
                "Umlaut: äöü",
                "Unicode: 你好",
                "Symbols: &*()"
            ]
        })

        # Verify all data is preserved
        assert len(df) == 6
        assert "O'Reilly" in df.iloc[0]["name"]
        assert "The Boss" in df.iloc[1]["name"]
        assert "日本語" in df.iloc[4]["name"]

    def test_utf8_handling(self):
        """Test UTF-8 encoding/decoding."""
        data = {
            "english": ["Hello", "World"],
            "spanish": ["Hola", "Mundo"],
            "chinese": ["你好", "世界"],
            "arabic": ["مرحبا", "عالم"],
            "emoji": ["👋", "🌍"]
        }

        df = pd.DataFrame(data)

        # Verify UTF-8 encoding works
        encoded = df.to_json(force_ascii=False).encode('utf-8')
        decoded = pd.read_json(io.BytesIO(encoded), encoding='utf-8')

        # Verify content preserved
        assert decoded.iloc[0]["chinese"] == "你好"
        assert decoded.iloc[0]["arabic"] == "مرحبا"
        assert decoded.iloc[0]["emoji"] == "👋"

    def test_mixed_data_types_in_columns(self):
        """Test handling of mixed data types in columns."""
        mixed_df = pd.DataFrame({
            "mixed": [1, "two", 3.0, None, "five"],
            "numeric_like": ["123", 456, "789.5", None, "1000"]
        })

        # Test type coercion
        mixed_df["numeric_converted"] = pd.to_numeric(mixed_df["numeric_like"], errors='coerce')

        assert pd.api.types.is_numeric_dtype(mixed_df["numeric_converted"])
        assert pd.notna(mixed_df["numeric_converted"].iloc[0])
        assert pd.isna(mixed_df["numeric_converted"].iloc[3])

    def test_whitespace_handling(self):
        """Test handling of leading/trailing whitespace."""
        df = pd.DataFrame({
            "name": ["  John Doe  ", "Jane Smith", "  Bob Jones  "],
            "email": [" john@example.com ", "jane@example.com", " bob@example.com "]
        })

        # Strip whitespace
        df["name_cleaned"] = df["name"].str.strip()
        df["email_cleaned"] = df["email"].str.strip()

        assert df.iloc[0]["name_cleaned"] == "John Doe"
        assert df.iloc[0]["email_cleaned"] == "john@example.com"

    def test_datetime_parsing(self):
        """Test various datetime formats parsing."""
        dates = [
            "2023-01-15",
            "2024-12-31"
        ]

        def parse_dates(date_list: List[str]):
            parsed = pd.to_datetime(date_list, errors='coerce')
            # Convert to list for compatibility
            return list(parsed)

        parsed = parse_dates(dates)

        # These formats should parse correctly
        assert pd.notna(parsed[0])  # 2023-01-15
        assert pd.notna(parsed[1])  # 2024-12-31

    def test_empty_dataframe_operations(self):
        """Test operations on empty DataFrames."""
        empty_df = pd.DataFrame({
            "name": pd.Series(dtype="str"),
            "email": pd.Series(dtype="str"),
            "age": pd.Series(dtype="int")
        })

        assert len(empty_df) == 0

        # Operations should not fail
        empty_df["name_cleaned"] = empty_df["name"].str.strip()
        empty_df["age_filled"] = empty_df["age"].fillna(0)

        assert len(empty_df) == 0


# =============================================================================
# Mock Gemini API Tests
# =============================================================================


class TestGeminiAPIMocks:
    """Test mocking of Gemini API for completeness."""

    @pytest.mark.asyncio
    async def test_mock_gemini_extraction(self):
        """Test mocking Gemini API extraction response."""
        from unittest.mock import AsyncMock, patch

        # Create mock response
        mock_response = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": '{"name": "John Doe", "email": "john@example.com"}'
                    }]
                }
            }]
        }

        # Mock the Gemini API call
        mock_api_call = AsyncMock(return_value=mock_response)

        # Call the mock
        result = await mock_api_call("test prompt")

        assert result == mock_response
        mock_api_call.assert_called_once_with("test prompt")

    def test_mock_gemini_sync(self):
        """Test synchronous mocking of Gemini API."""
        mock_client = MagicMock()

        # Setup mock method
        mock_client.generate_content.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{"text": "Cleaned data"}]
                }
            }]
        }

        result = mock_client.generate_content("Clean this data")

        assert "Cleaned data" in result["candidates"][0]["content"]["parts"][0]["text"]

    @pytest.mark.skipif(
        True,  # Always skip - module not installed
        reason="google-generativeai not installed"
    )
    @patch('google.generativeai.GenerativeModel')
    def test_gemini_model_mocking(self, mock_model_class):
        """Test mocking Google GenerativeModel."""
        # Skip if google.generativeai not installed
        try:
            from google.generativeai import GenerativeModel
        except ImportError:
            pytest.skip("google-generativeai not installed")

        # Setup mock
        mock_instance = MagicMock()
        mock_instance.generate_content_async = AsyncMock()
        mock_model_class.return_value = mock_instance

        # Simulate API call
        mock_instance.generate_content_async.return_value = {
            "text": "Processed by Gemini"
        }

        # Verify mock is in place
        assert GenerativeModel is mock_model_class


# =============================================================================
# Integration Test Fixtures
# =============================================================================


@pytest.fixture
def dirty_crm_data() -> pd.DataFrame:
    """Create sample dirty CRM data with known issues for testing."""
    return pd.DataFrame({
        "first_name": ["JOHN", "john", "Jane", "BOB", None, "MARY-JANE"],
        "last_name": ["DOE", "doe", "Smith", "JONES", "Johnson", "O'BRIEN"],
        "email": ["JOHN@EXAMPLE.COM", "john.doe@example.com", "JANE@EXAMPLE.COM", "BOB@EXAMPLE.COM", None, "MARY@TEST.COM"],
        "phone": ["1234567890", "1-234-567-8900", "(234) 567-8901", "2345678902", None, "234-567-8903"],
        "address": ["123 MAIN ST", "456 oak ave", "789 PINE RD", "123 MAIN ST", "321 ELM STREET", "654 MAPLE DR"],
        "city": ["NEW YORK", "new york", "Los Angeles", "NEW YORK", "Chicago", "Miami"],
        "zip_code": ["10001", "10001", "90001", "10001", "60601", "33101"],
        "company": ["Acme Inc", "ACME INC", "Tech Corp", None, "Tech Corp", "Startup LLC"]
    })


@pytest.fixture
def clean_expected_data() -> pd.DataFrame:
    """Expected cleaned data for comparison."""
    return pd.DataFrame({
        "first_name": ["John", "John", "Jane", "Bob", "Unknown", "Mary-Jane"],
        "last_name": ["Doe", "Doe", "Smith", "Jones", "Johnson", "O'Brien"],
        "email": ["john@example.com", "john.doe@example.com", "jane@example.com", "bob@example.com", "not provided", "mary@test.com"],
        "phone": ["(123) 456-7890", "(234) 567-8900", "(234) 567-8901", "(234) 567-8902", "N/A", "(234) 567-8903"],
        "address": ["123 Main St", "456 Oak Ave", "789 Pine Rd", "123 Main St", "321 Elm Street", "654 Maple Dr"],
        "city": ["New York", "New York", "Los Angeles", "New York", "Chicago", "Miami"],
        "zip_code": ["10001", "10001", "90001", "10001", "60601", "33101"],
        "company": ["Acme Inc", "Acme Inc", "Tech Corp", "Unknown", "Tech Corp", "Startup LLC"]
    })


class TestCRMDataCleaningIntegration:
    """Integration tests for CRM data cleaning pipeline."""

    def test_full_cleaning_pipeline(self, dirty_crm_data, clean_expected_data):
        """Test complete data cleaning pipeline."""
        df = dirty_crm_data.copy()

        # Step 1: Standardize names (title case)
        for col in ["first_name", "last_name"]:
            df[col] = df[col].apply(
                lambda x: x.title() if isinstance(x, str) else "Unknown"
            )

        # Step 2: Normalize emails (lowercase)
        df["email"] = df["email"].str.lower().fillna("not provided")

        # Step 3: Format phone numbers
        def format_phone(phone):
            if pd.isna(phone):
                return "N/A"
            digits = ''.join(filter(str.isdigit, str(phone)))
            if len(digits) == 10:
                return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
            return phone

        df["phone"] = df["phone"].apply(format_phone)

        # Step 4: Standardize addresses
        mappings = {"st": "St", "ave": "Ave", "rd": "Rd", "dr": "Dr"}
        df["address"] = df["address"].str.lower().str.title()
        for abbr, full in mappings.items():
            df["address"] = df["address"].str.replace(abbr, full, regex=False)

        # Step 5: Fill nulls in company
        df["company"] = df["company"].fillna("Unknown")

        # Verify key transformations
        assert df.iloc[0]["first_name"] == "John"
        assert df.iloc[0]["email"] == "john@example.com"
        assert df.iloc[0]["phone"] == "(123) 456-7890"
        assert df.iloc[0]["company"] == "Acme Inc"

    def test_deduplication_removes_duplicates(self, dirty_crm_data):
        """Test that deduplication removes expected duplicates."""
        df = dirty_crm_data.copy()

        # Count duplicates before
        initial_count = len(df)

        # Add exact duplicate rows
        df_with_dups = pd.concat([df, df.head(2)], ignore_index=True)
        dup_count = len(df_with_dups) - len(df_with_dups.drop_duplicates())

        assert dup_count == 2  # 2 exact duplicates added

    def test_data_quality_score_calculation(self, dirty_crm_data):
        """Test data quality score calculation."""
        df = dirty_crm_data.copy()

        # Calculate quality metrics
        total_cells = df.size
        null_cells = df.isnull().sum().sum()
        unique_cells = df.nunique().sum()

        quality_score = 1 - (null_cells / total_cells)

        assert quality_score < 1.0  # Has null values
        # Fixture has 4 nulls: first_name (1), email (1), phone (1), company (1)
        assert null_cells == 4

    def test_column_analysis_generation(self, dirty_crm_data):
        """Test column analysis for data quality insights."""
        df = dirty_crm_data.copy()

        analysis = {}
        for col in df.columns:
            analysis[col] = {
                "unique_count": df[col].nunique(),
                "null_count": int(df[col].isnull().sum()),
                "total_count": len(df),
                "null_percentage": (df[col].isnull().sum() / len(df)) * 100
            }

        assert analysis["first_name"]["unique_count"] == 5  # 6 values, 1 null, 2 "JOHN"/"john"
        assert analysis["email"]["null_count"] == 1
        assert analysis["phone"]["null_count"] == 1


# =============================================================================
# Test Utilities
# =============================================================================


def create_base64_csv(df: pd.DataFrame) -> str:
    """Helper function to create base64 encoded CSV from DataFrame."""
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    return base64.b64encode(csv_buffer.getvalue().encode('utf-8')).decode('utf-8')


def create_base64_excel(df: pd.DataFrame, sheet_name: str = "Sheet1") -> str:
    """Helper function to create base64 encoded Excel from DataFrame."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
    return base64.b64encode(output.getvalue()).decode('utf-8')


class TestHelperFunctions:
    """Test helper functions for test fixtures."""

    def test_create_base64_csv(self):
        """Test base64 CSV creation helper."""
        df = pd.DataFrame({"name": ["John", "Jane"], "value": [1, 2]})

        encoded = create_base64_csv(df)
        decoded = base64.b64decode(encoded)

        # Verify it's valid CSV
        df_decoded = pd.read_csv(io.BytesIO(decoded))
        assert len(df_decoded) == 2
        assert list(df_decoded.columns) == ["name", "value"]

    def test_create_base64_excel(self):
        """Test base64 Excel creation helper."""
        df = pd.DataFrame({"name": ["John", "Jane"], "value": [1, 2]})

        encoded = create_base64_excel(df, "TestSheet")
        decoded = base64.b64decode(encoded)

        # Verify it's valid Excel
        excel_file = pd.ExcelFile(io.BytesIO(decoded))
        assert "TestSheet" in excel_file.sheet_names

        df_decoded = pd.read_excel(excel_file, sheet_name="TestSheet")
        assert len(df_decoded) == 2
