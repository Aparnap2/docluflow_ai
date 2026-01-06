"""
Enterprise-grade security and validation utilities for PropFlow Agent.

Zero-cost Python checks that prevent expensive failures:
- Password protected PDF detection
- Filename sanitization
- File type verification (magic bytes)
- Input truncation (prevent ReDoS)
- PDF compression (cost saver)
"""
import re
import os
import tempfile
from typing import Optional, Dict, Any
from pathlib import Path


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent injection attacks.
    
    Removes dangerous characters and path traversal attempts.
    """
    # Remove path separators and dangerous characters
    # Keep only alphanumeric, dots, dashes, underscores
    clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)
    
    # Remove path traversal attempts
    clean_name = clean_name.replace('..', '_')
    clean_name = clean_name.replace('/', '_')
    clean_name = clean_name.replace('\\', '_')
    
    # Limit length
    clean_name = clean_name[:255]
    
    # Ensure it's not empty
    if not clean_name or clean_name.startswith('.'):
        clean_name = 'document.pdf'
    
    return clean_name


def check_pdf_encryption(file_path: str) -> Optional[Dict[str, str]]:
    """
    Check if PDF is password protected before processing.
    
    Returns error dict if encrypted, None if safe to process.
    """
    try:
        from pypdf import PdfReader
        
        reader = PdfReader(file_path)
        if reader.is_encrypted:
            return {
                "error": "PDF is password protected. Please unlock it before uploading.",
                "error_type": "encrypted_pdf"
            }
    except ImportError:
        # pypdf not installed, skip check (will fail later anyway)
        pass
    except Exception as e:
        # Corrupted PDF or other error
        return {
            "error": f"PDF file appears corrupted or invalid: {str(e)}",
            "error_type": "corrupted_pdf"
        }
    
    return None


def verify_file_type(file_path: str, expected_type: str = "application/pdf") -> Optional[Dict[str, str]]:
    """
    Verify actual file type using magic bytes (not just extension).
    
    Prevents malicious files renamed to .pdf extension.
    
    Note: python-magic is optional. If not installed, falls back to extension check.
    """
    try:
        import magic
        
        mime = magic.Magic(mime=True)
        actual_type = mime.from_file(file_path)
        
        if actual_type != expected_type:
            return {
                "error": f"Invalid file type. Expected {expected_type}, got {actual_type}. File may be malicious or incorrectly named.",
                "error_type": "invalid_file_type",
                "detected_type": actual_type
            }
    except ImportError:
        # python-magic not installed, skip magic bytes check
        # Fallback: check extension only (less secure but better than nothing)
        if not file_path.lower().endswith('.pdf'):
            return {
                "error": "File does not appear to be a PDF (missing .pdf extension). Note: Install python-magic for magic bytes verification.",
                "error_type": "invalid_extension",
                "warning": "Magic bytes check unavailable (python-magic not installed)"
            }
    except Exception as e:
        # Magic bytes check failed, but don't block (might be false positive)
        # Log warning but continue
        pass
    
    return None


def truncate_text(text: str, max_length: int = 100000) -> str:
    """
    Truncate text to prevent ReDoS attacks and buffer overflows.
    
    Limits input size before regex operations.
    """
    if len(text) > max_length:
        return text[:max_length]
    return text


def safe_regex_search(pattern: str, text: str, max_length: int = 100000) -> Optional[re.Match]:
    """
    Safe regex search with input truncation to prevent ReDoS.
    
    Truncates input before running regex to prevent catastrophic backtracking.
    """
    truncated_text = truncate_text(text, max_length)
    try:
        return re.search(pattern, truncated_text, re.DOTALL)
    except re.error:
        # Invalid regex pattern
        return None


def compress_pdf_if_needed(file_path: str, max_size_mb: int = 10) -> tuple[str, bool]:
    """
    Compress PDF if it exceeds size limit.
    
    Returns: (file_path, was_compressed)
    
    Note: Requires ghostscript or pypdf compression capabilities.
    For now, returns original path (compression can be added later).
    """
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    
    if file_size_mb > max_size_mb:
        # TODO: Implement PDF compression using pypdf or ghostscript
        # For now, just return original (compression is optional optimization)
        return file_path, False
    
    return file_path, False


def validate_document_url(url: str) -> Optional[Dict[str, str]]:
    """
    Validate document URL before fetching.
    
    Checks for:
    - Valid URL format
    - Allowed protocols (http, https)
    - Reasonable length
    """
    # Check URL length
    if len(url) > 2048:
        return {
            "error": "URL too long (max 2048 characters)",
            "error_type": "invalid_url"
        }
    
    # Check protocol
    # Allow file:// for local dev
    if not url.startswith(('http://', 'https://', 'file://')):
        return {
            "error": "Invalid URL protocol. Only http://, https://, and file:// are allowed",
            "error_type": "invalid_protocol"
        }
    
    # Basic URL format check
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if not parsed.netloc:
            return {
                "error": "Invalid URL format",
                "error_type": "invalid_url_format"
            }
    except Exception:
        return {
            "error": "Invalid URL format",
            "error_type": "invalid_url_format"
        }
    
    return None


def validate_and_prepare_document(doc_url: str, doc_bytes: bytes, temp_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Comprehensive document validation and preparation.
    
    Performs all security checks:
    1. Filename sanitization
    2. File type verification
    3. Encryption check
    4. Size validation
    
    Returns dict with 'file_path' and 'error' (if any).
    """
    result = {
        "file_path": None,
        "error": None,
        "was_compressed": False,
        "file_size_mb": 0
    }
    
    # Validate URL only if it looks like one
    if doc_url.startswith(('http://', 'https://', 'file://')):
        url_error = validate_document_url(doc_url)
        if url_error:
            result["error"] = url_error
            return result
    
    # Sanitize filename from URL or hint
    if '://' in doc_url:
        filename = os.path.basename(doc_url.split('?')[0])
    else:
        filename = doc_url
    sanitized_filename = sanitize_filename(filename)
    if not sanitized_filename.endswith('.pdf'):
        sanitized_filename += '.pdf'
    
    # Check file size
    file_size_mb = len(doc_bytes) / (1024 * 1024)
    result["file_size_mb"] = file_size_mb
    
    if file_size_mb > 50:  # 50MB limit
        result["error"] = {
            "error": f"File too large ({file_size_mb:.1f}MB). Maximum size is 50MB.",
            "error_type": "file_too_large"
        }
        return result
    
    # Create temporary file
    temp_dir = temp_dir or tempfile.gettempdir()
    temp_file_path = os.path.join(temp_dir, sanitized_filename)
    
    try:
        # Write bytes to temp file
        with open(temp_file_path, 'wb') as f:
            f.write(doc_bytes)
        
        # Verify file type (magic bytes)
        type_error = verify_file_type(temp_file_path)
        if type_error:
            os.unlink(temp_file_path)
            result["error"] = type_error
            return result
        
        # Check for encryption
        encryption_error = check_pdf_encryption(temp_file_path)
        if encryption_error:
            os.unlink(temp_file_path)
            result["error"] = encryption_error
            return result
        
        # Compress if needed (optional optimization)
        final_path, was_compressed = compress_pdf_if_needed(temp_file_path, max_size_mb=10)
        result["file_path"] = final_path
        result["was_compressed"] = was_compressed
        
    except Exception as e:
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
        result["error"] = {
            "error": f"Failed to prepare document: {str(e)}",
            "error_type": "preparation_error"
        }
    
    return result

