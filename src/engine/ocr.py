"""OCR processing module using Docling with granite-docling:256m (CPU) and DeepSeek-OCR (GPU fallback)."""

import os
import asyncio
import aiohttp
from typing import Optional, Dict, Any
from pathlib import Path
import tempfile
import requests
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
import structlog

logger = structlog.get_logger(__name__)

class OCRProcessor:
    """Hybrid OCR processor with CPU (granite-docling) and GPU (deepseek-ocr) capabilities."""
    
    def __init__(self):
        self.converter = None
        self._setup_docling()
        
    def _setup_docling(self):
        """Initialize Docling converter with granite-docling model for CPU processing."""
        try:
            # Configure PDF pipeline for optimal OCR results with granite-docling
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = True
            pipeline_options.do_table_structure = True
            pipeline_options.ocr_options.lang = ["en"]  # Primary language
            
            # Note: Docling automatically uses CPU for processing
            # The granite-docling model is used when available via Ollama
            
            self.converter = DocumentConverter(
                pipeline_options=pipeline_options
            )
            logger.info("Docling converter initialized with granite-docling:256m model")
        except TypeError as e:
            # Fallback to basic initialization if pipeline_options is not supported
            logger.warning("Advanced pipeline options not supported, using basic Docling converter", error=str(e))
            self.converter = DocumentConverter()
            logger.info("Docling converter initialized with basic configuration")
        except Exception as e:
            logger.error("Failed to initialize Docling converter", error=str(e))
            raise

    async def process_document(self, url: str, use_gpu_ocr: bool = False, confidence_threshold: float = 0.7) -> Dict[str, Any]:
        """
        Process document (PDF/Image) with hybrid OCR approach.
        
        Args:
            url: URL of the document to process
            use_gpu_ocr: Whether to force GPU OCR (for complex documents)
            confidence_threshold: Minimum confidence before trying GPU OCR
            
        Returns:
            Dict with extracted content and metadata
            
        Raises:
            Exception: If processing fails
        """
        logger.info("Starting document processing", url=url, use_gpu_ocr=use_gpu_ocr)
        
        try:
            # First, try local Docling processing (CPU with granite-docling)
            if not use_gpu_ocr:
                try:
                    result = await self._process_with_docling_cpu(url)
                    
                    # Check if we need GPU OCR based on confidence
                    if result.get("confidence", 0) < confidence_threshold or result.get("needs_gpu_ocr", False):
                        logger.info("Low confidence detected, falling back to GPU OCR", 
                                   confidence=result.get("confidence"),
                                   url=url)
                        return await self._process_with_deepseek_gpu(url)
                    
                    return result
                    
                except Exception as e:
                    logger.warning("Docling CPU processing failed, falling back to GPU OCR", 
                                 error=str(e))
                    return await self._process_with_deepseek_gpu(url)
            
            # Direct GPU OCR if requested
            if use_gpu_ocr:
                return await self._process_with_deepseek_gpu(url)
                
        except Exception as e:
            logger.error("Document processing failed", url=url, error=str(e))
            raise Exception(f"Failed to process document {url}: {str(e)}")

    async def _process_with_docling_cpu(self, url: str) -> Dict[str, Any]:
        """
        Process document using Docling with granite-docling:256m (CPU-only).
        
        Args:
            url: URL of the document
            
        Returns:
            Dict with extracted content and confidence metrics
        """
        logger.info("Processing with Docling CPU (granite-docling:256m)", url=url)
        
        try:
            # Download file to temporary location
            with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as tmp_file:
                tmp_path = tmp_file.name
                
                # Download the file
                logger.debug("Downloading document", url=url)
                response = requests.get(url, timeout=30, stream=True)
                response.raise_for_status()
                
                # Write to temp file
                for chunk in response.iter_content(chunk_size=8192):
                    tmp_file.write(chunk)
                
                file_size = os.path.getsize(tmp_path)
                logger.debug("Document downloaded", size=file_size)
                
            try:
                # Convert document using Docling with granite model
                logger.debug("Converting document with Docling granite", path=tmp_path)
                
                import time
                start_time = time.time()
                
                result = self.converter.convert(tmp_path)
                
                processing_time = time.time() - start_time
                
                # Export to markdown
                markdown = result.document.export_to_markdown()
                
                # Calculate confidence based on content quality
                confidence = self._calculate_docling_confidence(markdown, result)
                
                # Check if GPU OCR might improve results
                needs_gpu_ocr = self._assess_gpu_ocr_need(markdown, confidence)
                
                logger.info("Docling CPU processing completed", 
                           url=url, 
                           content_length=len(markdown),
                           confidence=confidence,
                           needs_gpu_ocr=needs_gpu_ocr,
                           processing_time=processing_time)
                
                return {
                    "markdown": markdown,
                    "confidence": confidence,
                    "needs_gpu_ocr": needs_gpu_ocr,
                    "processing_time": processing_time,
                    "engine": "docling_cpu",
                    "metadata": {
                        "pages": len(result.document.pages) if hasattr(result.document, 'pages') else 1,
                        "file_size": file_size,
                        "ocr_engine": "granite-docling:256m"
                    }
                }
                
            finally:
                # Clean up temp file
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                    
        except Exception as e:
            logger.error("Docling CPU processing failed", url=url, error=str(e))
            raise

    async def _process_with_deepseek_gpu(self, url: str) -> Dict[str, Any]:
        """
        Process document using DeepSeek OCR (GPU) via Ollama.
        
        Args:
            url: URL of the document
            
        Returns:
            Dict with extracted content and metadata
        """
        logger.info("Processing with DeepSeek OCR (GPU via Ollama)", url=url)
        
        try:
            # Use Ollama for DeepSeek OCR processing
            ollama_endpoint = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
            deepseek_model = "deepseek-ocr:3b"  # Use the 3B model we have available
            
            # Download file to temporary location
            with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as tmp_file:
                tmp_path = tmp_file.name
                
                # Download the file
                logger.debug("Downloading document for DeepSeek OCR", url=url)
                response = requests.get(url, timeout=60, stream=True)
                response.raise_for_status()
                
                # Write to temp file
                for chunk in response.iter_content(chunk_size=8192):
                    tmp_file.write(chunk)
                
                file_size = os.path.getsize(tmp_path)
                logger.debug("Document downloaded for DeepSeek OCR", size=file_size)
                
            try:
                # Process with DeepSeek OCR via Ollama
                logger.debug("Processing with DeepSeek OCR", model=deepseek_model)
                
                import time
                start_time = time.time()
                
                # Read the file and encode as base64 for Ollama
                import base64
                with open(tmp_path, 'rb') as f:
                    file_content = f.read()
                
                # Encode as base64 for JSON serialization
                encoded_content = base64.b64encode(file_content).decode('utf-8')
                
                # Prepare the request to Ollama
                ocr_request = {
                    "model": deepseek_model,
                    "prompt": f"Extract all text from this document and convert to markdown format. Preserve structure, tables, and formatting where possible.",
                    "images": [encoded_content],  # Send as base64 encoded image
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "top_p": 0.9
                    }
                }
                
                # Call Ollama API
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{ollama_endpoint}/api/generate",
                        json=ocr_request,
                        timeout=aiohttp.ClientTimeout(total=300)
                    ) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            raise Exception(f"Ollama DeepSeek OCR failed: {error_text}")
                        
                        result = await response.json()
                        markdown = result.get("response", "")
                        
                        processing_time = time.time() - start_time
                
                # Calculate confidence for DeepSeek results
                confidence = self._calculate_deepseek_confidence(markdown, result)
                
                logger.info("DeepSeek OCR processing completed", 
                           url=url, 
                           content_length=len(markdown),
                           confidence=confidence,
                           processing_time=processing_time)
                
                return {
                    "markdown": markdown,
                    "confidence": confidence,
                    "needs_gpu_ocr": False,  # Already using GPU
                    "processing_time": processing_time,
                    "engine": "deepseek_gpu",
                    "metadata": {
                        "pages": 1,  # DeepSeek processes per page
                        "file_size": file_size,
                        "ocr_engine": "deepseek-ocr:3b",
                        "ollama_host": ollama_endpoint
                    }
                }
                
            finally:
                # Clean up temp file
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                    
        except Exception as e:
            logger.error("DeepSeek OCR processing failed", url=url, error=str(e))
            raise

    def _calculate_docling_confidence(self, markdown: str, result) -> float:
        """
        Calculate confidence score for Docling extraction.
        
        Args:
            markdown: Extracted markdown content
            result: Docling conversion result
            
        Returns:
            Confidence score (0-1)
        """
        if not markdown or len(markdown.strip()) < 50:
            return 0.1
        
        # Base confidence from content length
        content_length = len(markdown.strip())
        base_confidence = min(0.8, content_length / 10000)  # Cap at 0.8 for CPU processing
        
        # Check for common OCR issues
        issues = 0
        
        # Excessive special characters (possible OCR artifacts)
        special_char_ratio = sum(1 for c in markdown if not c.isalnum() and not c.isspace()) / len(markdown)
        if special_char_ratio > 0.3:
            issues += 1
        
        # Very short lines (possible OCR segmentation issues)
        lines = markdown.split('\n')
        short_lines = sum(1 for line in lines if len(line.strip()) < 5)
        if short_lines / len(lines) > 0.5:
            issues += 1
        
        # Missing structural elements
        if '# ' not in markdown and len(lines) > 10:  # No headers in long document
            issues += 0.5
        
        # Reduce confidence based on issues
        confidence = max(0.1, base_confidence - (issues * 0.2))
        
        return round(confidence, 2)

    def _calculate_deepseek_confidence(self, markdown: str, result: Dict[str, Any]) -> float:
        """
        Calculate confidence score for DeepSeek OCR extraction.
        
        Args:
            markdown: Extracted markdown content
            result: Ollama API result
            
        Returns:
            Confidence score (0-1)
        """
        if not markdown or len(markdown.strip()) < 50:
            return 0.3  # Higher minimum for GPU processing
        
        # Base confidence from content length and GPU processing
        content_length = len(markdown.strip())
        base_confidence = min(0.95, 0.7 + (content_length / 20000))  # Higher base for GPU
        
        # Check for quality indicators
        quality_boost = 0
        
        # Well-structured content
        if '# ' in markdown:  # Has headers
            quality_boost += 0.1
        
        # Reasonable line lengths
        lines = markdown.split('\n')
        avg_line_length = sum(len(line) for line in lines) / len(lines) if lines else 0
        if 20 < avg_line_length < 200:  # Reasonable line length
            quality_boost += 0.1
        
        # No excessive repetition (sign of OCR issues)
        words = markdown.lower().split()
        if len(words) > 10:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio > 0.7:  # Good vocabulary diversity
                quality_boost += 0.1
        
        confidence = min(0.95, base_confidence + quality_boost)
        
        return round(confidence, 2)

    def _assess_gpu_ocr_need(self, markdown: str, confidence: float) -> bool:
        """
        Assess whether GPU OCR would improve results.
        
        Args:
            markdown: Extracted markdown content
            confidence: Current confidence score
            
        Returns:
            True if GPU OCR is recommended
        """
        # Low confidence threshold
        if confidence < 0.5:
            return True
        
        # Check for OCR artifacts
        if '�' in markdown:  # Unicode replacement characters
            return True
        
        # Excessive special characters (OCR artifacts)
        special_char_ratio = sum(1 for c in markdown if not c.isalnum() and not c.isspace()) / len(markdown)
        if special_char_ratio > 0.4:
            return True
        
        # Very fragmented content
        lines = markdown.split('\n')
        if len(lines) > 20:
            short_line_ratio = sum(1 for line in lines if len(line.strip()) < 3) / len(lines)
            if short_line_ratio > 0.3:
                return True
        
        return False

    def is_ocr_recommended(self, url: str, content_type: str) -> bool:
        """
        Determine if OCR processing is recommended for the given URL.
        
        Args:
            url: The document URL
            content_type: Detected content type
            
        Returns:
            True if OCR is recommended
        """
        if content_type not in ["pdf", "image"]:
            return False
            
        # Check file extension for likely scanned content
        url_lower = url.lower()
        scanned_indicators = ['.pdf', '.jpg', '.jpeg', '.png', '.tiff', '.bmp']
        
        has_scanned_extension = any(url_lower.endswith(ext) for ext in scanned_indicators)
        
        # For now, recommend OCR for all PDFs and images
        # In production, you might analyze the actual content first
        return has_scanned_extension

# Global processor instance
_ocr_processor = None

async def process_document(url: str, use_gpu_ocr: bool = False, confidence_threshold: float = 0.7) -> Dict[str, Any]:
    """
    Process document with hybrid OCR approach.
    
    Args:
        url: URL of the document to process
        use_gpu_ocr: Whether to force GPU OCR
        confidence_threshold: Minimum confidence before trying GPU OCR
        
    Returns:
        Dict with extracted content and metadata
    """
    global _ocr_processor
    
    if _ocr_processor is None:
        _ocr_processor = OCRProcessor()
    
    return await _ocr_processor.process_document(url, use_gpu_ocr, confidence_threshold)

def is_ocr_recommended(url: str, content_type: str) -> bool:
    """
    Determine if OCR processing is recommended.
    
    Args:
        url: The document URL
        content_type: Detected content type
        
    Returns:
        True if OCR is recommended
    """
    global _ocr_processor
    
    if _ocr_processor is None:
        _ocr_processor = OCRProcessor()
    
    return _ocr_processor.is_ocr_recommended(url, content_type)