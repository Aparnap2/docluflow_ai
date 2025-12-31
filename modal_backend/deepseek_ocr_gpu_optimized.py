"""Optimized Modal GPU backend for DeepSeek-OCR using vLLM with persistent caching."""

import modal
import subprocess
import os

# Create Modal app
app = modal.App("deepseek-ocr-gpu-optimized")

# Create persistent volume for Hugging Face cache to prevent re-downloads
hf_cache_vol = modal.Volume.from_name("deepseek-ocr-cache", create_if_missing=True)

# GPU-optimized image with CUDA and Flash Attention 2
image = (
    modal.Image.from_registry("nvidia/cuda:12.4.0-devel-ubuntu22.04", add_python="3.11")
    .apt_install(
        "libgl1-mesa-glx",
        "libglib2.0-0",
        "build-essential",
        "python3-dev"
    )
    .pip_install(
        "torch>=2.1.0",
        "transformers>=4.35.0",
        "structlog>=23.1.0",
        "pillow>=10.0.0"
    )
    .pip_install(
        "flash-attn>=2.3.0",
        "vllm>=0.11.0"
    )
)

@app.function(
    image=image,
    gpu="L4",  # L4 GPU with 24GB VRAM for optimal performance
    timeout=600,  # 10 minute timeout
    memory=32768,  # 32GB RAM for large model
    volumes={"/root/.cache/huggingface": hf_cache_vol},  # Persistent cache
    secrets=[
        modal.Secret.from_dict({"HF_TOKEN": ""})  # Empty token for public models
    ],
    scaledown_window=300  # Keep GPU warm for 5 minutes between requests
)
@modal.web_server(port=8000)
def serve():
    """Serve DeepSeek-OCR model using vLLM on GPU with persistent caching."""
    import structlog
    import time
    import requests
    
    logger = structlog.get_logger(__name__)
    
    logger.info("Starting DeepSeek-OCR GPU server with persistent caching")
    
    # Set HF token (empty for public models, but required for vLLM integration)
    os.environ["HF_TOKEN"] = ""  # Public model, no token needed
    
    # Set vLLM environment variables for better performance
    os.environ["VLLM_ATTENTION_BACKEND"] = "FLASH_ATTN"  # Use Flash Attention
    os.environ["VLLM_WORKER_MULTIPROC_METHOD"] = "spawn"  # Better for GPU
    os.environ["CUDA_VISIBLE_DEVICES"] = "0"  # Use first GPU
    
    # DeepSeek-OCR vLLM serving with optimized settings
    cmd = [
        "vllm", "serve", "deepseek-ai/DeepSeek-OCR",
        "--trust-remote-code",  # Required for DeepSeek-OCR
        "--port", "8000",
        "--host", "0.0.0.0",
        "--gpu-memory-utilization", "0.85",  # Use 85% of GPU memory (reduced for stability)
        "--max-model-len", "4096",  # Limit context for stability
        "--enforce-eager",  # Faster cold starts
        "--disable-log-stats",  # Reduce logging overhead
        "--dtype", "float16",  # Use FP16 for memory efficiency
        "--download-dir", "/root/.cache/huggingface",  # Use persistent cache
        "--mm-processor-cache-gb", "0",  # Recommended for DeepSeek-OCR
        "--max-num-batched-tokens", "4096",  # Batch size limit
        "--max-num-seqs", "16",  # Sequence limit
        "--disable-log-requests"  # Reduce logging
    ]
    
    logger.info("Launching vLLM server with optimized settings", cmd=" ".join(cmd))
    
    try:
        # Launch vLLM server with better error handling
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        logger.info("DeepSeek-OCR server process started", pid=process.pid)
        
        # Wait for server to start with health check
        max_wait_time = 300  # 5 minutes
        check_interval = 10  # Check every 10 seconds
        
        for attempt in range(max_wait_time // check_interval):
            try:
                # Check if server is responding
                response = requests.get("http://localhost:8000/health", timeout=5)
                if response.status_code == 200:
                    logger.info("DeepSeek-OCR server is healthy and ready",
                               attempt=attempt + 1,
                               response_time=response.elapsed.total_seconds())
                    break
                else:
                    logger.warning("Server health check failed",
                                 status_code=response.status_code,
                                 attempt=attempt + 1)
            except requests.exceptions.RequestException as e:
                logger.info("Server not ready yet, waiting...",
                           attempt=attempt + 1,
                           error=str(e))
            
            time.sleep(check_interval)
        else:
            # Server didn't start properly
            logger.error("DeepSeek-OCR server failed to start within timeout")
            
            # Get error output
            stdout, stderr = process.communicate(timeout=10)
            if stderr:
                logger.error("Server stderr output", stderr=stderr[-1000:])  # Last 1000 chars
            
            raise RuntimeError("Server failed to start within timeout period")
        
        # Keep the function running
        logger.info("DeepSeek-OCR server is running, keeping function alive")
        process.wait()
        
    except Exception as e:
        logger.error("Failed to start DeepSeek-OCR server", error=str(e), error_type=type(e).__name__)
        
        # Clean up process if it exists
        if 'process' in locals() and process.poll() is None:
            process.terminate()
            process.wait()
            
        # Re-raise the error
        raise RuntimeError(f"Failed to start DeepSeek-OCR server: {str(e)}")
    
    finally:
        logger.info("DeepSeek-OCR server function ending")

@app.function(
    image=image,
    gpu="L4",
    timeout=60,
    volumes={"/root/.cache/huggingface": hf_cache_vol}
)
def health_check() -> dict:
    """Health check endpoint for the GPU service."""
    import structlog
    import requests
    import time
    
    logger = structlog.get_logger(__name__)
    
    try:
        logger.info("Performing health check for DeepSeek-OCR GPU service")
        
        # Multiple health check endpoints
        health_endpoints = [
            "http://localhost:8000/health",
            "http://localhost:8000/v1/health",
            "http://localhost:8000/healthz"
        ]
        
        for endpoint in health_endpoints:
            try:
                logger.debug("Trying health endpoint", endpoint=endpoint)
                response = requests.get(endpoint, timeout=10)
                
                if response.status_code == 200:
                    health_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                    
                    logger.info("Health check successful", endpoint=endpoint, response_time=response.elapsed.total_seconds())
                    return {
                        "status": "healthy",
                        "service": "deepseek-ocr-gpu-optimized",
                        "endpoint": endpoint,
                        "gpu": "L4",
                        "response_time": response.elapsed.total_seconds(),
                        "health_data": health_data
                    }
                else:
                    logger.warning("Health endpoint returned non-200 status",
                                 endpoint=endpoint,
                                 status_code=response.status_code)
                    
            except requests.exceptions.RequestException as e:
                logger.debug("Health endpoint failed", endpoint=endpoint, error=str(e))
                continue  # Try next endpoint
        
        # If no endpoints worked, check if server is starting up
        logger.error("All health endpoints failed", endpoints_tried=len(health_endpoints))
        return {
            "status": "unhealthy",
            "error": "No health endpoints responded",
            "service": "deepseek-ocr-gpu-optimized",
            "gpu": "L4",
            "endpoints_tried": health_endpoints
        }
        
    except Exception as e:
        logger.error("Health check failed with unexpected error", error=str(e), error_type=type(e).__name__)
        return {
            "status": "unhealthy",
            "error": str(e),
            "error_type": type(e).__name__,
            "service": "deepseek-ocr-gpu-optimized",
            "gpu": "L4"
        }

# Local entry point for testing
if __name__ == "__main__":
    with app.run():
        result = health_check.remote()
        print(f"Health check: {result}")