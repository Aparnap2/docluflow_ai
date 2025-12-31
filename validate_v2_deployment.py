#!/usr/bin/env python3
"""
Final validation script for DocuFlow Headless v2 deployment.
Tests all anti-hallucination constraints and deployment readiness.
"""

import os
import sys
import subprocess
import json
from pathlib import Path


def check_no_torch_transformers():
    """Verify no torch/transformers imports in main container."""
    print("🔍 Checking for torch/transformers imports...")
    
    # Files to check
    check_files = [
        "src/main.py",
        "src/graph.py", 
        "src/models.py",
        "src/engine/__init__.py",
        "src/engine/ingest.py",
        "src/engine/ocr.py",
        "src/engine/llm.py"
    ]
    
    forbidden_imports = ["import torch", "from torch", "import transformers", "from transformers"]
    
    violations = []
    for file_path in check_files:
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                content = f.read()
                for forbidden in forbidden_imports:
                    if forbidden in content:
                        violations.append(f"{file_path}: {forbidden}")
    
    if violations:
        print("❌ VIOLATIONS FOUND:")
        for violation in violations:
            print(f"  - {violation}")
        return False
    else:
        print("✅ No torch/transformers imports found in main container")
        return True


def check_requirements_constraints():
    """Verify requirements.txt follows anti-hallucination constraints."""
    print("🔍 Checking requirements.txt constraints...")
    
    if not os.path.exists("requirements.txt"):
        print("❌ requirements.txt not found")
        return False
    
    with open("requirements.txt", 'r') as f:
        requirements = f.read().lower()
    
    forbidden_packages = ["torch", "transformers", "unstructured"]
    violations = []
    
    for package in forbidden_packages:
        if package in requirements:
            violations.append(package)
    
    if violations:
        print("❌ FORBIDDEN PACKAGES FOUND:")
        for violation in violations:
            print(f"  - {violation}")
        return False
    else:
        print("✅ No forbidden packages in requirements.txt")
        return True


def check_input_schema_format():
    """Verify input schema follows v2 format."""
    print("🔍 Checking input schema format...")
    
    schema_path = ".actor/input_schema.json"
    if not os.path.exists(schema_path):
        print("❌ input_schema.json not found")
        return False
    
    try:
        with open(schema_path, 'r') as f:
            schema = json.load(f)
        
        # Check for v2 specific fields
        required_fields = ["files", "filterKeywords", "schema"]
        missing_fields = []
        
        for field in required_fields:
            if field not in schema.get("properties", {}):
                missing_fields.append(field)
        
        if missing_fields:
            print(f"❌ Missing v2 fields: {missing_fields}")
            return False
        
        # Check files array format
        files_prop = schema["properties"]["files"]
        if files_prop.get("type") != "array":
            print("❌ files property should be array type")
            return False
        
        print("✅ Input schema follows v2 format")
        return True
        
    except Exception as e:
        print(f"❌ Error reading schema: {e}")
        return False


def check_actor_configuration():
    """Verify actor.json configuration."""
    print("🔍 Checking actor.json configuration...")
    
    actor_path = ".actor/actor.json"
    if not os.path.exists(actor_path):
        print("❌ actor.json not found")
        return False
    
    try:
        with open(actor_path, 'r') as f:
            actor_config = json.load(f)
        
        # Check runtime
        if actor_config.get("runtime", {}).get("type") != "python":
            print("❌ Runtime should be python")
            return False
        
        # Check Python version
        runtime_version = actor_config.get("runtime", {}).get("version")
        if runtime_version and not runtime_version.startswith("3.11"):
            print(f"⚠️  Python version is {runtime_version}, recommended is 3.11")
        
        print("✅ Actor configuration valid")
        return True
        
    except Exception as e:
        print(f"❌ Error reading actor.json: {e}")
        return False


def check_v2_engines_exist():
    """Verify all v2 engines are implemented."""
    print("🔍 Checking v2 engine implementations...")
    
    required_engines = [
        "src/engine/intelligent_ingest.py",
        "src/engine/engine_cpu.py", 
        "src/engine/engine_gpu.py",
        "src/engine/schema_builder.py",
        "src/engine/output_formatter.py"
    ]
    
    missing_engines = []
    for engine in required_engines:
        if not os.path.exists(engine):
            missing_engines.append(engine)
    
    if missing_engines:
        print(f"❌ Missing v2 engines: {missing_engines}")
        return False
    else:
        print("✅ All v2 engines implemented")
        return True


def check_test_coverage():
    """Verify test coverage for v2 functionality."""
    print("🔍 Checking test coverage...")
    
    test_files = [
        "test_v2_simple.py",
        "test_v2_comprehensive.py"
    ]
    
    missing_tests = []
    for test_file in test_files:
        if not os.path.exists(test_file):
            missing_tests.append(test_file)
    
    if missing_tests:
        print(f"❌ Missing test files: {missing_tests}")
        return False
    else:
        print("✅ Test files present")
        return True


def run_basic_tests():
    """Run basic functionality tests."""
    print("🔍 Running basic functionality tests...")
    
    try:
        result = subprocess.run(
            ["uv", "run", "python", "test_v2_simple.py"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print("✅ Basic tests passed")
            return True
        else:
            print("❌ Basic tests failed")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ Tests timed out")
        return False
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return False


def main():
    """Run all validation checks."""
    print("🚀 DocuFlow Headless v2 Deployment Validation")
    print("=" * 50)
    
    checks = [
        ("Anti-Hallucination Constraints", check_no_torch_transformers),
        ("Requirements Constraints", check_requirements_constraints), 
        ("Input Schema Format", check_input_schema_format),
        ("Actor Configuration", check_actor_configuration),
        ("V2 Engines Implementation", check_v2_engines_exist),
        ("Test Coverage", check_test_coverage),
        ("Basic Functionality", run_basic_tests)
    ]
    
    results = {}
    all_passed = True
    
    for check_name, check_func in checks:
        print(f"\n📋 {check_name}:")
        try:
            passed = check_func()
            results[check_name] = passed
            if not passed:
                all_passed = False
        except Exception as e:
            print(f"❌ Error in {check_name}: {e}")
            results[check_name] = False
            all_passed = False
    
    print("\n" + "=" * 50)
    print("📊 VALIDATION SUMMARY:")
    
    for check_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {check_name}: {status}")
    
    if all_passed:
        print("\n🎉 ALL VALIDATIONS PASSED!")
        print("✅ DocuFlow Headless v2 is ready for deployment!")
        return 0
    else:
        print("\n❌ SOME VALIDATIONS FAILED!")
        print("🔧 Please fix the issues before deployment.")
        return 1


if __name__ == "__main__":
    sys.exit(main())