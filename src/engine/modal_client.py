"""Modal client for calling vLLM endpoints with OpenAI SDK format."""

import os
import tempfile
import requests
from typing import Dict, Any, Optional
from openai import AsyncOpenAI
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger(__name__)

class ModalClient:
    """Client for calling Modal vLLM endpoints with OpenAI SDK format."""
    
    def __init__(self, endpoint_url: str, model_name: str, timeout: int = 120):
        """
        Initialize Modal client.
        
        Args:
            endpoint_url: Modal endpoint URL
            model_name: Model name to use
            timeout: Request timeout in seconds
        """
        self.endpoint_url = endpoint_url.rstrip('/')  # Remove trailing slash
        self.model_name = model_name
        self.timeout = timeout
        
        # Initialize OpenAI-compatible client
        self.client = AsyncOpenAI(
            base_url=f"{self.endpoint_url}/v1",
            api_key="EMPTY",  # Modal doesn't require API key
            timeout=timeout,
            max_retries=2
        )
        
        logger.info("Modal client initialized", 
                   endpoint=endpoint_url, 
                   model=model_name,
                   timeout=timeout)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def process_document(self, file_path: str, prompt: str) -> str:
        """
        Process document with Modal vLLM endpoint.
        
        Args:
            file_path: Path to the document file
            prompt: Processing prompt
            
        Returns:
            Extracted text content
        """
        try:
            # Read file content
            with open(file_path, 'rb') as f:
                file_content = f.read()
            
            # For vision models (DeepSeek-OCR), we need to encode image
            if "deepseek" in self.model_name.lower() and self._is_image_file(file_path):
                return await self._process_with_vision(file_path, prompt, file_content)
            else:
                return await self._process_with_text(prompt)
                
        except Exception as e:
            logger.error("Modal processing failed", 
                        error=str(e), 
                        file_path=file_path,
                        model=self.model_name)
            raise

    def _is_image_file(self, file_path: str) -> bool:
        """Check if file is an image."""
        image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp'}
        return any(file_path.lower().endswith(ext) for ext in image_extensions)

    async def _process_with_vision(self, file_path: str, prompt: str, file_content: bytes) -> str:
        """Process image with vision model."""
        import base64
        from PIL import Image
        
        try:
            # Convert image to base64
            image = Image.open(file_path)
            
            # Resize if too large (Modal has limits)
            max_size = (1024, 1024)
            if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
                image.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Save to bytes
            import io
            buffer = io.BytesIO()
            image.save(buffer, format='PNG')
            image_base64 = base64.b64encode(buffer.getvalue()).decode()
            
            # Create vision prompt
            vision_prompt = f"""{prompt}

Please analyze this image and extract any text, tables, or structured information you can find.

Image: data:image/png;base64,{image_base64}"""
            
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "user", "content": vision_prompt}
                ],
                temperature=0.0,
                max_tokens=2048
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error("Vision processing failed", error=str(e), file_path=file_path)
            # Fallback to text-only processing
            return await self._process_with_text(prompt)

    async def _process_with_text(self, prompt: str) -> str:
        """Process with text-only model."""
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_tokens=2048
        )
        
        return response.choices[0].message.content

    async def health_check(self) -> Dict[str, Any]:
        """Check if the Modal endpoint is healthy."""
        try:
            # Try to get model info
            response = await self.client.models.list()
            return {
                "status": "healthy",
                "endpoint": self.endpoint_url,
                "model": self.model_name,
                "available_models": [model.id for model in response.data] if response.data else []
            }
        except Exception as e:
            logger.error("Health check failed", error=str(e), endpoint=self.endpoint_url)
            return {
                "status": "unhealthy",
                "error": str(e),
                "endpoint": self.endpoint_url,
                "model": self.model_name
            }

class ModalCPUClient(ModalClient):
    """Specialized client for Granite-Docling CPU endpoint."""
    
    def __init__(self, timeout: int = 60):
        """Initialize CPU client with Granite-Docling endpoint."""
        endpoint_url = os.getenv('MODAL_GRANITE_URL')
        if not endpoint_url:
            raise ValueError("MODAL_GRANITE_URL environment variable is required")
        
        super().__init__(endpoint_url, "ibm-granite/granite-docling-258M", timeout)

class ModalGPUClient(ModalClient):
    """Specialized client for DeepSeek-OCR GPU endpoint."""
    
    def __init__(self, timeout: int = 120):
        """Initialize GPU client with DeepSeek-OCR endpoint."""
        endpoint_url = os.getenv('MODAL_DEEPSEEK_URL')
        if not endpoint_url:
            raise ValueError("MODAL_DEEPSEEK_URL environment variable is required")
        
        super().__init__(endpoint_url, "deepseek-ai/DeepSeek-OCR", timeout)

# Convenience functions for easy integration
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
async def process_with_granite_docling(file_path: str, prompt: str) -> str:
    """Process document with Granite-Docling CPU model."""
    client = ModalCPUClient()
    return await client.process_document(file_path, prompt)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
async def process_with_deepseek_ocr(file_path: str, prompt: str) -> str:
    """Process document with DeepSeek-OCR GPU model."""
    client = ModalGPUClient()
    return await client.process_document(file_path, prompt)

async def check_modal_endpoints() -> Dict[str, Any]:
    """Check health of all Modal endpoints."""
    results = {}
    
    # Check Granite-Docling CPU endpoint
    try:
        cpu_client = ModalCPUClient()
        results['granite_docling'] = await cpu_client.health_check()
    except Exception as e:
        results['granite_docling'] = {
            "status": "not_configured",
            "error": str(e)
        }
    
    # Check DeepSeek-OCR GPU endpoint
    try:
        gpu_client = ModalGPUClient()
        results['deepseek_ocr'] = await gpu_client.health_check()
    except Exception as e:
        results['deepseek_ocr'] = {
            "status": "not_configured",
            "error": str(e)
        }
    
    return results