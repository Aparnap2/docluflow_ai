"""Final optimized Modal CPU backend for Granite-Docling using vLLM with persistent caching."""

import modal
import subprocess
import os

# Create Modal app
app = modal.App("granite-docling-cpu-final")

# Create persistent volume for Hugging Face cache to prevent re-downloads
# This follows 2025 Modal best practices for model persistence
hf_cache_vol = modal.Volume.from_name("granite-docling-cache-final", create_if_missing=True)
vllm_cache_vol = modal.Volume.from_name("vllm-cache-granite-final", create_if_missing=True)

# CPU-optimized image with vLLM following Modal best practices
image = (
    modal.Image.debian_slim(python_version="3.11")
    .env({
        "HF_HUB_ENABLE_HF_TRANSFER": "1",  # faster model transfers
        "VLLM_WORKER_MULTIPROC_METHOD": "spawn",  # Better for CPU
    })
    .pip_install(
        "vllm>=0.10.2",
        "huggingface_hub[hf_transfer]>=0.35.0",
        "structlog>=23.1.0"
    )
)

# Model configuration
MODEL_NAME = "ibm-granite/granite-docling-258M"
MODEL_REVISION = "untied"  # CPU-compatible revision

@app.function(
    image=image, 
    cpu=4.0,  # 4 cores for CPU processing
    memory=8192,  # 8GB RAM
    timeout=600,  # 10 minute timeout
    volumes={
        "/root/.cache/huggingface": hf_cache_vol,  # Persistent HF cache
        "/root/.cache/vllm": vllm_cache_vol  # Persistent vLLM cache
    },
    secrets=[
        modal.Secret.from_dict({"HF_TOKEN": ""})  # Empty token for public models
    ],
    scaledown_window=300  # Keep warm for 5 minutes between requests
)
@modal.web_server(port=8000)
def serve():
    """Serve Granite-Docling model using vLLM on CPU with persistent caching."""
    import structlog
    
    logger = structlog.get_logger(__name__)
    logger.info("Starting Granite-Docling CPU vLLM server with persistent caching")
    
    # Set HF token for public models
    os.environ["HF_TOKEN"] = ""
    
    # vLLM serving command for CPU with optimized settings
    cmd = [
        "vllm", "serve", MODEL_NAME,
        "--revision", MODEL_REVISION,
        "--device", "cpu",
        "--port", "8000",
        "--host", "0.0.0.0",
        "--max-model-len", "4096",  # Limit context for CPU efficiency
        "--enforce-eager",  # Faster cold starts
        "--disable-log-stats",  # Reduce logging overhead
        "--download-dir", "/root/.cache/huggingface",  # Use persistent cache
        "--dtype", "float32",  # CPU-friendly dtype
        "--max-num-batched-tokens", "2048",  # Batch size limit for CPU
        "--max-num-seqs", "8",  # Sequence limit for CPU
        "--disable-log-requests"  # Reduce logging
    ]
    
    logger.info("Launching vLLM server", cmd=" ".join(cmd))
    
    try:
        # Launch vLLM server
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        logger.info("Granite-Docling vLLM server started", pid=process.pid)
        
        # Keep the function running
        process.wait()
        
    except Exception as e:
        logger.error("Failed to start Granite-Docling vLLM server", error=str(e))
        raise RuntimeError(f"Failed to start vLLM server: {str(e)}")

# Local entry point for testing
if __name__ == "__main__":
    with app.run():
        print("Granite-Docling CPU vLLM server running locally")