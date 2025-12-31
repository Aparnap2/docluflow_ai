"""Modal CPU backend for Granite-Docling-258M using vLLM."""

import modal
import subprocess
import os

# Create Modal app
app = modal.App("granite-docling-cpu")

# CPU-optimized image with vLLM
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "vllm>=0.10.2",
        "huggingface_hub",
        "structlog>=23.1.0"
    )
)

@app.function(
    image=image, 
    cpu=4.0,  # 4 cores for CPU processing
    memory=8192,  # 8GB RAM
    timeout=600,  # 10 minute timeout
    secrets=[
        modal.Secret.from_name("huggingface-secret")  # For gated models if needed
    ]
)
@modal.web_server(port=8000)
def serve():
    """Serve Granite-Docling model using vLLM on CPU."""
    import structlog
    logger = structlog.get_logger(__name__)
    
    logger.info("Starting Granite-Docling CPU server")
    
    # Uses the 'untied' revision for compatibility with CPU/non-bfloat16
    cmd = [
        "vllm", "serve", "ibm-granite/granite-docling-258M",
        "--revision", "untied",
        "--device", "cpu",
        "--port", "8000",
        "--host", "0.0.0.0",
        "--max-model-len", "4096",  # Limit context for CPU efficiency
        "--enforce-eager",  # Faster cold starts
        "--disable-log-stats"  # Reduce logging overhead
    ]
    
    # Launch vLLM server
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    logger.info("Granite-Docling server started", pid=process.pid)
    
    # Keep the function running
    try:
        process.wait()
    except KeyboardInterrupt:
        process.terminate()
        process.wait()

@app.function(
    image=image,
    cpu=2.0,
    memory=4096,
    timeout=60
)
def health_check() -> dict:
    """Health check endpoint for the CPU service."""
    try:
        import requests
        response = requests.get("http://localhost:8000/health", timeout=10)
        return {
            "status": "healthy" if response.status_code == 200 else "unhealthy",
            "service": "granite-docling-cpu",
            "endpoint": "http://localhost:8000"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "service": "granite-docling-cpu"
        }

# Local entry point for testing
if __name__ == "__main__":
    with app.run():
        result = health_check.remote()
        print(f"Health check: {result}")