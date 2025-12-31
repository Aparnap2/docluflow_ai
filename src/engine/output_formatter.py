"""Output formatter for DocuFlow Headless v2 - Generates n8n-compatible output with Google Drive routing metadata."""

from typing import Dict, Any, Optional, List
from datetime import datetime
import re
import structlog
from pathlib import Path

logger = structlog.get_logger(__name__)

class OutputFormatter:
    """Formats extraction output for n8n integration and Google Drive routing."""
    
    def __init__(self):
        self.date_patterns = [
            r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
            r'\d{2}/\d{2}/\d{4}',  # MM/DD/YYYY
            r'\d{2}-\d{2}-\d{4}',  # MM-DD-YYYY
            r'\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}',  # DD Mon YYYY
        ]
        
        self.vendor_patterns = [
            r'(?:Invoice|Receipt|Bill)\s+(?:from|by)\s+([A-Za-z\s&]+)',
            r'([A-Za-z\s&]+)\s+(?:Inc|LLC|Corp|Ltd|GmbH)',
            r'Vendor:\s*([A-Za-z\s&]+)',
            r'Company:\s*([A-Za-z\s&]+)',
            r'From:\s*([A-Za-z\s&]+)',
        ]
    
    def format_n8n_output(
        self,
        extracted_data: Dict[str, Any],
        original_filename: Optional[str] = None,
        processing_method: str = "unknown",
        confidence: float = 0.0,
        filter_keywords_found: List[str] = None
    ) -> Dict[str, Any]:
        """
        Format output for n8n integration with Google Drive routing metadata.
        
        Args:
            extracted_data: Raw extracted data
            original_filename: Original filename
            processing_method: cpu_fast or gpu_vision
            confidence: Extraction confidence score
            filter_keywords_found: Keywords that were found during filtering
            
        Returns:
            n8n-compatible formatted output
        """
        logger.info("Formatting n8n output", 
                   original_filename=original_filename,
                   processing_method=processing_method,
                   confidence=confidence)
        
        # Extract metadata for routing
        metadata = self._extract_routing_metadata(extracted_data, original_filename)
        
        # Generate suggested filename
        suggested_filename = self._generate_suggested_filename(
            extracted_data, original_filename, metadata
        )
        
        # Generate routing folder path
        routing_folder = self._generate_routing_folder(metadata)
        
        # Create n8n-compatible output
        n8n_output = {
            # Main extracted data
            "data": extracted_data,
            
            # Metadata for routing
            "_meta": {
                "processed_by": processing_method,
                "confidence": confidence,
                "processed_at": datetime.now().isoformat(),
                "suggested_filename": suggested_filename,
                "routing_folder": routing_folder,
                "original_filename": original_filename,
                "filter_keywords_found": filter_keywords_found or [],
                "metadata": metadata
            },
            
            # Google Drive specific fields
            "google_drive": {
                "filename": suggested_filename,
                "folder_path": routing_folder,
                "mime_type": self._detect_mime_type(suggested_filename),
                "description": f"Extracted by DocuFlow v2 ({processing_method}, confidence: {confidence:.2f})"
            },
            
            # n8n specific fields
            "n8n": {
                "binary_data": None,  # Can be populated with file bytes if needed
                "file_name": suggested_filename,
                "file_path": f"{routing_folder}/{suggested_filename}" if routing_folder else suggested_filename,
                "mime_type": self._detect_mime_type(suggested_filename),
                "metadata": {
                    "confidence": confidence,
                    "processing_method": processing_method,
                    "extracted_fields": list(extracted_data.keys())
                }
            }
        }
        
        logger.info("n8n output formatted successfully",
                   suggested_filename=suggested_filename,
                   routing_folder=routing_folder,
                   field_count=len(extracted_data))
        
        return n8n_output
    
    def _extract_routing_metadata(self, data: Dict[str, Any], original_filename: Optional[str]) -> Dict[str, Any]:
        """Extract metadata for routing decisions."""
        metadata = {
            "date": None,
            "year": None,
            "month": None,
            "vendor": None,
            "total": None,
            "type": None
        }
        
        # Extract date
        date_value = self._find_date_in_data(data)
        if date_value:
            metadata["date"] = date_value
            try:
                if isinstance(date_value, str):
                    # Try to parse date string
                    if len(date_value) >= 10 and date_value[4] == '-' and date_value[7] == '-':
                        # ISO format YYYY-MM-DD
                        metadata["year"] = int(date_value[:4])
                        metadata["month"] = int(date_value[5:7])
                    elif '/' in date_value:
                        # MM/DD/YYYY format
                        parts = date_value.split('/')
                        if len(parts) == 3:
                            metadata["month"] = int(parts[0])
                            metadata["year"] = int(parts[2])
            except (ValueError, IndexError):
                pass
        
        # Extract vendor/company name
        vendor_value = self._find_vendor_in_data(data)
        if vendor_value:
            metadata["vendor"] = self._clean_vendor_name(vendor_value)
        
        # Extract total amount
        total_value = self._find_total_in_data(data)
        if total_value:
            metadata["total"] = total_value
        
        # Determine document type
        metadata["type"] = self._determine_document_type(data, original_filename)
        
        # Fallback to current date if no date found
        if not metadata["date"]:
            now = datetime.now()
            metadata["date"] = now.isoformat()
            metadata["year"] = now.year
            metadata["month"] = now.month
        
        return metadata
    
    def _find_date_in_data(self, data: Dict[str, Any]) -> Optional[str]:
        """Find date in extracted data."""
        # Check common date field names
        date_fields = ['date', 'invoice_date', 'receipt_date', 'created_date', 'issue_date', 'due_date']
        
        for field in date_fields:
            if field in data and data[field]:
                value = str(data[field]).strip()
                # Validate date format
                for pattern in self.date_patterns:
                    if re.search(pattern, value):
                        return value
        
        # Search in all string values
        for key, value in data.items():
            if isinstance(value, str):
                for pattern in self.date_patterns:
                    match = re.search(pattern, value)
                    if match:
                        return match.group()
        
        return None
    
    def _find_vendor_in_data(self, data: Dict[str, Any]) -> Optional[str]:
        """Find vendor/company name in extracted data."""
        # Check common vendor field names
        vendor_fields = ['vendor', 'company', 'seller', 'merchant', 'supplier', 'from', 'issuer']
        
        for field in vendor_fields:
            if field in data and data[field]:
                value = str(data[field]).strip()
                if len(value) > 2 and len(value) < 100:  # Reasonable vendor name length
                    return value
        
        # Search in all string values using patterns
        for key, value in data.items():
            if isinstance(value, str) and len(value) < 500:  # Don't search in long text
                for pattern in self.vendor_patterns:
                    match = re.search(pattern, value, re.IGNORECASE)
                    if match:
                        vendor_name = match.group(1).strip()
                        if len(vendor_name) > 2 and len(vendor_name) < 100:
                            return vendor_name
        
        return None
    
    def _find_total_in_data(self, data: Dict[str, Any]) -> Optional[float]:
        """Find total amount in extracted data."""
        # Check common total field names
        total_fields = ['total', 'amount', 'grand_total', 'final_total', 'sum', 'price']
        
        for field in total_fields:
            if field in data and data[field]:
                try:
                    # Try to convert to float
                    if isinstance(data[field], (int, float)):
                        return float(data[field])
                    elif isinstance(data[field], str):
                        # Remove currency symbols and convert
                        cleaned = re.sub(r'[$£€¥,]', '', data[field])
                        return float(cleaned)
                except (ValueError, TypeError):
                    continue
        
        return None
    
    def _clean_vendor_name(self, vendor_name: str) -> str:
        """Clean and normalize vendor name."""
        # Remove common suffixes and clean up
        cleaned = vendor_name.strip()
        cleaned = re.sub(r'\s+(Inc|LLC|Corp|Ltd|GmbH|SA|SARL)\s*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'[^\w\s&-]', '', cleaned)  # Remove special characters
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()  # Normalize whitespace
        
        # Limit length
        if len(cleaned) > 50:
            cleaned = cleaned[:47] + "..."
        
        return cleaned
    
    def _determine_document_type(self, data: Dict[str, Any], original_filename: Optional[str]) -> str:
        """Determine document type based on content and filename."""
        # Check filename extension
        if original_filename:
            ext = Path(original_filename).suffix.lower()
            if ext == '.pdf':
                return 'pdf'
            elif ext in ['.jpg', '.jpeg']:
                return 'jpeg'
            elif ext == '.png':
                return 'png'
        
        # Check content for type indicators
        content_str = str(data).lower()
        
        if any(word in content_str for word in ['invoice', 'bill', 'receipt']):
            return 'invoice'
        elif any(word in content_str for word in ['contract', 'agreement']):
            return 'contract'
        elif any(word in content_str for word in ['report', 'summary']):
            return 'report'
        
        return 'document'
    
    def _generate_suggested_filename(
        self, 
        data: Dict[str, Any], 
        original_filename: Optional[str], 
        metadata: Dict[str, Any]
    ) -> str:
        """Generate suggested filename based on extracted data."""
        
        # Build filename components
        components = []
        
        # Add date (YYYY-MM-DD format)
        if metadata.get('date'):
            try:
                date_obj = datetime.fromisoformat(metadata['date'].replace('Z', '+00:00'))
                components.append(date_obj.strftime('%Y-%m-%d'))
            except:
                # Try to extract date from string
                date_match = re.search(r'\d{4}-\d{2}-\d{2}', metadata['date'])
                if date_match:
                    components.append(date_match.group())
        
        # Add vendor name
        if metadata.get('vendor'):
            # Clean vendor name for filename
            vendor_clean = re.sub(r'[^\w\s-]', '', metadata['vendor'])
            vendor_clean = re.sub(r'\s+', '_', vendor_clean.strip())
            if vendor_clean:
                components.append(vendor_clean)
        
        # Add document type
        if metadata.get('type'):
            components.append(metadata['type'])
        
        # Add original filename as fallback
        if not components and original_filename:
            name_part = Path(original_filename).stem
            components.append(name_part)
        
        # Default to timestamp if nothing else
        if not components:
            components.append(datetime.now().strftime('%Y%m%d_%H%M%S'))
        
        # Join components and add extension
        filename_base = "_".join(components)
        
        # Determine extension
        if original_filename:
            ext = Path(original_filename).suffix
        else:
            ext = '.pdf'  # Default to PDF
        
        # Ensure reasonable length
        if len(filename_base) > 100:
            filename_base = filename_base[:97] + "..."
        
        return f"{filename_base}{ext}"
    
    def _generate_routing_folder(self, metadata: Dict[str, Any]) -> str:
        """Generate routing folder path for Google Drive organization."""
        folder_parts = []
        
        # Add year
        if metadata.get('year'):
            folder_parts.append(str(metadata['year']))
        else:
            folder_parts.append(str(datetime.now().year))
        
        # Add month (zero-padded)
        if metadata.get('month'):
            folder_parts.append(f"{metadata['month']:02d}")
        else:
            folder_parts.append(f"{datetime.now().month:02d}")
        
        # Add vendor if available
        if metadata.get('vendor'):
            # Clean vendor name for folder
            vendor_folder = re.sub(r'[^\w\s-]', '', metadata['vendor'])
            vendor_folder = re.sub(r'\s+', '_', vendor_folder.strip())
            if vendor_folder and len(vendor_folder) <= 50:
                folder_parts.append(vendor_folder)
        
        # Add document type
        if metadata.get('type'):
            folder_parts.append(metadata['type'])
        
        return "/".join(folder_parts)
    
    def _detect_mime_type(self, filename: str) -> str:
        """Detect MIME type from filename extension."""
        ext = Path(filename).suffix.lower()
        
        mime_map = {
            '.pdf': 'application/pdf',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.tiff': 'image/tiff',
            '.bmp': 'image/bmp',
            '.webp': 'image/webp'
        }
        
        return mime_map.get(ext, 'application/octet-stream')

# Global formatter instance
_output_formatter = None

def format_n8n_output(
    extracted_data: Dict[str, Any],
    original_filename: Optional[str] = None,
    processing_method: str = "unknown",
    confidence: float = 0.0,
    filter_keywords_found: List[str] = None
) -> Dict[str, Any]:
    """
    Format output for n8n integration with Google Drive routing metadata.
    
    Args:
        extracted_data: Raw extracted data
        original_filename: Original filename
        processing_method: cpu_fast or gpu_vision
        confidence: Extraction confidence score
        filter_keywords_found: Keywords that were found during filtering
        
    Returns:
        n8n-compatible formatted output
    """
    global _output_formatter
    
    if _output_formatter is None:
        _output_formatter = OutputFormatter()
    
    return _output_formatter.format_n8n_output(
        extracted_data, original_filename, processing_method, confidence, filter_keywords_found
    )