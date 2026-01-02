import os
import json
from typing import Optional, TypedDict, Literal
import httpx
from apify import Actor
from langgraph.graph import StateGraph, START, END

# Import GLiNER for Tier 1 processing
try:
    from gliner import GLiNER
    GLINER_AVAILABLE = True
    gliner_model = None  # Will be loaded on demand
except ImportError:
    GLINER_AVAILABLE = False
    gliner_model = None


# ---- ENV (set in Apify Secrets / Env vars) ----
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "").rstrip("/")  # https://...modal.run
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-ai/DeepSeek-OCR")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")  # if you add auth

GRANITE_BASE_URL = os.getenv("GRANITE_BASE_URL", "").rstrip("/")  # https://...modal.run
GRANITE_API_KEY = os.getenv("GRANITE_API_KEY")  # optional


class DocState(TypedDict, total=False):
    doc_url: str
    doc_type: Literal["image", "pdf", "html", "text", "unknown"]
    bytes: bytes

    ocr_text: str
    docling_json: dict
    gliner_entities: dict

    used: str
    error: str


def detect_type(url: str) -> str:
    u = url.lower()
    if any(u.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".tiff", ".bmp"]):
        return "image"
    if u.endswith(".pdf"):
        return "pdf"
    if u.endswith(".txt"):
        return "text"
    if u.startswith("http"):
        return "unknown"
    return "unknown"


async def fetch_document(state: DocState, client: httpx.AsyncClient) -> DocState:
    url = state["doc_url"]
    r = await client.get(url, follow_redirects=True, timeout=120)
    r.raise_for_status()
    return {"bytes": r.content, "doc_type": detect_type(url)}


async def call_gliner_extraction(state: DocState) -> DocState:
    """Tier 1: GLiNER extraction - Instant and free for specific entities."""
    if not GLINER_AVAILABLE:
        return {"error": "GLiNER not available", "used": "gliner_not_available"}

    # Get text content from state
    text_content = state.get("ocr_text", "")
    if not text_content:
        # If no OCR text, try to decode bytes
        if state.get("bytes"):
            try:
                text_content = state["bytes"].decode("utf-8", errors="ignore")
            except:
                return {"error": "Could not extract text for GLiNER processing", "used": "gliner_decode_error"}

    # Load GLiNER model if not already loaded
    global gliner_model
    if gliner_model is None:
        try:
            gliner_model = GLiNER.from_pretrained("urchade/gliner_medium-v2.1")
        except Exception as e:
            return {"error": f"Could not load GLiNER model: {str(e)}", "used": "gliner_load_error"}

    # Define common labels for document processing
    labels = [
        "invoice_number", "date", "total_amount", "vendor_name", "customer_name",
        "item", "quantity", "price", "subtotal", "tax", "due_date", "po_number",
        "payment_terms", "address", "phone", "email", "website"
    ]

    try:
        # Extract entities using GLiNER
        entities = gliner_model.predict_entities(text_content, labels)

        # Format entities into structured data
        structured_entities = {}
        for entity in entities:
            label = entity['label']
            text = entity['text']

            # Group entities by label
            if label not in structured_entities:
                structured_entities[label] = []
            structured_entities[label].append(text)

        return {
            "gliner_entities": structured_entities,
            "used": "gliner_extraction",
            "ocr_text": text_content  # Pass through the text for downstream processing
        }

    except Exception as e:
        return {"error": f"GLiNER extraction failed: {str(e)}", "used": "gliner_extraction_error"}


async def call_deepseek_ocr(state: DocState, client: httpx.AsyncClient) -> DocState:
    """Tier 3: DeepSeek OCR - Premium processing for complex documents."""
    if not DEEPSEEK_BASE_URL:
        return {"error": "Missing DEEPSEEK_BASE_URL"}

    # For multimodal models like DeepSeek-OCR, we need to handle image content
    if state["doc_type"] in ("image", "pdf"):
        # For now, we'll pass the URL directly - in production, you'd download and encode the image
        payload = {
            "model": DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": "You are an OCR engine. Return only extracted text from the document."},
                {"role": "user", "content": [
                    {"type": "text", "text": "Extract all text from this document."},
                    {"type": "image_url", "image_url": {"url": state['doc_url']}}
                ]},
            ],
            "stream": False,
            "temperature": 0,
            "max_tokens": 2048,
        }
    else:
        # For text documents, just pass the content
        payload = {
            "model": DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": "You are an OCR engine. Return only extracted text."},
                {"role": "user", "content": f"Extract text from this document:\n{state['doc_url']}"},
            ],
            "stream": False,
            "temperature": 0,
            "max_tokens": 2048,
        }

    headers = {"Content-Type": "application/json"}
    if DEEPSEEK_API_KEY:
        headers["Authorization"] = f"Bearer {DEEPSEEK_API_KEY}"

    r = await client.post(f"{DEEPSEEK_BASE_URL}/v1/chat/completions", json=payload, headers=headers, timeout=300)
    r.raise_for_status()
    data = r.json()
    text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return {"ocr_text": text, "used": "deepseek_ocr"}


async def call_granite_docling(state: DocState, client: httpx.AsyncClient) -> DocState:
    """Tier 2: Granite Docling - Cheap CPU processing for structured extraction."""
    if not GRANITE_BASE_URL:
        return {"error": "Missing GRANITE_BASE_URL"}

    # Use the text from either GLiNER (if it ran) or OCR
    text_to_process = state.get('gliner_entities', state.get('ocr_text', ''))

    # If text_to_process is a dict (from GLiNER), convert to string
    if isinstance(text_to_process, dict):
        text_str = json.dumps(text_to_process, indent=2)
    else:
        text_str = str(text_to_process)

    # Based on research, llama.cpp servers may use different endpoints
    # Common endpoints are /v1/chat/completions or /completion
    headers = {"Content-Type": "application/json"}
    if GRANITE_API_KEY:
        headers["Authorization"] = f"Bearer {GRANITE_API_KEY}"

    # Try the OpenAI-compatible endpoint first
    payload = {
        "model": "granite-docling",  # Model identifier
        "messages": [
            {"role": "system", "content": "You are a document understanding engine. Extract structured information from the provided text."},
            {"role": "user", "content": f"Extract structured information from this text:\n{text_str}"},
        ],
        "temperature": 0,
        "max_tokens": 1024,
    }

    try:
        r = await client.post(f"{GRANITE_BASE_URL}/v1/chat/completions", json=payload, headers=headers, timeout=300)
        r.raise_for_status()
        response_data = r.json()
        text = response_data.get("choices", [{}])[0].get("message", {}).get("content", "")
    except (httpx.HTTPStatusError, json.JSONDecodeError, IndexError):
        # Fallback to /completion endpoint
        try:
            payload = {
                "prompt": f"Extract structured information from this text:\n{text_str}",
                "temperature": 0,
                "max_tokens": 1024,
            }
            r = await client.post(f"{GRANITE_BASE_URL}/completion", json=payload, headers=headers, timeout=300)
            r.raise_for_status()
            response_data = r.json()
            text = response_data.get("content", "") or response_data.get("choices", [{}])[0].get("text", "")
        except Exception as e:
            return {"error": f"Granite Docling API error: {str(e)}"}

    # "Docling JSON" placeholder: plug in real Docling parsing here.
    return {
        "docling_json": {
            "text": text,
            "source": "granite_docling_llama_server",
            "processing_method": "structured_extraction"
        },
        "used": (state.get("used", "") + "+granite_docling").strip("+"),
    }


def build_graph():
    g = StateGraph(DocState)

    # Define the processing nodes
    g.add_node("fetch", fetch_document)
    g.add_node("gliner", call_gliner_extraction)  # Tier 1: Free & Instant
    g.add_node("ocr", call_deepseek_ocr)          # Tier 3: Premium
    g.add_node("docling", call_granite_docling)   # Tier 2: Cheap

    # Define the flow: fetch -> try GLiNER first -> fallback to OCR -> process with Docling
    g.add_edge(START, "fetch")
    g.add_edge("fetch", "gliner")

    # After GLiNER, we can either go to docling directly (if GLiNER succeeded)
    # or to OCR (if GLiNER failed) and then to docling
    # For now, we'll always go to OCR as fallback and then to docling
    g.add_edge("gliner", "ocr")
    g.add_edge("ocr", "docling")
    g.add_edge("docling", END)

    return g.compile()


graph = build_graph()


async def run_one(doc_url: str) -> dict:
    state: DocState = {"doc_url": doc_url}

    async with httpx.AsyncClient() as client:
        # Run the graph from the initial state
        final_state = await graph.ainvoke(state)
        return final_state


async def main() -> None:
    async with Actor:
        inp = await Actor.get_input() or {}  # canonical pattern [web:4979]
        urls = inp.get("docUrls") or []
        if not urls:
            raise RuntimeError("Input must include docUrls: [ ... ]")

        for url in urls:
            result = await run_one(url)
            await Actor.push_data(result)  # canonical output [web:4972]


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())