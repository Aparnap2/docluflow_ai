from langgraph.graph import StateGraph, END
from typing import TypedDict, Any
from schemas import LeaseSchema, QuoteSchema, CoiSchema
from utils_ocr import run_docling
from pydantic import ValidationError
import json
import re

class AgentState(TypedDict):
    doc_url: str
    text_md: str
    doc_type: str
    final_data: dict

async def ocr_node(state):
    text_md = await run_docling(state['doc_url'])
    return {"text_md": text_md}

def router_node(state):
    """
    Router node with input truncation to prevent ReDoS attacks.
    
    Limits text to first 1000 characters before pattern matching.
    """
    from utils_security import truncate_text
    
    # Truncate input to prevent ReDoS (even though we use simple 'in' checks)
    text = truncate_text(state['text_md'], max_length=1000).lower()
    
    # Simple heuristic or mini-LLM call
    if "lease" in text or "tenant" in text: 
        return {"doc_type": "lease"}
    if "estimate" in text or "quote" in text: 
        return {"doc_type": "quote"}
    if "certificate of liability" in text: 
        return {"doc_type": "coi"}
    return {"doc_type": "unknown"}

def extraction_node(state):
    """
    Extraction node with dynamic model selection (PRD Pattern).
    
    PRD specifies:
    - DeepSeek-V3 for complex docs (lease, quote)
    - Gemma-3-12b-it for simple docs (COI)
    - Use with_structured_output for structured extraction
    
    Current implementation uses Ollama for local dev, but structured
    to easily migrate to DeepInfra with with_structured_output.
    """
    # Dynamic Model Selection based on complexity (PRD Pattern)
    # Dev: Using Ollama (ministral-3:3b for all types)
    # Prod: Would use DeepInfra with DeepSeek-V3 for complex, Gemma for simple
    model_name = "ministral-3:3b"  # Dev: Ollama equivalent
    
    # Production pattern (commented for reference):
    # if state['doc_type'] == "coi":
    #     model_name = "google/gemma-3-12b-it"  # Cheaper for simple docs
    # else:
    #     model_name = "deepseek-ai/DeepSeek-V3"  # Smartest for complex docs
    
    # Select Schema
    schema_map = {"lease": LeaseSchema, "quote": QuoteSchema, "coi": CoiSchema}
    target_schema = schema_map.get(state['doc_type'])
    
    if not target_schema: 
        return {"final_data": {"error": "Unknown Type"}}

    # PRD Pattern: Structured Output (The Magic)
    # Production would use: extractor = llm.with_structured_output(target_schema)
    # For Ollama (dev), we use manual JSON parsing
    
    # Use Ollama via langchain (dev mode)
    from langchain_community.llms import Ollama
    llm = Ollama(model=model_name, temperature=0)
    
    # Production pattern (commented for reference):
    # from langchain_openai import ChatOpenAI
    # llm = ChatOpenAI(
    #     base_url="https://api.deepinfra.com/v1/openai",
    #     model=model_name,
    #     temperature=0,
    #     api_key=os.getenv("DEEPINFRA_TOKEN")
    # )
    # extractor = llm.with_structured_output(target_schema)
    # data = extractor.invoke(state['text_md'])
    # return {"final_data": data.model_dump(mode='json')}
    
    # Dev: Manual JSON parsing (Ollama doesn't support with_structured_output)
    # Truncate text to prevent ReDoS and reduce token usage
    from utils_security import truncate_text, safe_regex_search
    
    truncated_text = truncate_text(state['text_md'], max_length=50000)  # Limit to 50k chars
    
    schema_json = json.dumps(target_schema.model_json_schema(), indent=2)
    prompt = f"""Extract information from the following document text according to this JSON schema:

{schema_json}

Document text:
{truncated_text}

Return ONLY valid JSON matching the schema. Do not include any markdown code blocks or extra text, just the JSON object."""

    try:
        response = llm.invoke(prompt)
        
        # Clean response - remove markdown code blocks if present (safe regex)
        cleaned_response = re.sub(r'```json\s*', '', response)
        cleaned_response = re.sub(r'```\s*', '', cleaned_response)
        cleaned_response = cleaned_response.strip()
        
        # Try to find JSON object in response (safe regex with truncation)
        json_match = safe_regex_search(r'\{.*\}', cleaned_response, max_length=10000)
        if json_match:
            cleaned_response = json_match.group(0)
        
        # Parse JSON
        data = json.loads(cleaned_response)
        
        # Validate with schema (this triggers business logic validators)
        # CRITICAL: Catch ValidationError specifically to prevent silent failures
        try:
            validated = target_schema(**data)
            return {"final_data": validated.model_dump(mode='json')}
        except ValidationError as e:
            # Return validation errors as structured data, don't crash
            return {
                "final_data": {
                    "status": "validation_error",
                    "doc_type": state['doc_type'],
                    "errors": e.errors(),
                    "partial_data": data,  # Include what we did extract
                    "message": "Schema validation failed - some fields may be missing or invalid"
                }
            }
    except json.JSONDecodeError as e:
        return {"final_data": {"error": f"JSON parsing failed: {str(e)}. Response was: {response[:200]}"}}
    except Exception as e:
        return {"final_data": {"error": str(e), "error_type": type(e).__name__}}

# Build Graph
workflow = StateGraph(AgentState)
workflow.add_node("ocr", ocr_node)
workflow.add_node("router", router_node)
workflow.add_node("extract", extraction_node)
workflow.set_entry_point("ocr")
workflow.add_edge("ocr", "router")
workflow.add_edge("router", "extract")
workflow.add_edge("extract", END)
app = workflow.compile()