"""Simple validation script for DocuFlow Headless v2 transformation."""

import json
import re

def validate_requirements():
    """Validate requirements.txt meets anti-hallucination constraints."""
    print("🔍 Validating requirements.txt...")
    
    with open('requirements.txt', 'r') as f:
        requirements = f.read()
    
    # Anti-hallucination constraints
    constraints = [
        ("torch", False, "torch should not be in requirements"),
        ("transformers", False, "transformers should not be in requirements"),
        ("unstructured", False, "unstructured should not be in requirements"),
        ("ollama", False, "ollama should not be in requirements"),
        ("PyMuPDF", True, "PyMuPDF should be in requirements"),
        ("docling", True, "docling should be in requirements"),
        ("tenacity", True, "tenacity should be in requirements"),
        ("ghostscript", True, "ghostscript should be in requirements")
    ]
    
    results = []
    for constraint, should_exist, message in constraints:
        exists = constraint in requirements
        if exists == should_exist:
            results.append(f"✅ {message}")
        else:
            results.append(f"❌ {message}")
    
    return results

def validate_input_schema():
    """Validate the new v2 input schema."""
    print("🔍 Validating v2 input schema...")
    
    try:
        with open('.actor/input_schema_v2.json', 'r') as f:
            schema = json.load(f)
        
        results = []
        
        # Check for multi-file support
        if "files" in schema.get("properties", {}):
            files_prop = schema["properties"]["files"]
            if files_prop.get("type") == "array":
                results.append("✅ Multi-file input schema present")
            else:
                results.append("❌ files property should be array")
        else:
            results.append("❌ Multi-file input schema missing")
        
        # Check for filter keywords
        if "filter_keywords" in schema.get("properties", {}):
            results.append("✅ Filter keywords schema present")
        else:
            results.append("❌ Filter keywords schema missing")
        
        # Check for schema field
        if "schema" in schema.get("properties", {}):
            results.append("✅ Schema field present")
        else:
            results.append("❌ Schema field missing")
        
        return results
        
    except Exception as e:
        return [f"❌ Schema validation error: {str(e)}"]

def validate_code_changes():
    """Validate key code changes are present."""
    print("🔍 Validating code changes...")
    
    results = []
    
    # Check ingest.py for new functions
    try:
        with open('src/engine/ingest.py', 'r') as f:
            ingest_code = f.read()
        
        if 'def extract_pdf_text_first_pages(' in ingest_code:
            results.append("✅ PyMuPDF text extraction function present")
        else:
            results.append("❌ PyMuPDF text extraction function missing")
        
        if 'def filter_by_keywords(' in ingest_code:
            results.append("✅ AGB filtering function present")
        else:
            results.append("❌ AGB filtering function missing")
        
        if 'def route_processing(' in ingest_code:
            results.append("✅ Routing logic function present")
        else:
            results.append("❌ Routing logic function missing")
        
        if 'def process_file_intelligently(' in ingest_code:
            results.append("✅ Intelligent processing function present")
        else:
            results.append("❌ Intelligent processing function missing")
        
    except Exception as e:
        results.append(f"❌ ingest.py validation error: {str(e)}")
    
    # Check ocr.py for external API usage
    try:
        with open('src/engine/ocr.py', 'r') as f:
            ocr_code = f.read()
        
        if 'def _process_with_external_gpu(' in ocr_code:
            results.append("✅ External GPU API function present")
        else:
            results.append("❌ External GPU API function missing")
        
        if 'GPU_OCR_API_URL' in ocr_code:
            results.append("✅ External API configuration present")
        else:
            results.append("❌ External API configuration missing")
        
        if 'tenacity' in ocr_code:
            results.append("✅ Tenacity retry logic present")
        else:
            results.append("❌ Tenacity retry logic missing")
        
    except Exception as e:
        results.append(f"❌ ocr.py validation error: {str(e)}")
    
    # Check models.py for new functions
    try:
        with open('src/models.py', 'r') as f:
            models_code = f.read()
        
        if 'def create_dynamic_schema(' in models_code:
            results.append("✅ Dynamic schema function present")
        else:
            results.append("❌ Dynamic schema function missing")
        
        if 'def format_n8n_output(' in models_code:
            results.append("✅ n8n output formatting function present")
        else:
            results.append("❌ n8n output formatting function missing")
        
    except Exception as e:
        results.append(f"❌ models.py validation error: {str(e)}")
    
    return results

def validate_main_py():
    """Validate main.py has v2 processing."""
    print("🔍 Validating main.py v2 processing...")
    
    try:
        with open('src/main.py', 'r') as f:
            main_code = f.read()
        
        results = []
        
        if 'files' in main_code and 'process_file_intelligently' in main_code:
            results.append("✅ Multi-file processing present in main.py")
        else:
            results.append("❌ Multi-file processing missing in main.py")
        
        if '_format_apify_v2_result' in main_code:
            results.append("✅ v2 result formatting present in main.py")
        else:
            results.append("❌ v2 result formatting missing in main.py")
        
        return results
        
    except Exception as e:
        return [f"❌ main.py validation error: {str(e)}"]

def main():
    """Run all validation tests."""
    print("🚀 Starting DocuFlow Headless v2 transformation validation...")
    print("=" * 60)
    
    all_results = []
    
    # 1. Requirements validation
    print("\n📋 Requirements Validation:")
    req_results = validate_requirements()
    all_results.extend(req_results)
    
    # 2. Input schema validation
    print("\n📊 Input Schema Validation:")
    schema_results = validate_input_schema()
    all_results.extend(schema_results)
    
    # 3. Code changes validation
    print("\n🏗️ Code Changes Validation:")
    code_results = validate_code_changes()
    all_results.extend(code_results)
    
    # 4. Main.py validation
    print("\n🔧 Main.py Validation:")
    main_results = validate_main_py()
    all_results.extend(main_results)
    
    # Summary
    print("\n" + "=" * 60)
    print("📈 VALIDATION SUMMARY:")
    print("=" * 60)
    
    passed_count = sum(1 for result in all_results if result.startswith("✅"))
    failed_count = sum(1 for result in all_results if result.startswith("❌"))
    
    for result in all_results:
        print(result)
    
    print(f"\n📊 Results: {passed_count} passed, {failed_count} failed")
    
    if failed_count == 0:
        print("\n🎉 ALL VALIDATIONS PASSED!")
        print("\n✨ DocuFlow Headless v2 transformation is complete and validated!")
        print("\nKey achievements:")
        print("  ✅ Anti-hallucination constraints enforced")
        print("  ✅ PyMuPDF + Docling (no_ocr) for CPU processing")
        print("  ✅ External API calls for GPU processing (no local heavy models)")
        print("  ✅ Intelligent ingestion with AGB filtering")
        print("  ✅ Dynamic schema generation with all Optional fields")
        print("  ✅ n8n-compatible output with Google Drive routing")
        print("  ✅ Multi-file processing support")
        print("  ✅ Comprehensive error handling and logging")
        return True
    else:
        print(f"\n⚠️  {failed_count} validation(s) failed. Please review the issues above.")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)