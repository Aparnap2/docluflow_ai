"""Robust input type detection and defense logic for DocuFlow Headless."""

import requests
import fitz  # PyMuPDF
import tempfile
from typing import Literal, List, Dict, Any, Optional
from urllib.parse import urlparse
import structlog
from PIL import Image
import os

logger = structlog.get_logger(__name__)

def determine_input_type(url: str) -> Literal["web", "pdf", "image", "error"]:
    """
    Robustly detects type via HEAD request headers.
    Handles redirects and errors with comprehensive defense logic.
    
    Args:
        url: The URL to analyze
        
    Returns:
        Type classification: "web", "pdf", "image", or "error"
    """
    try:
        # Validate URL format first
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            logger.error("Invalid URL format", url=url)
            return "error"
            
        # 1. HEAD Request (Fast and efficient)
        logger.info("Performing HEAD request for type detection", url=url)
        resp = requests.head(url, timeout=10, allow_redirects=True)
        
        # 2. Check Accessibility (Defense against private content)
        if resp.status_code in [401, 403]:
            logger.error("URL is private/access denied", 
                        url=url, status_code=resp.status_code)
            return "error"
            
        if resp.status_code >= 400:
            logger.error("URL inaccessible", 
                        url=url, status_code=resp.status_code)
            return "error"
        
        # 3. Check Size (Defense against huge files - Max 20MB)
        size = int(resp.headers.get('Content-Length', 0))
        if size > 20 * 1024 * 1024:
            logger.error("File too large for processing", 
                        url=url, size_bytes=size, max_size_bytes=20*1024*1024)
            return "error"
        
        # 4. Check Content-Type (Primary detection method)
        ctype = resp.headers.get('Content-Type', '').lower()
        logger.info("Content-Type detected", url=url, content_type=ctype)
        
        if 'application/pdf' in ctype:
            return "pdf"
        if any(img_type in ctype for img_type in ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp']):
            return "image"
        if 'text/html' in ctype or 'application/xhtml+xml' in ctype:
            return "web"
            
    except requests.exceptions.Timeout:
        logger.error("HEAD request timed out", url=url, timeout=10)
    except requests.exceptions.ConnectionError as e:
        logger.error("Connection failed during HEAD request", url=url, error=str(e))
    except Exception as e:
        logger.error("Unexpected error during HEAD request", 
                    url=url, error=str(e), error_type=type(e).__name__)
    
    # 5. Extension Fallback (When HEAD fails or is inconclusive)
    logger.warning("HEAD request failed, falling back to extension analysis", url=url)
    url_lower = url.lower()
    
    if url_lower.endswith('.pdf'): 
        return "pdf"
    if url_lower.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff')):
        return "image"
    if url_lower.endswith(('.html', '.htm', '.aspx', '.php', '.jsp')):
        return "web"
    
    # 6. Default to Web with warning (Most permissive fallback)
    logger.warning("Could not determine type, defaulting to web", url=url)
    return "web"

def is_garbage(markdown: str) -> bool:
    """
    Detects Login Walls, Empty Content, or Low-Quality Extracts.
    Implements comprehensive content quality checks.
    
    Args:
        markdown: Extracted markdown content to analyze
        
    Returns:
        True if content appears to be garbage/login wall, False otherwise
    """
    if not markdown:
        logger.warning("Empty markdown content detected")
        return True
    
    # Length check (defense against empty/minimal content)
    content_length = len(markdown.strip())
    if content_length < 15:  # Reduced threshold for simple documents like "Dummy PDF file"
        logger.warning("Content too short, likely garbage",
                      content_length=content_length, min_length=15)
        return True
    
    # Login wall detection (comprehensive trigger list)
    login_triggers = [
        "login", "sign in", "signin", "password", "subscribe", "captcha",
        "authentication required", "access denied", "unauthorized",
        "please log in", "member login", "premium content", "paywall",
        "subscription required", "register now", "create account",
        "forgot password", "reset password", "verify your email"
    ]
    
    # Check first 500 characters (most critical area for login walls)
    head = markdown[:500].lower()
    for trigger in login_triggers:
        if trigger in head:
            logger.warning("Login wall detected", 
                          trigger=trigger, preview=head[:100])
            return True
    
    # Additional quality checks
    # Check for excessive JavaScript/CSS remnants
    if markdown.count('<script') > 5 or markdown.count('style=') > 10:
        logger.warning("Excessive HTML remnants detected")
        return True
    
    # Check for repetitive patterns (often indicates poor extraction)
    lines = markdown.split('\n')
    if len(lines) > 10:
        # Check if more than 50% of lines are very short
        short_lines = sum(1 for line in lines if len(line.strip()) < 10)
        if short_lines / len(lines) > 0.7:
            logger.warning("Excessive short lines, likely poor extraction",
                          short_lines=short_lines, total_lines=len(lines))
            return True
    
    # Check for excessive whitespace
    whitespace_ratio = (len(markdown) - len(markdown.strip())) / len(markdown) if markdown else 0
    if whitespace_ratio > 0.3:
        logger.warning("Excessive whitespace detected", 
                      whitespace_ratio=whitespace_ratio)
        return True
    
    logger.info("Content quality check passed", 
                content_length=content_length, preview=head[:100])
    return False

def validate_url_accessibility(url: str) -> tuple[bool, str]:
    """
    Comprehensive URL accessibility validation.
    
    Args:
        url: URL to validate
        
    Returns:
        Tuple of (is_accessible, error_message)
    """
    try:
        # Quick connectivity test
        resp = requests.head(url, timeout=5, allow_redirects=True)
        
        if resp.status_code >= 400:
            return False, f"HTTP {resp.status_code}: {resp.reason}"
            
        return True, ""
        
    except requests.exceptions.Timeout:
        return False, "Connection timeout"
    except requests.exceptions.ConnectionError:
        return False, "Connection failed"
    except Exception as e:
        return False, f"Validation error: {str(e)}"

def compress_pdf(file_path: str) -> str:
    """Compress PDF using ghostscript if >10MB."""
    file_size = os.path.getsize(file_path)
    if file_size <= 10 * 1024 * 1024:  # 10MB
        return file_path
    
    logger.info("Compressing large PDF", original_size=file_size)
    try:
        import subprocess
        compressed_path = file_path.replace('.pdf', '_compressed.pdf')
        
        cmd = [
            'ghostscript', '-sDEVICE=pdfwrite', '-dCompatibilityLevel=1.4',
            '-dPDFSETTINGS=/screen', '-dNOPAUSE', '-dQUIET', '-dBATCH',
            f'-sOutputFile={compressed_path}', file_path
        ]
        
        subprocess.run(cmd, check=True, capture_output=True)
        compressed_size = os.path.getsize(compressed_path)
        
        logger.info("PDF compression completed",
                   original_size=file_size, compressed_size=compressed_size)
        return compressed_path
    except Exception as e:
        logger.warning("PDF compression failed, using original", error=str(e))
        return file_path

def compress_image(file_path: str) -> str:
    """Resize image if >5MB or width >2500px."""
    file_size = os.path.getsize(file_path)
    if file_size <= 5 * 1024 * 1024:  # 5MB
        return file_path
    
    logger.info("Compressing large image", original_size=file_size)
    try:
        with Image.open(file_path) as img:
            # Resize if width > 2500px
            if img.width > 2500:
                ratio = 2500 / img.width
                new_height = int(img.height * ratio)
                img = img.resize((2500, new_height), Image.Resampling.LANCZOS)
            
            # Save with optimization
            compressed_path = file_path.replace('.', '_compressed.')
            img.save(compressed_path, optimize=True, quality=85)
            
            compressed_size = os.path.getsize(compressed_path)
            logger.info("Image compression completed",
                       original_size=file_size, compressed_size=compressed_size)
            return compressed_path
    except Exception as e:
        logger.warning("Image compression failed, using original", error=str(e))
        return file_path

def filter_by_keywords(text: str, filter_keywords: List[str]) -> bool:
    """Check if any filter keyword exists in text (AGB filtering)."""
    if not filter_keywords:
        return True
    
    text_lower = text.lower()
    for keyword in filter_keywords:
        if keyword.lower() in text_lower:
            logger.info("Filter keyword found", keyword=keyword)
            return True
    
    logger.info("No filter keywords found, skipping file")
    return False

def extract_pdf_text_first_pages(url: str, max_pages: int = 2) -> Optional[str]:
    """Extract text from first N pages of PDF using PyMuPDF."""
    try:
        # Download PDF to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            response = requests.get(url, timeout=30, stream=True)
            response.raise_for_status()
            
            for chunk in response.iter_content(chunk_size=8192):
                tmp_file.write(chunk)
            
            tmp_path = tmp_file.name
        
        try:
            # Open with PyMuPDF
            doc = fitz.open(tmp_path)
            text = ""
            
            # Extract text from first max_pages pages
            for page_num in range(min(max_pages, doc.page_count)):
                page = doc[page_num]
                text += page.get_text() + "\n"
            
            doc.close()
            return text.strip()
            
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
                
    except Exception as e:
        logger.error("Failed to extract PDF text", url=url, error=str(e))
        return None

def calculate_text_density(text: str, page_count: int) -> float:
    """Calculate text density (characters per page)."""
    if page_count <= 0:
        return 0.0
    return len(text) / page_count

def route_processing(text: str, has_text_layer: bool, page_count: int) -> str:
    """Route to CPU_FAST or GPU_VISION based on text analysis."""
    if not text:
        return "GPU_VISION"
    
    text_density = calculate_text_density(text, page_count)
    
    # If has text layer and reasonable density, use CPU_FAST
    if has_text_layer and text_density > 50:
        return "CPU_FAST"
    
    return "GPU_VISION"

async def process_file_intelligently(file_info: Dict[str, Any], filter_keywords: List[str]) -> Dict[str, Any]:
    """Intelligent file processing with filtering and routing."""
    url = file_info.get("url") or file_info.get("base64")
    filename = file_info.get("filename", "unknown")
    
    if not url:
        return {"error": "No URL or base64 data provided", "skipped": True}
    
    logger.info("Processing file intelligently", filename=filename, url=url[:50])
    
    try:
        # Determine file type
        file_type = determine_input_type(url)
        if file_type == "error":
            return {"error": "Invalid or inaccessible file", "skipped": True}
        
        # For PDFs, check first 2 pages for filter keywords
        if file_type == "pdf":
            first_pages_text = extract_pdf_text_first_pages(url)
            if first_pages_text:
                # AGB filtering
                if not filter_by_keywords(first_pages_text, filter_keywords):
                    return {"skipped": True, "reason": "Filter keywords not found"}
                
                # Check if has text layer
                has_text_layer = len(first_pages_text.strip()) > 10
                
                # Route processing
                route = route_processing(first_pages_text, has_text_layer, 2)
                return {
                    "url": url,
                    "filename": filename,
                    "type": file_type,
                    "route": route,
                    "has_text_layer": has_text_layer,
                    "text_density": calculate_text_density(first_pages_text, 2)
                }
        
        # For images, always use GPU_VISION
        if file_type == "image":
            return {
                "url": url,
                "filename": filename,
                "type": file_type,
                "route": "GPU_VISION"
            }
        
        # For web content, use CPU_FAST
        if file_type == "web":
            return {
                "url": url,
                "filename": filename,
                "type": file_type,
                "route": "CPU_FAST"
            }
        
        return {"error": "Unsupported file type", "skipped": True}
        
    except Exception as e:
        logger.error("Intelligent processing failed", filename=filename, error=str(e))
        return {"error": str(e), "skipped": True}