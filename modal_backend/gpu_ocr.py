"""Modal GPU backend for DeepSeek-OCR processing."""

import modal
import os
import tempfile
import requests
from typing import Dict, Any, Optional
import json
import structlog

# Configure logging
logger = structlog.get_logger(__name__)

# Create Modal stub
stub = modal.Stub("docuflow-gpu-ocr")

# Define the container image with required dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "requests>=2.31.0",
        "pillow>=10.0.0",
        "opencv-python>=4.8.0",
        "numpy>=1.24.0",
        "torch>=2.0.0",
        "transformers>=4.30.0",
        "docling>=1.0.0",
        "structlog>=23.1.0",
        "pydantic>=2.5.0"
    )
    .apt_install(
        "tesseract-ocr",
        "tesseract-ocr-eng",
        "libgl1-mesa-glx",
        "libglib2.0-0"
    )
)

@stub.function(
    gpu="A10G",  # A10G GPU for optimal OCR performance
    timeout=600,  # 10 minute timeout
    image=image,
    secrets=[
        modal.Secret.from_name("docuflow-secrets")  # For API keys if needed
    ]
)
@modal.web_endpoint(method="POST")
async def process_ocr(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process document with GPU-accelerated OCR using DeepSeek.
    
    Args:
        item: Processing request containing:
            - file_url: URL of the document to process
            - ocr_engine: OCR engine to use (default: deepseek)
            - output_format: Output format (default: markdown)
            - options: Additional processing options
            
    Returns:
        Processing result with extracted text
    """
    try:
        logger.info("Starting GPU OCR processing", item=item)
        
        # Validate input
        file_url = item.get("file_url")
        if not file_url:
            raise ValueError("file_url is required")
        
        ocr_engine = item.get("ocr_engine", "deepseek")
        output_format = item.get("output_format", "markdown")
        options = item.get("options", {})
        
        logger.info("Processing parameters",
                   file_url=file_url,
                   ocr_engine=ocr_engine,
                   output_format=output_format)
        
        # Download the file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as tmp_file:
            tmp_path = tmp_file.name
            
            logger.debug("Downloading file", url=file_url)
            response = requests.get(file_url, timeout=60, stream=True)
            response.raise_for_status()
            
            # Write to temp file
            for chunk in response.iter_content(chunk_size=8192):
                tmp_file.write(chunk)
            
            file_size = os.path.getsize(tmp_path)
            logger.info("File downloaded", path=tmp_path, size=file_size)
        
        try:
            # Process based on OCR engine
            if ocr_engine == "deepseek":
                result = await _process_with_deepseek(tmp_path, output_format, options)
            elif ocr_engine == "docling":
                result = await _process_with_docling_gpu(tmp_path, output_format, options)
            else:
                raise ValueError(f"Unsupported OCR engine: {ocr_engine}")
            
            logger.info("GPU OCR processing completed",
                       file_url=file_url,
                       content_length=len(result.get("markdown", "")))
            
            return {
                "success": True,
                "markdown": result.get("markdown", ""),
                "metadata": result.get("metadata", {}),
                "processing_time": result.get("processing_time", 0),
                "ocr_engine": ocr_engine
            }
            
        finally:
            # Clean up temp file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
                
    except Exception as e:
        logger.error("GPU OCR processing failed", error=str(e), item=item)
        
        return {
            "success": False,
            "error": str(e),
            "markdown": "",
            "metadata": {}
        }

async def _process_with_deepseek(file_path: str, output_format: str, options: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process document with DeepSeek OCR.
    
    This is a placeholder implementation. In production, you would:
    1. Load the actual DeepSeek OCR model
    2. Process the image/document
    3. Return structured results
    
    For now, we'll use a simplified approach with Docling as fallback.
    """
    logger.info("Processing with DeepSeek OCR", file_path=file_path)
    
    try:
        # For MVP, we'll use Docling with enhanced GPU processing
        # In production, replace with actual DeepSeek OCR implementation
        
        from docling.document_converter import DocumentConverter
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        
        # Configure pipeline for optimal OCR
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True
        pipeline_options.do_table_structure = True
        pipeline_options.ocr_options.lang = options.get("languages", ["en"])
        pipeline_options.ocr_options.use_gpu = True  # Enable GPU acceleration
        
        converter = DocumentConverter(pipeline_options=pipeline_options)
        
        # Convert document
        import time
        start_time = time.time()
        
        result = converter.convert(file_path)
        
        processing_time = time.time() - start_time
        
        # Export to requested format
        if output_format == "markdown":
            content = result.document.export_to_markdown()
        elif output_format == "text":
            content = result.document.export_to_text()
        else:
            content = result.document.export_to_dict()
        
        # Extract metadata
        metadata = {
            "pages": len(result.document.pages) if hasattr(result.document, 'pages') else 1,
            "processing_time": processing_time,
            "file_size": os.path.getsize(file_path),
            "confidence": 0.85  # Placeholder confidence score
        }
        
        logger.info("DeepSeek OCR processing completed",
                   processing_time=processing_time,
                   pages=metadata["pages"])
        
        return {
            "markdown": content,
            "metadata": metadata
        }
        
    except Exception as e:
        logger.error("DeepSeek OCR failed", error=str(e))
        raise

async def _process_with_docling_gpu(file_path: str, output_format: str, options: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process document with Docling using GPU acceleration.
    """
    logger.info("Processing with Docling GPU", file_path=file_path)
    
    try:
        from docling.document_converter import DocumentConverter
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        
        # Configure pipeline for GPU processing
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True
        pipeline_options.do_table_structure = True
        pipeline_options.ocr_options.lang = options.get("languages", ["en"])
        pipeline_options.ocr_options.use_gpu = True
        
        converter = DocumentConverter(pipeline_options=pipeline_options)
        
        # Convert document
        import time
        start_time = time.time()
        
        result = converter.convert(file_path)
        
        processing_time = time.time() - start_time
        
        # Export to requested format
        if output_format == "markdown":
            content = result.document.export_to_markdown()
        elif output_format == "text":
            content = result.document.export_to_text()
        else:
            content = result.document.export_to_dict()
        
        # Extract metadata
        metadata = {
            "pages": len(result.document.pages) if hasattr(result.document, 'pages') else 1,
            "processing_time": processing_time,
            "file_size": os.path.getsize(file_path),
            "confidence": 0.8
        }
        
        logger.info("Docling GPU processing completed",
                   processing_time=processing_time,
                   pages=metadata["pages"])
        
        return {
            "markdown": content,
            "metadata": metadata
        }
        
    except Exception as e:
        logger.error("Docling GPU processing failed", error=str(e))
        raise

@stub.function(
    gpu="A10G",
    timeout=300,
    image=image
)
def health_check() -> Dict[str, Any]:
    """
    Health check endpoint for the GPU service.
    """
    try:
        # Check if GPU is available
        import torch
        gpu_available = torch.cuda.is_available()
        gpu_count = torch.cuda.device_count() if gpu_available else 0
        
        return {
            "status": "healthy",
            "gpu_available": gpu_available,
            "gpu_count": gpu_count,
            "service": "docuflow-gpu-ocr"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "service": "docuflow-gpu-ocr"
        }

@stub.function(
    gpu="A10G",
    timeout=60,
    image=image
)
async def batch_process(batch_items: list) -> list:
    """
    Batch processing endpoint for multiple documents.
    
    Args:
        batch_items: List of processing requests
        
    Returns:
        List of processing results
    """
    logger.info("Starting batch processing", batch_size=len(batch_items))
    
    results = []
    for item in batch_items:
        try:
            result = await process_ocr.remote.aio(item)
            results.append(result)
        except Exception as e:
            results.append({
                "success": False,
                "error": str(e),
                "markdown": "",
                "metadata": {}
            })
    
    logger.info("Batch processing completed", 
                batch_size=len(batch_items),
                success_count=sum(1 for r in results if r.get("success")))
    
    return results

# Local entry point for testing
if __name__ == "__main__":
    # Test the function locally
    test_item = {
        "file_url": "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf",
        "ocr_engine": "docling",
        "output_format": "markdown"
    }
    
    with stub.run():
        result = process_ocr.local(test_item)
        print(json.dumps(result, indent=2))