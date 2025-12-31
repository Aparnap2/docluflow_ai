"""Final optimized Modal GPU backend for DeepSeek-OCR using vLLM with persistent caching."""

import modal
import subprocess
import os

# Create Modal app
app = modal.App("deepseek-ocr-gpu-final")

# Create persistent volumes for caching
# This follows 2025 Modal best practices for model persistence
hf_cache_vol = modal.Volume.from_name("deepseek-ocr-cache-final", create_if_missing=True)
vllm_cache_vol = modal.Volume.from_name("vllm-cache-deepseek-final", create_if_missing=True)

# GPU-optimized image with CUDA and vLLM following Modal best practices
image = (
    modal.Image.from_registry("nvidia/cuda:12.8.0-devel-ubuntu22.04", add_python="3.11")
    .apt_install(
        "libgl1-mesa-glx",
        "libglib2.0-0",
        "build-essential",
        "python3-dev"
    )
    .env({
        "HF_HUB_ENABLE_HF_TRANSFER": "1",  # faster model transfers
        "VLLM_ATTENTION_BACKEND": "FLASH_ATTN",  # Use Flash Attention
        "VLLM_WORKER_MULTIPROC_METHOD": "spawn",  # Better for GPU
        "CUDA_VISIBLE_DEVICES": "0",  # Use first GPU
    })
    .pip_install(  # Use pip for compatibility
        "vllm>=0.10.2",
        "huggingface_hub[hf_transfer]>=0.35.0",
        "flashinfer-python==0.3.1",
        "torch==2.8.0",
        "structlog>=23.1.0"
    )
)

# Model configuration
MODEL_NAME = "deepseek-ai/DeepSeek-OCR"
MODEL_REVISION = "main"  # Use latest stable revision

@app.function(
    image=image,
    gpu="L4",  # L4 GPU with 24GB VRAM
    timeout=600,  # 10 minute timeout
    memory=32768,  # 32GB RAM
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
    """Serve DeepSeek-OCR model using vLLM on GPU with persistent caching."""
    import structlog
    
    logger = structlog.get_logger(__name__)
    logger.info("Starting DeepSeek-OCR GPU vLLM server with persistent caching")
    
    # Set HF token for public models
    os.environ["HF_TOKEN"] = ""
    
    # vLLM serving command for GPU with optimized settings
    cmd = [
        "vllm", "serve", MODEL_NAME,
        "--revision", MODEL_REVISION,
        "--port", "8000",
        "--host", "0.0.0.0",
        "--trust-remote-code",  # Required for DeepSeek-OCR
        "--gpu-memory-utilization", "0.85",  # Use 85% of GPU memory
        "--max-model-len", "4096",  # Limit context for stability
        "--enforce-eager",  # Faster cold starts
        "--disable-log-stats",  # Reduce logging overhead
        "--download-dir", "/root/.cache/huggingface",  # Use persistent cache
        "--dtype", "float16",  # Use FP16 for memory efficiency
        "--mm-processor-cache-gb", "0",  # Recommended for DeepSeek-OCR
        "--max-num-batched-tokens", "4096",  # Batch size limit
        "--max-num-seqs", "16",  # Sequence limit
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
        
        logger.info("DeepSeek-OCR vLLM server started", pid=process.pid)
        
        # Keep the function running
        process.wait()
        
    except Exception as e:
        logger.error("Failed to start DeepSeek-OCR vLLM server", error=str(e))
        raise RuntimeError(f"Failed to start vLLM server: {str(e)}")

# Local entry point for testing
if __name__ == "__main__":
    with app.run():
        print("DeepSeek-OCR GPU vLLM server running locally")