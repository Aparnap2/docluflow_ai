"""Validation module for extracted data with self-healing capabilities."""

import json
from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field, ValidationError
import re
import structlog

logger = structlog.get_logger(__name__)

class ValidationResult(BaseModel):
    """Result of data validation."""
    is_valid: bool = Field(description="Whether the data is valid")
    errors: List[str] = Field(default_factory=list, description="Validation errors")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")
    suggestions: List[str] = Field(default_factory=list, description="Improvement suggestions")
    corrected_data: Optional[Dict[str, Any]] = Field(None, description="Corrected data if applicable")

class DataValidator:
    """Self-healing data validator with comprehensive validation rules."""
    
    def __init__(self):
        self.validation_rules = {
            'email': self._validate_email,
            'phone': self._validate_phone,
            'url': self._validate_url,
            'date': self._validate_date,
            'currency': self._validate_currency,
            'number': self._correct_number,
            'percentage': self._validate_percentage,
        }

    def validate_extraction(self, data: Dict[str, Any], target_schema: Dict[str, Any]) -> ValidationResult:
        """
        Validate extracted data against target schema with self-healing.
        
        Args:
            data: Extracted data to validate
            target_schema: Target schema for validation
            
        Returns:
            ValidationResult with validation status and corrections
        """
        logger.info("Starting data validation", 
                   data_keys=list(data.keys()),
                   schema_keys=list(target_schema.keys()))
        
        errors = []
        warnings = []
        suggestions = []
        corrected_data = data.copy()
        
        try:
            # Schema structure validation
            structure_result = self._validate_schema_structure(data, target_schema)
            errors.extend(structure_result['errors'])
            warnings.extend(structure_result['warnings'])
            
            # Type validation and correction
            type_result = self._validate_types(corrected_data, target_schema)
            errors.extend(type_result['errors'])
            warnings.extend(type_result['warnings'])
            corrected_data.update(type_result.get('corrections', {}))
            
            # Content validation
            content_result = self._validate_content(corrected_data, target_schema)
            errors.extend(content_result['errors'])
            warnings.extend(content_result['warnings'])
            corrected_data.update(content_result.get('corrections', {}))
            
            # Business logic validation
            business_result = self._validate_business_rules(corrected_data, target_schema)
            errors.extend(business_result['errors'])
            warnings.extend(business_result['warnings'])
            suggestions.extend(business_result.get('suggestions', []))
            
            # Generate improvement suggestions
            suggestion_result = self._generate_suggestions(corrected_data, target_schema)
            suggestions.extend(suggestion_result)
            
            is_valid = len(errors) == 0
            
            logger.info("Validation completed", 
                       is_valid=is_valid,
                       error_count=len(errors),
                       warning_count=len(warnings),
                       suggestion_count=len(suggestions))
            
            return ValidationResult(
                is_valid=is_valid,
                errors=errors,
                warnings=warnings,
                suggestions=suggestions,
                corrected_data=corrected_data if corrected_data != data else None
            )
            
        except Exception as e:
            logger.error("Validation failed with exception", error=str(e))
            return ValidationResult(
                is_valid=False,
                errors=[f"Validation error: {str(e)}"],
                warnings=warnings,
                suggestions=[],
                corrected_data=None
            )

    def _validate_schema_structure(self, data: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, List[str]]:
        """Validate basic schema structure."""
        errors = []
        warnings = []
        
        # Check for missing required fields
        for field_name in schema.keys():
            if field_name not in data:
                errors.append(f"Missing required field: {field_name}")
        
        # Check for extra fields
        for field_name in data.keys():
            if field_name not in schema:
                warnings.append(f"Unexpected field: {field_name}")
        
        return {'errors': errors, 'warnings': warnings}

    def _validate_types(self, data: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and correct data types."""
        errors = []
        warnings = []
        corrections = {}
        
        for field_name, field_spec in schema.items():
            if field_name not in data:
                continue
                
            field_value = data[field_name]
            expected_type = field_spec if isinstance(field_spec, str) else field_spec.get('type', 'string')
            
            # Skip validation for None values
            if field_value is None:
                continue
            
            try:
                if expected_type == 'number':
                    corrected_value = self._correct_number(field_value)
                    if corrected_value != field_value:
                        corrections[field_name] = corrected_value
                        warnings.append(f"Field {field_name}: corrected number format")
                        
                elif expected_type == 'string':
                    # Ensure string type
                    if not isinstance(field_value, str):
                        corrections[field_name] = str(field_value)
                        warnings.append(f"Field {field_name}: converted to string")
                        
                elif expected_type == 'boolean':
                    corrected_value = self._correct_boolean(field_value)
                    if corrected_value != field_value:
                        corrections[field_name] = corrected_value
                        warnings.append(f"Field {field_name}: corrected boolean value")
                        
                elif expected_type == 'array':
                    if not isinstance(field_value, list):
                        corrections[field_name] = [field_value] if field_value else []
                        warnings.append(f"Field {field_name}: converted to array")
                        
                elif expected_type == 'object':
                    if not isinstance(field_value, dict):
                        errors.append(f"Field {field_name} should be an object")
                        
            except Exception as e:
                errors.append(f"Field {field_name}: type correction failed - {str(e)}")
        
        return {'errors': errors, 'warnings': warnings, 'corrections': corrections}

    def _validate_content(self, data: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
        """Validate content quality and format."""
        errors = []
        warnings = []
        corrections = {}
        
        for field_name, field_value in data.items():
            if field_value is None:
                continue
                
            field_spec = schema.get(field_name, {})
            if isinstance(field_spec, dict):
                format_type = field_spec.get('format')
                
                if format_type == 'email':
                    if not self._validate_email(str(field_value)):
                        errors.append(f"Field {field_name}: invalid email format")
                        
                elif format_type == 'phone':
                    if not self._validate_phone(str(field_value)):
                        warnings.append(f"Field {field_name}: suspicious phone number format")
                        
                elif format_type == 'url':
                    if not self._validate_url(str(field_value)):
                        errors.append(f"Field {field_name}: invalid URL format")
                        
                elif format_type == 'date':
                    if not self._validate_date(str(field_value)):
                        warnings.append(f"Field {field_name}: suspicious date format")
                        
                elif format_type == 'currency':
                    corrected_value = self._validate_currency(str(field_value))
                    if corrected_value != field_value:
                        corrections[field_name] = corrected_value
                        warnings.append(f"Field {field_name}: corrected currency format")
                        
                elif format_type == 'percentage':
                    corrected_value = self._validate_percentage(str(field_value))
                    if corrected_value != field_value:
                        corrections[field_name] = corrected_value
                        warnings.append(f"Field {field_name}: corrected percentage format")
        
        return {'errors': errors, 'warnings': warnings, 'corrections': corrections}

    def _validate_business_rules(self, data: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
        """Validate business logic rules."""
        errors = []
        warnings = []
        suggestions = []
        
        # Example business rules (customize based on your needs)
        
        # Date consistency checks
        if 'start_date' in data and 'end_date' in data:
            if data['start_date'] and data['end_date']:
                if data['start_date'] > data['end_date']:
                    errors.append("Start date cannot be after end date")
        
        # Numeric range checks
        for field_name, field_value in data.items():
            if isinstance(field_value, (int, float)):
                field_spec = schema.get(field_name, {})
                if isinstance(field_spec, dict):
                    if 'minimum' in field_spec and field_value < field_spec['minimum']:
                        warnings.append(f"Field {field_name} below minimum value {field_spec['minimum']}")
                    if 'maximum' in field_spec and field_value > field_spec['maximum']:
                        warnings.append(f"Field {field_name} above maximum value {field_spec['maximum']}")
        
        # String length checks
        for field_name, field_value in data.items():
            if isinstance(field_value, str):
                field_spec = schema.get(field_name, {})
                if isinstance(field_spec, dict):
                    if 'minLength' in field_spec and len(field_value) < field_spec['minLength']:
                        warnings.append(f"Field {field_name} shorter than minimum length {field_spec['minLength']}")
                    if 'maxLength' in field_spec and len(field_value) > field_spec['maxLength']:
                        warnings.append(f"Field {field_name} longer than maximum length {field_spec['maxLength']}")
        
        return {'errors': errors, 'warnings': warnings, 'suggestions': suggestions}

    def _generate_suggestions(self, data: Dict[str, Any], schema: Dict[str, Any]) -> List[str]:
        """Generate improvement suggestions."""
        suggestions = []
        
        # Suggest missing fields that could be extracted
        for field_name, field_spec in schema.items():
            if field_name not in data or data[field_name] is None:
                suggestions.append(f"Consider extracting {field_name} for more complete data")
        
        # Suggest data enrichment opportunities
        if 'email' in data and 'phone' not in data:
            suggestions.append("Consider extracting phone number for better contact information")
        
        if 'total' in data and 'tax' not in data:
            suggestions.append("Consider extracting tax information for financial completeness")
        
        return suggestions

    # Helper methods for specific validations
    def _validate_email(self, email: str) -> bool:
        """Validate email format."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None

    def _validate_phone(self, phone: str) -> bool:
        """Validate phone number format."""
        # Remove common formatting characters
        cleaned = re.sub(r'[\s\-\(\)\+\.]', '', phone)
        # Check if it contains only digits and is reasonable length
        return cleaned.isdigit() and 7 <= len(cleaned) <= 15

    def _validate_url(self, url: str) -> bool:
        """Validate URL format."""
        pattern = r'^https?://[^\s/$.?#].[^\s]*$'
        return re.match(pattern, url) is not None

    def _validate_date(self, date_str: str) -> bool:
        """Validate date format."""
        # Common date patterns
        patterns = [
            r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
            r'\d{2}/\d{2}/\d{4}',  # MM/DD/YYYY
            r'\d{2}-\d{2}-\d{4}',  # MM-DD-YYYY
        ]
        return any(re.match(pattern, date_str) for pattern in patterns)

    def _validate_currency(self, currency_str: str) -> str:
        """Validate and correct currency format."""
        # Remove common currency symbols and spaces
        cleaned = re.sub(r'[\s,$£€¥]', '', currency_str)
        try:
            # Try to parse as float
            float_value = float(cleaned)
            return f"{float_value:.2f}"
        except ValueError:
            return currency_str

    def _validate_percentage(self, percentage_str: str) -> str:
        """Validate and correct percentage format."""
        # Remove percentage sign
        cleaned = percentage_str.replace('%', '').strip()
        try:
            float_value = float(cleaned)
            return f"{float_value}%"
        except ValueError:
            return percentage_str

    def _correct_number(self, value: Any) -> Union[int, float]:
        """Correct number format."""
        if isinstance(value, (int, float)):
            return value
        
        # Try to extract number from string
        if isinstance(value, str):
            # Remove common formatting
            cleaned = re.sub(r'[\s,]', '', value)
            try:
                if '.' in cleaned:
                    return float(cleaned)
                else:
                    return int(cleaned)
            except ValueError:
                return 0
        
        return 0

    def _correct_boolean(self, value: Any) -> bool:
        """Correct boolean value."""
        if isinstance(value, bool):
            return value
        
        if isinstance(value, str):
            lower_value = value.lower().strip()
            if lower_value in ['true', 'yes', '1', 'on']:
                return True
            elif lower_value in ['false', 'no', '0', 'off']:
                return False
        
        return bool(value)

# Global validator instance
_validator = None

def validate_extraction(data: Dict[str, Any], target_schema: Dict[str, Any]) -> ValidationResult:
    """
    Validate extracted data against target schema with self-healing.
    
    Args:
        data: Extracted data to validate
        target_schema: Target schema for validation
        
    Returns:
        ValidationResult with validation status and corrections
    """
    global _validator
    
    if _validator is None:
        _validator = DataValidator()
    
    return _validator.validate_extraction(data, target_schema)