"""Universal LLM module using OpenAI SDK format for flexible provider switching."""

import os
import json
from typing import Dict, Any, Optional, Type
from pydantic import BaseModel, Field
from openai import AsyncOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
import structlog

logger = structlog.get_logger(__name__)

class ExtractionResult(BaseModel):
    """Result of structured data extraction."""
    success: bool = Field(description="Whether extraction was successful")
    data: Dict[str, Any] = Field(description="Extracted structured data")
    errors: list[str] = Field(default_factory=list, description="Any errors encountered")
    confidence: float = Field(default=0.0, description="Confidence score (0-1)")
    needs_gpu_ocr: bool = Field(default=False, description="Whether GPU OCR is recommended")

class UniversalLLMExtractor:
    """Universal LLM extractor using OpenAI SDK format for Groq, Modal, and other providers."""
    
    def __init__(self, provider: str = "groq", model_name: str = "llama-3-70b-8192", dev_mode: bool = False):
        """
        Initialize the universal LLM extractor.
        
        Args:
            provider: LLM provider ('groq', 'modal_granite', 'modal_deepseek', 'ollama')
            model_name: Model name to use
            dev_mode: If True, use Ollama for local development
        """
        self.provider = provider
        self.model_name = model_name
        self.dev_mode = dev_mode
        self._setup_client()
        
    def _setup_client(self):
        """Initialize OpenAI-compatible client based on provider."""
        if self.dev_mode:
            # Use Ollama for local development
            ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
            self.client = AsyncOpenAI(
                base_url=f"{ollama_host}/v1",
                api_key="ollama",  # Ollama doesn't need real API key
                timeout=30.0,
                max_retries=2
            )
            self.model_name = "ministral-3:3b"  # Use faster model for dev
            logger.info("Ollama client initialized (dev mode)", host=ollama_host, model=self.model_name)
            
        elif self.provider == "groq":
            # Use Groq with OpenAI SDK format
            groq_api_key = os.getenv('GROQ_API_KEY')
            if not groq_api_key:
                raise ValueError("GROQ_API_KEY environment variable is required for Groq provider")
            
            self.client = AsyncOpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=groq_api_key,
                timeout=30.0,
                max_retries=2
            )
            logger.info("Groq client initialized with OpenAI SDK format", model=self.model_name)
            
        elif self.provider == "modal_granite":
            # Use Modal Granite-Docling endpoint
            modal_granite_url = os.getenv('MODAL_GRANITE_URL')
            if not modal_granite_url:
                raise ValueError("MODAL_GRANITE_URL environment variable is required for Modal Granite provider")
            
            self.client = AsyncOpenAI(
                base_url=modal_granite_url,
                api_key="EMPTY",  # Modal doesn't require API key
                timeout=60.0,  # Longer timeout for CPU processing
                max_retries=2
            )
            self.model_name = "ibm-granite/granite-docling-258M"
            logger.info("Modal Granite-Docling client initialized", url=modal_granite_url)
            
        elif self.provider == "modal_deepseek":
            # Use Modal DeepSeek-OCR endpoint
            modal_deepseek_url = os.getenv('MODAL_DEEPSEEK_URL')
            if not modal_deepseek_url:
                raise ValueError("MODAL_DEEPSEEK_URL environment variable is required for Modal DeepSeek provider")
            
            self.client = AsyncOpenAI(
                base_url=modal_deepseek_url,
                api_key="EMPTY",  # Modal doesn't require API key
                timeout=120.0,  # Longer timeout for GPU processing
                max_retries=2
            )
            self.model_name = "deepseek-ai/DeepSeek-OCR"
            logger.info("Modal DeepSeek-OCR client initialized", url=modal_deepseek_url)
            
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def create_extraction_prompt(self, schema: Dict[str, Any], content: str) -> str:
        """
        Create a prompt for structured data extraction.
        
        Args:
            schema: JSON schema defining the extraction structure
            content: Document content to extract from
            
        Returns:
            Formatted prompt string
        """
        schema_description = json.dumps(schema, indent=2)
        
        system_prompt = """You are an expert data extraction specialist. Your task is to extract structured information from documents with high accuracy and attention to detail.

IMPORTANT GUIDELINES:
1. Extract ONLY information that is explicitly present in the document
2. If information is not available, use null or appropriate default values
3. Be precise with numbers, dates, and specific details
4. For text fields, extract the exact text without interpretation
5. For numerical fields, ensure proper formatting and units
6. Convert all dates to ISO8601 format (YYYY-MM-DD)
7. If the document appears to be a login page, error page, or contains no relevant data, indicate this clearly
8. Assess the quality and completeness of the extracted data
9. Recommend GPU OCR if the document appears to be scanned, has poor quality, or contains complex layouts

SCHEMA TO EXTRACT:
{schema}

Return the extracted data in valid JSON format with a confidence score (0-1) and a recommendation for whether GPU OCR would improve results."""

        user_prompt = f"""Extract structured data from this document content and assess its quality:

{content}

Please provide:
1. The extracted data in the exact JSON format specified in the schema
2. A confidence score (0-1) based on data completeness and quality  
3. A boolean indicating if GPU OCR would improve results

Return format:
{{
  "data": {{extracted_data}},
  "confidence": 0.85,
  "needs_gpu_ocr": false,
  "quality_issues": []
}}"""

        return f"{system_prompt}\n\n{user_prompt}"

    async def extract_structured_data(self, content: str, target_schema: Dict[str, Any]) -> ExtractionResult:
        """
        Extract structured data from content using the target schema.
        
        Args:
            content: The document content to extract from
            target_schema: JSON schema defining what to extract
            
        Returns:
            ExtractionResult with structured data or errors
        """
        logger.info("Starting structured data extraction", 
                   content_length=len(content),
                   schema_keys=list(target_schema.keys()),
                   provider=self.provider,
                   model=self.model_name)
        
        try:
            # Validate inputs
            if not content or len(content.strip()) < 10:
                return ExtractionResult(
                    success=False,
                    data={},
                    errors=["Content too short for meaningful extraction"],
                    confidence=0.0,
                    needs_gpu_ocr=False
                )
            
            if not target_schema:
                return ExtractionResult(
                    success=False,
                    data={},
                    errors=["No target schema provided"],
                    confidence=0.0,
                    needs_gpu_ocr=False
                )
            
            # Create prompt
            prompt = self.create_extraction_prompt(target_schema, content[:4000])  # Limit content size
            
            # Make API call using OpenAI SDK format
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": prompt.split("\n\n")[0]},  # System prompt
                    {"role": "user", "content": prompt.split("\n\n")[1]}     # User prompt
                ],
                temperature=0.0,  # Zero creativity for deterministic output
                max_tokens=1024,  # Limit response length
                response_format={"type": "json_object"}  # Force JSON response
            )
            
            if not response or not response.choices or not response.choices[0].message.content:
                return ExtractionResult(
                    success=False,
                    data={},
                    errors=["No response from LLM"],
                    confidence=0.0,
                    needs_gpu_ocr=False
                )
            
            # Parse JSON response
            try:
                response_content = response.choices[0].message.content.strip()
                extraction_data = json.loads(response_content)
                
                # Handle different response formats
                if "data" in extraction_data:
                    extracted_data = extraction_data["data"]
                    confidence = extraction_data.get("confidence", 0.5)
                    needs_gpu_ocr = extraction_data.get("needs_gpu_ocr", False)
                    quality_issues = extraction_data.get("quality_issues", [])
                else:
                    # Fallback to direct schema extraction
                    extracted_data = extraction_data
                    confidence = 0.7  # Default confidence
                    needs_gpu_ocr = False
                    quality_issues = []
                
                # Validate against schema structure
                validation_errors = self._validate_extraction(extracted_data, target_schema)
                
                if validation_errors:
                    return ExtractionResult(
                        success=False,
                        data=extracted_data,
                        errors=validation_errors,
                        confidence=confidence * 0.3,  # Reduce confidence on validation errors
                        needs_gpu_ocr=needs_gpu_ocr
                    )
                
                logger.info("Extraction completed successfully",
                           extracted_fields=len(extracted_data),
                           confidence=confidence,
                           needs_gpu_ocr=needs_gpu_ocr,
                           quality_issues=quality_issues)
                
                return ExtractionResult(
                    success=True,
                    data=extracted_data,
                    errors=[],
                    confidence=confidence,
                    needs_gpu_ocr=needs_gpu_ocr
                )
                
            except json.JSONDecodeError as e:
                logger.error("Failed to parse LLM response as JSON", 
                           error=str(e),
                           response_preview=response_content[:200])
                
                return ExtractionResult(
                    success=False,
                    data={},
                    errors=[f"Invalid JSON response from LLM: {str(e)}"],
                    confidence=0.0,
                    needs_gpu_ocr=False
                )
                
        except Exception as e:
            logger.error("Extraction failed with exception", 
                        error=str(e),
                        error_type=type(e).__name__)
            
            return ExtractionResult(
                success=False,
                data={},
                errors=[f"Extraction failed: {str(e)}"],
                confidence=0.0,
                needs_gpu_ocr=False
            )

    def _validate_extraction(self, data: Dict[str, Any], schema: Dict[str, Any]) -> list[str]:
        """
        Validate extracted data against the target schema.
        
        Args:
            data: Extracted data
            schema: Target schema
            
        Returns:
            List of validation errors
        """
        errors = []
        
        # Check for required fields (but we're using Optional fields to prevent hallucination)
        for field_name, field_spec in schema.items():
            if field_name not in data:
                # This is OK since all fields are Optional - no error
                continue
                
            # Basic type validation (simplified)
            field_value = data[field_name]
            expected_type = field_spec if isinstance(field_spec, str) else field_spec.get('type', 'string')
            
            if expected_type == 'number' and not isinstance(field_value, (int, float)):
                if field_value is not None:  # Allow null values
                    errors.append(f"Field {field_name} should be a number, got {type(field_value).__name__}")
            elif expected_type == 'string' and not isinstance(field_value, str):
                if field_value is not None:  # Allow null values
                    errors.append(f"Field {field_name} should be a string, got {type(field_value).__name__}")
            elif expected_type == 'boolean' and not isinstance(field_value, bool):
                if field_value is not None:  # Allow null values
                    errors.append(f"Field {field_name} should be a boolean, got {type(field_value).__name__}")
        
        return errors

# Global extractor instances
_extractors = {}

async def extract_structured_data(content: str, target_schema: Dict[str, Any], 
                                provider: str = "groq", model_name: str = "llama-3-70b-8192", 
                                dev_mode: bool = False) -> ExtractionResult:
    """
    Extract structured data from content using the target schema with universal provider support.
    
    Args:
        content: The document content to extract from
        target_schema: JSON schema defining what to extract
        provider: LLM provider ('groq', 'modal_granite', 'modal_deepseek', 'ollama')
        model_name: Model name to use
        dev_mode: If True, use Ollama for local development
        
    Returns:
        ExtractionResult with structured data or errors
    """
    global _extractors
    
    # Create unique key for provider/model combination
    extractor_key = f"{provider}_{model_name}_{dev_mode}"
    
    if extractor_key not in _extractors:
        _extractors[extractor_key] = UniversalLLMExtractor(
            provider=provider, 
            model_name=model_name, 
            dev_mode=dev_mode
        )
    
    return await _extractors[extractor_key].extract_structured_data(content, target_schema)