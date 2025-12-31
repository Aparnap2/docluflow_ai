"""Engine modules for DocuFlow Headless v2."""

# Import v2 engines only if they exist
try:
    from .intelligent_ingest import IntelligentIngestionEngine
    from .engine_cpu import CPUEngine
    from .engine_gpu import GPUEngine
    from .schema_builder import SchemaBuilder
    from .output_formatter import OutputFormatter
    
    __all__ = [
        'IntelligentIngestionEngine',
        'CPUEngine',
        'GPUEngine',
        'SchemaBuilder',
        'OutputFormatter'
    ]
except ImportError:
    # Fallback to v1 engines if v2 not available
    try:
        from .ingest import determine_input_type, is_garbage
        from .ocr import extract_text_from_pdf, extract_text_from_image
        from .llm import extract_structured_data
        from .validator import validate_output
        
        __all__ = [
            'determine_input_type',
            'is_garbage',
            'extract_text_from_pdf',
            'extract_text_from_image',
            'extract_structured_data',
            'validate_output'
        ]
    except ImportError:
        # Minimal fallback
        __all__ = []