# DocuFlow Headless - Development Plan

## Overview
This document outlines the development plan to fix issues with the Granite Docling CPU and DeepSeek OCR GPU Modal endpoints, ensuring both work correctly with persistent volume storage and proper model configurations.

## Current Issues Identified

### 1. Granite Docling CPU Endpoint
- **Issue**: `unknown pre-tokenizer type: 'granite-docling'`
- **Root Cause**: Using outdated llama-cpp-python version that doesn't support granite-docling pre-tokenizer
- **Solution**: Build llama.cpp from source to get latest granite-docling support

### 2. DeepSeek OCR GPU Endpoint
- **Issue**: `vllm error: unrecognized arguments` (e.g., `--no-enable-prefix-caching`, `--mm-processor-cache-gb`)
- **Root Cause**: Using vLLM command-line arguments that are incompatible with v0.6.3+ version
- **Solution**: Simplify vLLM command to use only supported arguments

### 3. Repository URL Issue
- **Issue**: Using incorrect Hugging Face repository URL (`infl002` instead of `infil00p`)
- **Solution**: Update repository URL to correct one

## Development Tasks

### Task 1: Fix Granite Docling CPU Endpoint
**Priority**: High
**Estimated Time**: 2-3 hours

#### Subtasks:
1.1. Update the image to build llama.cpp from source
1.2. Ensure proper compilation flags for granite-docling support
1.3. Update model download function to use correct repository URL
1.4. Test compilation and model loading
1.5. Verify granite-docling pre-tokenizer works

#### Implementation:
- Use git clone to get latest llama.cpp source
- Compile with proper CMake flags
- Download models from correct repository (`infil00p/granite-docling-258M-GGUF`)
- Use compiled llama-server binary

### Task 2: Fix DeepSeek OCR GPU Endpoint
**Priority**: High
**Estimated Time**: 1-2 hours

#### Subtasks:
2.1. Remove unsupported vLLM command-line arguments
2.2. Simplify vLLM serve command to use only supported arguments
2.3. Add `--trust-remote-code` flag for DeepSeek-OCR
2.4. Set appropriate context length to prevent OOM errors
2.5. Test vLLM server startup and model loading

#### Implementation:
- Remove problematic flags: `--no-enable-prefix-caching`, `--mm-processor-cache-gb`, `--logits-processors`
- Keep essential flags: `--trust-remote-code`, `--max-model-len`, `--tensor-parallel-size`
- Ensure model loads correctly from persistent volume

### Task 3: Update Model Download Functions
**Priority**: Medium
**Estimated Time**: 1 hour

#### Subtasks:
3.1. Update download functions to use correct repository URLs
3.2. Ensure models are properly saved to Modal volumes
3.3. Add error handling for download failures
3.4. Test download functions work correctly

### Task 4: Update Apify Actor Integration
**Priority**: Medium
**Estimated Time**: 1 hour

#### Subtasks:
4.1. Update endpoint URLs in main.py to match deployed endpoints
4.2. Ensure proper error handling for API calls
4.3. Test integration with both fixed endpoints

### Task 5: Testing and Validation
**Priority**: High
**Estimated Time**: 2 hours

#### Subtasks:
5.1. Deploy both fixed endpoints to Modal
5.2. Run integration tests to verify functionality
5.3. Test with sample documents
5.4. Verify persistent volume usage works correctly
5.5. Run load tests to ensure stability

## Implementation Timeline

### Day 1
- [x] Analyze current codebase and identify issues
- [ ] Implement Task 1: Fix Granite Docling CPU Endpoint
- [ ] Implement Task 2: Fix DeepSeek OCR GPU Endpoint

### Day 2
- [ ] Implement Task 3: Update Model Download Functions
- [ ] Implement Task 4: Update Apify Actor Integration
- [ ] Begin Task 5: Testing and Validation

### Day 3
- [ ] Complete Task 5: Testing and Validation
- [ ] Document deployment instructions
- [ ] Prepare final deployment

## Success Criteria

### Granite Docling CPU Endpoint
- [ ] Successfully compiles llama.cpp from source
- [ ] Loads granite-docling model without pre-tokenizer errors
- [ ] Responds to API requests correctly
- [ ] Uses persistent volume for model storage

### DeepSeek OCR GPU Endpoint
- [ ] Starts vLLM server without argument errors
- [ ] Loads DeepSeek-OCR model correctly
- [ ] Responds to API requests correctly
- [ ] Uses persistent volume for model storage

### Overall System
- [ ] Both endpoints deploy successfully to Modal
- [ ] Apify Actor can communicate with both endpoints
- [ ] Integration tests pass
- [ ] Load tests show stability

## Risk Mitigation

### Risks
1. **Compilation Time**: Building llama.cpp from source takes time
   - Mitigation: Use efficient build flags and parallel compilation

2. **GPU Resource Limitations**: vLLM may require more resources than available
   - Mitigation: Optimize model loading and context size

3. **Model Compatibility**: Updated models may have different API requirements
   - Mitigation: Test thoroughly with sample requests

## Deployment Instructions

### Pre-deployment
1. Ensure Modal account is set up and authenticated
2. Verify sufficient GPU resources for DeepSeek OCR
3. Test model download functions

### Deployment Steps
1. Deploy Granite Docling CPU endpoint: `modal deploy modal_backend/modal_granite_docling_llama_server.py`
2. Deploy DeepSeek OCR GPU endpoint: `modal deploy modal_backend/modal_deepseek_ocr_vllm.py`
3. Update Apify Actor with new endpoint URLs
4. Deploy Apify Actor to production

### Post-deployment
1. Run integration tests
2. Monitor endpoint health and performance
3. Verify persistent volume usage