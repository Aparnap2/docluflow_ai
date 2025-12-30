"""LLM module for structured data extraction using Groq and local granite-docling model."""

import os
import json
from typing import Dict, Any, Optional, Type
from pydantic import BaseModel, Field
from langchain_groq import ChatGroq
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

class LLMExtractor:
    """LLM-based structured data extractor using Groq for general extraction and local models for documents."""
    
    def __init__(self, model_name: str = "ministral-3:3b", dev_mode: bool = False):
        """
        Initialize the LLM extractor.
        
        Args:
            model_name: Groq model to use for extraction
            dev_mode: If True, use Ollama for local development
        """
        self.model_name = model_name
        self.dev_mode = dev_mode
        self._setup_llm()
        
    def _setup_llm(self):
        """Initialize LLM based on dev mode setting."""
        if self.dev_mode:
            # Use Ollama for local development
            ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
            
            try:
                from langchain_openai import ChatOpenAI
                self.llm = ChatOpenAI(
                    base_url=f"{ollama_host}/v1",
                    api_key="ollama",  # Ollama doesn't need real API key
                    model="ministral-3:3b",
                    temperature=0.1,
                    max_tokens=4096,
                    timeout=30,
                    max_retries=2,
                )
                logger.info("Ollama LLM initialized (dev mode)", model="ministral-3:3b", host=ollama_host)
            except Exception as e:
                logger.error("Ollama initialization failed in dev mode", error=str(e))
                raise ValueError(f"Ollama not available for dev mode: {str(e)}")
        else:
            # Use Groq for production
            groq_api_key = os.getenv('GROQ_API_KEY')
            if not groq_api_key:
                raise ValueError("GROQ_API_KEY environment variable is required for production")
            
            self.llm = ChatGroq(
                model=self.model_name,
                groq_api_key=groq_api_key,
                temperature=0.1,  # Low temperature for consistent extraction
                max_tokens=4096,
                timeout=30,
                max_retries=2,
            )
            logger.info("Groq LLM initialized", model=self.model_name)

    def create_extraction_prompt(self, schema: Dict[str, Any]) -> ChatPromptTemplate:
        """
        Create a prompt template for structured extraction.
        
        Args:
            schema: JSON schema defining the extraction structure
            
        Returns:
            Configured prompt template
        """
        schema_description = json.dumps(schema, indent=2)
        
        system_template = """You are an expert data extraction specialist. Your task is to extract structured information from documents with high accuracy and attention to detail.

IMPORTANT GUIDELINES:
1. Extract ONLY information that is explicitly present in the document
2. If information is not available, use null or appropriate default values
3. Be precise with numbers, dates, and specific details
4. For text fields, extract the exact text without interpretation
5. For numerical fields, ensure proper formatting and units
6. If the document appears to be a login page, error page, or contains no relevant data, indicate this clearly
7. Assess the quality and completeness of the extracted data
8. Recommend GPU OCR if the document appears to be scanned, has poor quality, or contains complex layouts

SCHEMA TO EXTRACT:
{schema}

Return the extracted data in valid JSON format with a confidence score (0-1) and a recommendation for whether GPU OCR would improve results."""

        human_template = """Extract structured data from this document content and assess its quality:

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

        return ChatPromptTemplate.from_messages([
            ("system", system_template),
            ("human", human_template)
        ])

    def create_document_analysis_prompt(self) -> ChatPromptTemplate:
        """
        Create a prompt for analyzing document quality and OCR needs.
        
        Returns:
            Configured prompt template for document analysis
        """
        system_template = """You are a document analysis expert. Analyze the provided document content and determine:

1. Content quality and readability
2. Whether the document appears to be scanned vs digitally created
3. Presence of complex layouts, tables, or images
4. OCR quality and completeness
5. Recommendation for GPU OCR processing

Focus on identifying documents that would benefit from advanced GPU-based OCR processing."""

        human_template = """Analyze this document content and assess whether GPU OCR processing would improve extraction quality:

{content}

Consider:
- Is this a scanned document or digitally created?
- Are there complex layouts, tables, or embedded images?
- Is the text clear and well-formatted?
- Are there any OCR errors or missing content?
- Would advanced OCR processing improve results?

Return format:
{{
  "is_scanned": false,
  "has_complex_layout": false,
  "ocr_quality": "good|fair|poor",
  "recommend_gpu_ocr": false,
  "reasoning": "brief explanation"
}}"""

        return ChatPromptTemplate.from_messages([
            ("system", system_template),
            ("human", human_template)
        ])

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
                   schema_keys=list(target_schema.keys()))
        
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
            
            # First, analyze if GPU OCR is needed
            analysis_prompt = self.create_document_analysis_prompt()
            analysis_response = await self.llm.ainvoke(
                analysis_prompt.format_messages(content=content[:10000])
            )
            
            try:
                analysis_result = json.loads(analysis_response.content.strip())
                needs_gpu_ocr = analysis_result.get("recommend_gpu_ocr", False)
                ocr_quality = analysis_result.get("ocr_quality", "unknown")
                
                logger.info("Document analysis completed",
                           needs_gpu_ocr=needs_gpu_ocr,
                           ocr_quality=ocr_quality)
                
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Failed to parse document analysis", error=str(e))
                needs_gpu_ocr = False
                ocr_quality = "unknown"
            
            # Create extraction prompt
            prompt = self.create_extraction_prompt(target_schema)
            
            # Format the prompt with content and schema
            formatted_prompt = prompt.format_messages(
                content=content[:50000],  # Limit content size to avoid token limits
                schema=json.dumps(target_schema, indent=2)
            )
            
            logger.debug("Sending extraction request to Groq", 
                        model=self.model_name,
                        content_length=len(content),
                        needs_gpu_ocr=needs_gpu_ocr)
            
            # Get LLM response
            response = await self.llm.ainvoke(formatted_prompt)
            
            if not response or not response.content:
                return ExtractionResult(
                    success=False,
                    data={},
                    errors=["No response from LLM"],
                    confidence=0.0,
                    needs_gpu_ocr=needs_gpu_ocr
                )
            
            # Parse JSON response
            try:
                response_content = response.content.strip()
                
                # Handle markdown code block wrapping
                if response_content.startswith('```json'):
                    response_content = response_content[7:]  # Remove ```json
                if response_content.endswith('```'):
                    response_content = response_content[:-3]  # Remove ```
                
                extraction_data = json.loads(response_content.strip())
                
                # Handle different response formats
                if "data" in extraction_data:
                    extracted_data = extraction_data["data"]
                    confidence = extraction_data.get("confidence", 0.5)
                    response_needs_gpu = extraction_data.get("needs_gpu_ocr", False)
                    quality_issues = extraction_data.get("quality_issues", [])
                else:
                    # Fallback to direct schema extraction
                    extracted_data = extraction_data
                    confidence = 0.7  # Default confidence
                    response_needs_gpu = False
                    quality_issues = []
                
                # Override with document analysis if it's more conservative
                if needs_gpu_ocr and not response_needs_gpu:
                    response_needs_gpu = True
                    quality_issues.append("Document analysis recommends GPU OCR")
                
                # Validate against schema structure
                validation_errors = self._validate_extraction(extracted_data, target_schema)
                
                if validation_errors:
                    return ExtractionResult(
                        success=False,
                        data=extracted_data,
                        errors=validation_errors,
                        confidence=confidence * 0.3,  # Reduce confidence on validation errors
                        needs_gpu_ocr=response_needs_gpu
                    )
                
                # Calculate confidence based on data completeness
                if confidence < 0.5 or response_needs_gpu or ocr_quality in ["fair", "poor"]:
                    # Low confidence or quality issues - recommend GPU OCR
                    final_confidence = max(0.1, confidence * 0.7)
                    final_needs_gpu = True
                else:
                    final_confidence = confidence
                    final_needs_gpu = response_needs_gpu
                
                logger.info("Extraction completed successfully",
                           extracted_fields=len(extracted_data),
                           confidence=final_confidence,
                           needs_gpu_ocr=final_needs_gpu,
                           quality_issues=quality_issues)
                
                return ExtractionResult(
                    success=True,
                    data=extracted_data,
                    errors=[],
                    confidence=final_confidence,
                    needs_gpu_ocr=final_needs_gpu
                )
                
            except json.JSONDecodeError as e:
                logger.error("Failed to parse LLM response as JSON", 
                           error=str(e),
                           response_preview=response.content[:200])
                
                return ExtractionResult(
                    success=False,
                    data={},
                    errors=[f"Invalid JSON response from LLM: {str(e)}"],
                    confidence=0.0,
                    needs_gpu_ocr=needs_gpu_ocr
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
        
        # Check for required fields
        for field_name, field_spec in schema.items():
            if field_name not in data:
                errors.append(f"Missing required field: {field_name}")
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

# Global extractor instance
_extractor = None

async def extract_structured_data(content: str, target_schema: Dict[str, Any], dev_mode: bool = False) -> ExtractionResult:
    """
    Extract structured data from content using the target schema.
    
    Args:
        content: The document content to extract from
        target_schema: JSON schema defining what to extract
        dev_mode: If True, use Ollama for local development
        
    Returns:
        ExtractionResult with structured data or errors
    """
    global _extractor
    
    if _extractor is None or _extractor.dev_mode != dev_mode:
        _extractor = LLMExtractor(dev_mode=dev_mode)
    
    return await _extractor.extract_structured_data(content, target_schema)