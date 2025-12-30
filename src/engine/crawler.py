"""Web crawling module using Crawl4AI with smart document detection and routing."""

import os
import asyncio
import re
from typing import Optional, List, Dict, Any
from urllib.parse import urljoin, urlparse
from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig
import structlog

logger = structlog.get_logger(__name__)

def get_proxy_url() -> Optional[str]:
    """
    Get Proxy URL from Environment (Apify injects this).
    
    Returns:
        Proxy URL if available, None otherwise
    """
    password = os.getenv('APIFY_PROXY_PASSWORD')
    if not password:
        logger.warning("No Apify proxy password found, crawling without proxy")
        return None
    
    proxy_url = f"http://auto:{password}@proxy.apify.com:8000"
    logger.info("Apify proxy configured", proxy_url=proxy_url.replace(password, '***'))
    return proxy_url

def extract_document_urls(content: str, base_url: str) -> List[str]:
    """
    Extract PDF and image URLs from HTML content.
    
    Args:
        content: HTML content
        base_url: Base URL for resolving relative URLs
        
    Returns:
        List of document URLs found in the content
    """
    document_urls = []
    
    # Pattern to match PDF and image links
    patterns = [
        r'href=["\']([^"\']*\.pdf(?:\?[^"\']*)?)["\']',  # PDF links
        r'src=["\']([^"\']*\.(?:jpg|jpeg|png|gif|webp|tiff|bmp)(?:\?[^"\']*)?)["\']',  # Image src
        r'href=["\']([^"\']*\.(?:jpg|jpeg|png|gif|webp|tiff|bmp)(?:\?[^"\']*)?)["\']',  # Image links
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        for match in matches:
            # Resolve relative URLs
            full_url = urljoin(base_url, match)
            document_urls.append(full_url)
    
    # Also look for embedded PDFs in iframes
    iframe_pattern = r'<iframe[^>]*src=["\']([^"\']*\.pdf(?:\?[^"\']*)?)["\'][^>]*>'
    iframe_matches = re.findall(iframe_pattern, content, re.IGNORECASE)
    for match in iframe_matches:
        full_url = urljoin(base_url, match)
        document_urls.append(full_url)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_urls = []
    for url in document_urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    
    if unique_urls:
        logger.info("Found embedded documents in web content", 
                   base_url=base_url, 
                   document_count=len(unique_urls),
                   documents=unique_urls[:3])  # Log first 3 for brevity
    
    return unique_urls

async def process_embedded_documents(document_urls: List[str], use_gpu_ocr: bool = False) -> List[Dict[str, Any]]:
    """
    Process embedded documents found in web content.
    
    Args:
        document_urls: List of document URLs to process
        use_gpu_ocr: Whether to use GPU OCR for complex documents
        
    Returns:
        List of processing results
    """
    if not document_urls:
        return []
    
    logger.info("Processing embedded documents", document_count=len(document_urls))
    
    from .ocr import process_document  # Import here to avoid circular imports
    
    results = []
    for doc_url in document_urls:
        try:
            logger.info("Processing embedded document", url=doc_url)
            
            # Determine document type
            doc_type = "pdf" if doc_url.lower().endswith(".pdf") else "image"
            
            # Process the document
            result = await process_document(doc_url, use_gpu_ocr=use_gpu_ocr)
            
            results.append({
                "url": doc_url,
                "type": doc_type,
                "content": result.get("markdown", ""),
                "confidence": result.get("confidence", 0),
                "engine": result.get("engine", "unknown")
            })
            
            logger.info("Embedded document processed", 
                       url=doc_url, 
                       confidence=result.get("confidence", 0))
            
        except Exception as e:
            logger.error("Failed to process embedded document", 
                        url=doc_url, 
                        error=str(e))
            results.append({
                "url": doc_url,
                "type": "error",
                "content": "",
                "confidence": 0,
                "error": str(e)
            })
    
    return results

def merge_web_and_documents(web_content: str, document_results: List[Dict[str, Any]]) -> str:
    """
    Merge web content with extracted document content.
    
    Args:
        web_content: Original web content in markdown
        document_results: Results from processing embedded documents
        
    Returns:
        Combined markdown content
    """
    if not document_results:
        return web_content
    
    # Start with web content
    combined_content = web_content
    
    # Add document content sections
    for i, doc_result in enumerate(document_results):
        if doc_result.get("content"):
            doc_type = doc_result.get("type", "document")
            doc_url = doc_result.get("url", f"document_{i+1}")
            confidence = doc_result.get("confidence", 0)
            
            # Add section header
            combined_content += f"\n\n## Embedded {doc_type.upper()}: {doc_url}\n"
            combined_content += f"*Confidence: {confidence:.2f} | Engine: {doc_result.get('engine', 'unknown')}*\n\n"
            
            # Add the extracted content
            combined_content += doc_result["content"]
    
    logger.info("Merged web and document content", 
               web_length=len(web_content),
               document_count=len(document_results),
               combined_length=len(combined_content))
    
    return combined_content

async def crawl_url(url: str, use_proxy: bool = True, process_documents: bool = True) -> str:
    """
    Crawl a web URL and extract markdown content using Crawl4AI.
    Automatically detects and processes embedded documents.
    
    Args:
        url: The URL to crawl
        use_proxy: Whether to use Apify proxy (default: True)
        process_documents: Whether to process embedded documents (default: True)
        
    Returns:
        Extracted markdown content (web + embedded documents)
        
    Raises:
        Exception: If crawling fails
    """
    logger.info("Starting web crawl with document detection", url=url, use_proxy=use_proxy)
    
    try:
        # Configure browser with proxy if available
        proxy_url = get_proxy_url() if use_proxy else None
        
        browser_config = BrowserConfig(
            headless=True,
            proxy=proxy_url,
            user_agent="Mozilla/5.0 (compatible; DocuFlow-Bot/1.0; +https://docuflow.ai/bot)"
        )
        
        crawl_config = CrawlerRunConfig(
            wait_for="body",
            remove_overlay_elements=True,
            exclude_external_links=True,
            exclude_social_media_links=True,
            magic=True,  # Enable magic mode for better extraction
            simulate_user=True,  # Simulate real user behavior
        )
        
        async with AsyncWebCrawler(config=browser_config) as crawler:
            logger.debug("Crawler initialized, running extraction", url=url)
            
            result = await crawler.arun(
                url=url,
                config=crawl_config
            )
            
            if not result.success:
                error_msg = f"Crawling failed: {result.error_message}"
                logger.error(error_msg, url=url, error=result.error_message)
                raise Exception(error_msg)
            
            if not result.markdown:
                logger.warning("No markdown content extracted", url=url)
                return ""
            
            # Clean up the markdown
            markdown = result.markdown.strip()
            
            # Extract and process embedded documents if enabled
            document_content = ""
            if process_documents:
                # Extract document URLs from the HTML content
                document_urls = extract_document_urls(result.html if hasattr(result, 'html') else '', url)
                
                if document_urls:
                    # Process embedded documents
                    document_results = await process_embedded_documents(document_urls, use_gpu_ocr=False)
                    
                    # Merge web content with document content
                    markdown = merge_web_and_documents(markdown, document_results)
            
            logger.info("Crawling completed successfully", 
                       url=url, 
                       content_length=len(markdown),
                       title=result.metadata.get('title', 'Unknown'),
                       has_documents=bool(document_urls) if process_documents else False)
            
            return markdown
            
    except Exception as e:
        logger.error("Crawling failed with exception", 
                    url=url, 
                    error=str(e),
                    error_type=type(e).__name__)
        raise Exception(f"Failed to crawl {url}: {str(e)}")

async def crawl_with_retry(url: str, max_retries: int = 3, use_proxy: bool = True, process_documents: bool = True) -> str:
    """
    Crawl URL with retry logic and fallback strategies.
    Includes document detection and processing.
    
    Args:
        url: The URL to crawl
        max_retries: Maximum number of retry attempts
        use_proxy: Whether to use proxy (will try without proxy on failure)
        process_documents: Whether to process embedded documents
        
    Returns:
        Extracted markdown content (web + embedded documents)
        
    Raises:
        Exception: If all retry attempts fail
    """
    for attempt in range(max_retries):
        try:
            logger.info("Crawl attempt", url=url, attempt=attempt + 1, max_retries=max_retries)
            
            # On later attempts, try without proxy if initial attempts failed
            current_use_proxy = use_proxy if attempt == 0 else False
            
            return await crawl_url(url, use_proxy=current_use_proxy, process_documents=process_documents)
            
        except Exception as e:
            logger.warning("Crawl attempt failed", 
                          url=url, 
                          attempt=attempt + 1, 
                          error=str(e))
            
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2  # Exponential backoff
                logger.info("Retrying after delay", wait_seconds=wait_time)
                await asyncio.sleep(wait_time)
            else:
                logger.error("All crawl attempts failed", 
                           url=url, 
                           total_attempts=max_retries)
                raise
    
    raise Exception(f"Failed to crawl {url} after {max_retries} attempts")

def validate_crawl_result(markdown: str, min_length: int = 100) -> bool:
    """
    Validate the quality of crawled content.
    
    Args:
        markdown: The extracted markdown content
        min_length: Minimum acceptable content length
        
    Returns:
        True if content is valid, False otherwise
    """
    if not markdown or len(markdown.strip()) < min_length:
        logger.warning("Crawled content too short", 
                      content_length=len(markdown) if markdown else 0,
                      min_length=min_length)
        return False
    
    # Check for common error pages
    error_indicators = [
        "404 not found", "page not found", "error 404", 
        "internal server error", "503 service unavailable",
        "access denied", "forbidden", "unauthorized"
    ]
    
    content_lower = markdown.lower()
    for indicator in error_indicators:
        if indicator in content_lower:
            logger.warning("Error page detected", indicator=indicator)
            return False
    
    return True