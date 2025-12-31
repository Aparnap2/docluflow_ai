"""Data models for DocuFlow Headless v2."""

from typing import List, Dict, Any, Optional, Literal, Type
from pydantic import BaseModel, Field, validator, create_model
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)

class FileInput(BaseModel):
    """Input file specification."""
    url: Optional[str] = Field(None, description="Public URL of the file")
    base64: Optional[str] = Field(None, description="Base64 encoded file data")
    filename: Optional[str] = Field(None, description="Original filename")
    
    @validator('url', 'base64')
    def validate_at_least_one_source(cls, v, values):
        """Ensure at least one source is provided."""
        if not v and not values.get('base64') and not values.get('url'):
            raise ValueError("Either url or base64 must be provided")
        return v

class ProcessingInput(BaseModel):
    """Main input schema for DocuFlow Headless v2."""
    files: List[FileInput] = Field(..., description="Files to process", min_items=1, max_items=10)
    filter_keywords: List[str] = Field(default_factory=list, description="Keywords to filter relevant documents")
    schema: Dict[str, Any] = Field(..., description="Target JSON schema for extraction")
    use_gpu_ocr: bool = Field(default=False, description="Force GPU OCR for all files")
    proxy_configuration: Dict[str, Any] = Field(default_factory=lambda: {"useApifyProxy": True})
    max_retries: int = Field(default=3, ge=1, le=5, description="Maximum retry attempts")
    timeout_seconds: int = Field(default=120, ge=30, le=300, description="Processing timeout")
    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0, description="Confidence threshold for GPU fallback")
    output_format: Literal["json", "n8n_compatible"] = Field(default="n8n_compatible", description="Output format")
    
    @validator('files')
    def validate_files(cls, v):
        """Validate file inputs."""
        if not v:
            raise ValueError("At least one file must be provided")
        return v
    
    @validator('schema')
    def validate_schema(cls, v):
        """Ensure schema is not empty."""
        if not v or not isinstance(v, dict):
            raise ValueError("Schema must be a non-empty dictionary")
        return v

class FileProcessingResult(BaseModel):
    """Result of processing a single file."""
    file_index: int = Field(..., description="Index of the file in the input array")
    filename: Optional[str] = Field(None, description="Original filename")
    status: Literal["success", "skipped", "failed"] = Field(..., description="Processing status")
    error: Optional[str] = Field(None, description="Error message if failed")
    skip_reason: Optional[str] = Field(None, description="Reason for skipping")
    
    # Extraction results
    extracted_data: Optional[Dict[str, Any]] = Field(None, description="Extracted structured data")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="Extraction confidence score")
    
    # Processing metadata
    processing_method: Optional[Literal["cpu_fast", "gpu_vision"]] = Field(None, description="Processing method used")
    processing_time_seconds: float = Field(0.0, ge=0.0, description="Processing time in seconds")
    file_size_bytes: Optional[int] = Field(None, description="Original file size in bytes")
    compressed_size_bytes: Optional[int] = Field(None, description="Compressed file size in bytes")
    
    # n8n/Google Drive routing metadata
    suggested_filename: Optional[str] = Field(None, description="Suggested filename for saving")
    routing_folder: Optional[str] = Field(None, description="Suggested folder path for routing")
    
    # AGB filtering metadata
    filter_keywords_found: List[str] = Field(default_factory=list, description="Filter keywords found in document")
    text_density: Optional[float] = Field(None, description="Text density (chars per page)")
    page_count: Optional[int] = Field(None, description="Number of pages in document")

def create_dynamic_schema(user_schema: Dict[str, Any]) -> Type[BaseModel]:
    """
    Create a dynamic Pydantic model from user-provided JSON schema.
    All fields are Optional to prevent hallucination.
    
    Args:
        user_schema: JSON schema defining the structure
        
    Returns:
        Pydantic model class
    """
    try:
        fields = {}
        
        # Handle different schema formats
        if "properties" in user_schema:
            properties = user_schema["properties"]
        elif isinstance(user_schema, dict) and user_schema:
            # Simple dict format: {"field_name": "field_type"}
            properties = user_schema
        else:
            logger.warning("Invalid schema format, using empty model")
            return create_model("DynamicSchema", __base__=BaseModel)
        
        # Convert each property to Optional field
        for field_name, field_spec in properties.items():
            if isinstance(field_spec, dict):
                field_type = field_spec.get("type", "string")
                field_description = field_spec.get("description", "")
            elif isinstance(field_spec, str):
                # Simple format: "field_name": "string"
                field_type = field_spec
                field_description = ""
            else:
                field_type = "string"
                field_description = ""
            
            # Map JSON types to Python types
            type_mapping = {
                "string": str,
                "number": float,
                "integer": int,
                "boolean": bool,
                "array": List[str],
                "object": Dict[str, Any]
            }
            
            python_type = type_mapping.get(field_type, str)
            
            # Make all fields Optional to prevent hallucination
            from typing import Optional
            fields[field_name] = (Optional[python_type], Field(None, description=field_description))
        
        # Create the dynamic model
        DynamicModel = create_model("DynamicSchema", __base__=BaseModel, **fields)
        
        logger.info("Created dynamic schema model", field_count=len(fields))
        return DynamicModel
        
    except Exception as e:
        logger.error("Failed to create dynamic schema", error=str(e))
        # Return empty model as fallback
        return create_model("DynamicSchema", __base__=BaseModel)

def format_n8n_output(extracted_data: Dict[str, Any], filename: str, processing_method: str) -> Dict[str, Any]:
    """
    Format output for n8n compatibility with Google Drive routing.
    
    Args:
        extracted_data: Extracted structured data
        filename: Original filename
        processing_method: CPU or GPU processing method
        
    Returns:
        n8n-compatible output with routing information
    """
    try:
        # Extract date and vendor for routing
        date_str = extracted_data.get("date", "")
        vendor = extracted_data.get("vendor", "unknown")
        doc_type = extracted_data.get("type", "document")
        
        # Format date for filename and folder
        if date_str:
            try:
                # Try to parse and format date
                if isinstance(date_str, str):
                    # Handle various date formats
                    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"]:
                        try:
                            parsed_date = datetime.strptime(date_str.split("T")[0], fmt.split("T")[0])
                            date_formatted = parsed_date.strftime("%Y-%m-%d")
                            year = parsed_date.strftime("%Y")
                            month = parsed_date.strftime("%m")
                            break
                        except:
                            continue
                    else:
                        # Fallback to original date
                        date_formatted = date_str.replace("/", "-")
                        year = "unknown"
                        month = "unknown"
                else:
                    date_formatted = str(date_str)
                    year = "unknown"
                    month = "unknown"
            except:
                date_formatted = str(date_str)
                year = "unknown"
                month = "unknown"
        else:
            date_formatted = "unknown-date"
            year = "unknown"
            month = "unknown"
        
        # Create suggested filename
        suggested_filename = f"{date_formatted}_{vendor}_{doc_type}.pdf"
        
        # Create routing folder path
        routing_folder = f"/{year}/{month}/{vendor}"
        
        return {
            "main_data": extracted_data,
            "_meta": {
                "processed_by": processing_method.lower(),
                "suggested_filename": suggested_filename,
                "routing_folder": routing_folder,
                "original_filename": filename
            }
        }
        
    except Exception as e:
        logger.error("Failed to format n8n output", error=str(e))
        return {
            "main_data": extracted_data,
            "_meta": {
                "processed_by": processing_method.lower(),
                "suggested_filename": filename,
                "routing_folder": "/unknown",
                "original_filename": filename,
                "error": str(e)
            }
        }

class ProcessingOutput(BaseModel):
    """Main output schema for DocuFlow Headless v2."""
    success: bool = Field(..., description="Overall processing success")
    results: List[FileProcessingResult] = Field(..., description="Results for each processed file")
    
    # Summary statistics
    total_files: int = Field(..., description="Total number of files processed")
    successful_files: int = Field(..., description="Number of successfully processed files")
    skipped_files: int = Field(..., description="Number of skipped files")
    failed_files: int = Field(..., description="Number of failed files")
    
    # Processing metadata
    processing_start_time: datetime = Field(..., description="Processing start time")
    processing_end_time: datetime = Field(..., description="Processing end time")
    total_processing_time_seconds: float = Field(..., description="Total processing time")
    
    # n8n-compatible output
    n8n_output: Optional[Dict[str, Any]] = Field(None, description="n8n-compatible formatted output")
    
    # Errors and warnings
    errors: List[str] = Field(default_factory=list, description="Global errors")
    warnings: List[str] = Field(default_factory=list, description="Global warnings")

class RoutingDecision(BaseModel):
    """Routing decision for processing method."""
    method: Literal["cpu_fast", "gpu_vision"] = Field(..., description="Selected processing method")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in routing decision")
    reasoning: str = Field(..., description="Reasoning for routing decision")
    text_density: float = Field(..., ge=0.0, description="Calculated text density")
    has_text_layer: bool = Field(..., description="Whether document has text layer")
    page_count: int = Field(..., description="Number of pages analyzed")

class CompressionResult(BaseModel):
    """Result of file compression."""
    original_size_bytes: int = Field(..., description="Original file size")
    compressed_size_bytes: int = Field(..., description="Compressed file size")
    compression_ratio: float = Field(..., description="Compression ratio")
    method: Literal["ghostscript", "pillow", "none"] = Field(..., description="Compression method used")
    success: bool = Field(..., description="Whether compression was successful")
    error: Optional[str] = Field(None, description="Error if compression failed")

class AGBFilterResult(BaseModel):
    """Result of AGB (Allgemeine Geschäftsbedingungen) filtering."""
    should_process: bool = Field(..., description="Whether file should be processed")
    keywords_found: List[str] = Field(default_factory=list, description="Filter keywords found")
    first_page_text: str = Field("", description="Text from first page")
    second_page_text: str = Field("", description="Text from second page")
    reasoning: str = Field(..., description="Reasoning for filter decision")