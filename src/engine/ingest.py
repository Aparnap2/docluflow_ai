"""Robust input type detection and defense logic for DocuFlow Headless."""

import requests
from typing import Literal
from urllib.parse import urlparse
import structlog

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
    if content_length < 50:
        logger.warning("Content too short, likely garbage", 
                      content_length=content_length, min_length=50)
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