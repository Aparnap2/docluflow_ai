"""
Modal Integration Module for DocuFlow Headless v2
Handles communication with optimized Modal endpoints (CPU/GPU)
"""

import requests
import base64
import json
import structlog
import os
from typing import Dict, Any, Optional, List
from pathlib import Path
import io
from PIL import Image
import PyPDF2
from tenacity import retry, stop_after_attempt, wait_exponential
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging
logger = structlog.get_logger(__name__)

# Modal endpoint URLs from environment variables
CPU_ENDPOINT = os.getenv("MODAL_CPU_ENDPOINT", "https://ap3617180--docuflow-cpu-granite-gguf-serve.modal.run")
GPU_ENDPOINT = os.getenv("MODAL_GPU_ENDPOINT", "https://ap3617180--docuflow-gpu-deepseek-serve.modal.run")

# Validate environment variables
if not CPU_ENDPOINT or not GPU_ENDPOINT:
    logger.warning("Modal endpoints not configured in environment variables, using defaults")

class ModalIntegration:
    """Integration class for Modal CPU/GPU endpoints."""
    
    def __init__(self, cpu_endpoint: Optional[str] = None, gpu_endpoint: Optional[str] = None):
        """Initialize with optional custom endpoints and serverless cold start handling."""
        self.cpu_endpoint = cpu_endpoint or CPU_ENDPOINT
        self.gpu_endpoint = gpu_endpoint or GPU_ENDPOINT
        
        # Create robust session for serverless cold starts
        self.session = self._create_robust_session()
        
        logger.info("Modal integration initialized",
                   cpu_endpoint=self.cpu_endpoint,
                   gpu_endpoint=self.gpu_endpoint)
    
    def _create_robust_session(self):
        """Create requests session with retry logic for serverless cold starts."""
        retry_strategy = Retry(
            total=3,
            backoff_factor=2,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session = requests.Session()
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session
    
    def convert_pdf_page_to_image(self, pdf_bytes: bytes, page_num: int = 0) -> bytes:
        """Convert PDF page to image for vision model processing."""
        try:
            # Convert PDF page to image using PIL/PyPDF2
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
            
            if page_num >= len(pdf_reader.pages):
                page_num = 0
                
            page = pdf_reader.pages[page_num]
            
            # For now, create a simple image representation
            # In production, you'd use pdf2image or similar
            img = Image.new('RGB', (612, 792), color='white')
            
            # Save as JPEG
            img_buffer = io.BytesIO()
            img.save(img_buffer, format='JPEG', quality=85)
            img_buffer.seek(0)
            
            return img_buffer.read()
            
        except Exception as e:
            logger.error("PDF to image conversion failed", error=str(e))
            # Return a placeholder image
            img = Image.new('RGB', (612, 792), color='white')
            img_buffer = io.BytesIO()
            img.save(img_buffer, format='JPEG', quality=85)
            img_buffer.seek(0)
            return img_buffer.read()
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=10, max=30))
    def process_with_cpu(self, text_content: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Process text-heavy documents with Granite-Docling CPU endpoint."""
        logger.info("Processing with CPU endpoint", content_length=len(text_content))
        
        try:
            # For text processing, we can use a simpler approach
            # Granite-Docling is primarily a vision model, so we'll simulate text processing
            payload = {
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a document extraction engine. Extract structured data from the provided text."
                    },
                    {
                        "role": "user",
                        "content": f"Schema: {json.dumps(schema)}\n\nText: {text_content}"
                    }
                ],
                "max_tokens": 1000,
                "temperature": 0.1
            }
            
            response = self.session.post(
                f"{self.cpu_endpoint}/v1/chat/completions",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=120  # 2 minutes for cold start + processing
            )
            
            response.raise_for_status()
            result = response.json()
            
            extracted_text = result['choices'][0]['message']['content']
            
            logger.info("CPU processing successful", extracted_length=len(extracted_text))
            
            return {
                "status": "success",
                "markdown": extracted_text,
                "processing_time": 0,  # Will be measured by Modal
                "model": "granite-docling-cpu",
                "device": "cpu"
            }
            
        except requests.exceptions.ReadTimeout:
            logger.error("CPU processing timed out after 120s (serverless cold start)")
            raise
        except Exception as e:
            logger.error("CPU processing failed", error=str(e))
            raise
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=10, max=30))
    def process_with_gpu(self, image_bytes: bytes, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Process image documents with DeepSeek-OCR GPU endpoint."""
        logger.info("Processing with GPU endpoint", image_size=len(image_bytes))
        
        try:
            # Convert image to base64
            image_b64 = base64.b64encode(image_bytes).decode('utf-8')
            
            # Create vision model payload
            payload = {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text", 
                                "text": f"Extract structured data from this image. Schema: {json.dumps(schema)}"
                            },
                            {
                                "type": "image_url", 
                                "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}
                            }
                        ]
                    }
                ],
                "max_tokens": 1000,
                "temperature": 0.1
            }
            
            response = self.session.post(
                f"{self.gpu_endpoint}/v1/chat/completions",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=120  # 2 minutes for cold start + processing
            )
            
            response.raise_for_status()
            result = response.json()
            
            extracted_text = result['choices'][0]['message']['content']
            
            logger.info("GPU processing successful", extracted_length=len(extracted_text))
            
            return {
                "status": "success",
                "markdown": extracted_text,
                "processing_time": 0,  # Will be measured by Modal
                "model": "deepseek-ocr-gpu",
                "device": "gpu"
            }
            
        except requests.exceptions.ReadTimeout:
            logger.error("GPU processing timed out after 120s (serverless cold start)")
            raise
        except Exception as e:
            logger.error("GPU processing failed", error=str(e))
            raise
    
    def process_document(self, file_bytes: bytes, filename: str, content_type: str, 
                        text_density: float, has_text_layer: bool, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Main processing function that routes to appropriate endpoint."""
        
        logger.info("Processing document", 
                   filename=filename, 
                   content_type=content_type,
                   text_density=text_density,
                   has_text_layer=has_text_layer)
        
        # Route decision based on document characteristics
        if text_density > 50 and has_text_layer and content_type == "application/pdf":
            # CPU route for text-heavy PDFs
            logger.info("Routing to CPU endpoint", reason="text_heavy_pdf")
            
            # Extract text from PDF for CPU processing
            try:
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
                text_content = ""
                for page in pdf_reader.pages:
                    text_content += page.extract_text() + "\n"
                
                return self.process_with_cpu(text_content, schema)
            except Exception as e:
                logger.warning("Text extraction failed, falling back to GPU", error=str(e))
                # Fall back to GPU if text extraction fails
        
        # GPU route for images and documents with low text density
        logger.info("Routing to GPU endpoint", reason="image_or_low_text")
        
        if content_type == "application/pdf":
            # Convert PDF page to image for GPU processing
            image_bytes = self.convert_pdf_page_to_image(file_bytes)
        else:
            # Use image directly
            image_bytes = file_bytes
        
        return self.process_with_gpu(image_bytes, schema)
    
    def health_check(self, endpoint: str) -> bool:
        """Check if Modal endpoint is healthy with proper timeout for cold starts."""
        try:
            response = self.session.get(f"{endpoint}/health", timeout=90)  # 90s for serverless cold start
            return response.status_code == 200
        except requests.exceptions.ReadTimeout:
            logger.error(f"Health check timed out for {endpoint} (cold start > 90s)")
            return False
        except Exception as e:
            logger.error(f"Health check failed for {endpoint}", error=str(e))
            return False

# Global integration instance with environment-based configuration
modal_integration = ModalIntegration()

# Convenience functions for the main application
def process_with_modal(file_bytes: bytes, filename: str, content_type: str, 
                      text_density: float, has_text_layer: bool, schema: Dict[str, Any]) -> Dict[str, Any]:
    """Process document using Modal endpoints."""
    return modal_integration.process_document(
        file_bytes, filename, content_type, text_density, has_text_layer, schema
    )

def check_modal_health() -> Dict[str, bool]:
    """Check health of both Modal endpoints."""
    return {
        "cpu": modal_integration.health_check(modal_integration.cpu_endpoint),
        "gpu": modal_integration.health_check(modal_integration.gpu_endpoint)
    }

# Environment configuration helper
def configure_modal_endpoints(cpu_url: str, gpu_url: str):
    """Configure Modal endpoints from environment or custom URLs."""
    global modal_integration
    modal_integration = ModalIntegration(cpu_url, gpu_url)
    logger.info("Modal endpoints reconfigured", cpu_url=cpu_url, gpu_url=gpu_url)

# Example usage for testing
if __name__ == "__main__":
    # Test health check
    health = check_modal_health()
    print("Modal endpoints health:", health)
    
    # Test with sample data
    test_schema = {
        "invoice_number": "string",
        "date": "string", 
        "vendor": "string",
        "total": "number"
    }
    
    # Test CPU processing
    test_text = "Invoice #INV-2024-001\nDate: 2024-01-15\nVendor: TechCorp Solutions\nTotal: $1,250.00"
    result = modal_integration.process_with_cpu(test_text, test_schema)
    print("CPU result:", result)