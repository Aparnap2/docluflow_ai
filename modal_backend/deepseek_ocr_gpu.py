"""Modal GPU backend for DeepSeek-OCR using vLLM."""

import modal
import subprocess
import os

# Create Modal app
app = modal.App("deepseek-ocr-gpu")

# GPU-optimized image with CUDA and Flash Attention 2
image = (
    modal.Image.from_registry("nvidia/cuda:12.4.0-devel-ubuntu22.04", add_python="3.11")
    .pip_install(
        "vllm>=0.11.0",
        "torch>=2.1.0",
        "transformers>=4.35.0",
        "flash-attn>=2.3.0",
        "structlog>=23.1.0",
        "pillow>=10.0.0"
    )
    .apt_install(
        "libgl1-mesa-glx",
        "libglib2.0-0"
    )
)

@app.function(
    image=image,
    gpu="L4",  # L4 GPU with 24GB VRAM for optimal performance
    timeout=600,  # 10 minute timeout
    memory=32768,  # 32GB RAM for large model
    secrets=[
        modal.Secret.from_name("huggingface-secret")  # For gated models if needed
    ],
    scaledown_window=300  # Keep GPU warm for 5 minutes between requests
)
@modal.web_server(port=8000)
def serve():
    """Serve DeepSeek-OCR model using vLLM on GPU."""
    import structlog
    logger = structlog.get_logger(__name__)
    
    logger.info("Starting DeepSeek-OCR GPU server")
    
    # DeepSeek-OCR vLLM serving with optimized settings
    cmd = [
        "vllm", "serve", "deepseek-ai/DeepSeek-OCR",
        "--trust-remote-code",  # Required for DeepSeek-OCR
        "--port", "8000",
        "--host", "0.0.0.0",
        "--gpu-memory-utilization", "0.9",  # Use 90% of GPU memory
        "--max-model-len", "4096",  # Limit context for stability
        "--enforce-eager",  # Faster cold starts
        "--disable-log-stats",  # Reduce logging overhead
        "--dtype", "float16"  # Use FP16 for memory efficiency
    ]
    
    # Launch vLLM server
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    logger.info("DeepSeek-OCR server started", pid=process.pid)
    
    # Keep the function running
    try:
        process.wait()
    except KeyboardInterrupt:
        process.terminate()
        process.wait()

@app.function(
    image=image,
    gpu="L4",
    timeout=60
)
def health_check() -> dict:
    """Health check endpoint for the GPU service."""
    try:
        import requests
        response = requests.get("http://localhost:8000/health", timeout=10)
        return {
            "status": "healthy" if response.status_code == 200 else "unhealthy",
            "service": "deepseek-ocr-gpu",
            "endpoint": "http://localhost:8000",
            "gpu": "L4"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "service": "deepseek-ocr-gpu",
            "gpu": "L4"
        }

# Local entry point for testing
if __name__ == "__main__":
    with app.run():
        result = health_check.remote()
        print(f"Health check: {result}")