import time
import socket
import subprocess
import modal
from huggingface_hub import snapshot_download

APP_NAME = "docuflow-deepseek-ocr-openai"

MODEL_NAME = "deepseek-ai/DeepSeek-OCR"
FAST_BOOT = True

N_GPU = 1
MINUTES = 60
PORT = 8000

vllm_image = (
    modal.Image.from_registry("nvidia/cuda:12.1.1-devel-ubuntu22.04", add_python="3.11")
    .apt_install("git", "wget", "curl", "build-essential")
    .pip_install(
        "vllm==0.6.3.post1",  # Updated to a more stable version
        "huggingface-hub==0.24.7",
        "torch==2.4.0",
        "transformers==4.44.2",
        "Pillow==10.4.0"
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)

hf_cache_vol = modal.Volume.from_name("huggingface-cache", create_if_missing=True)
model_volume = modal.Volume.from_name("deepseek-models", create_if_missing=True)
MODEL_DIR = "/models"

app = modal.App(APP_NAME)


def wait_port(host: str, port: int, timeout_s: int = 900) -> None:
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            with socket.create_connection((host, port), timeout=1):
                return
        except OSError:
            time.sleep(1)
    raise RuntimeError(f"Port did not open in {timeout_s}s: {host}:{port}")


@app.function(
    image=vllm_image,
    volumes={MODEL_DIR: model_volume},
    timeout=600,  # 10 minutes for download
)
def download_model():
    """Download DeepSeek-OCR model to Modal volume."""
    print(f"Downloading {MODEL_NAME} to {MODEL_DIR}/deepseek-ocr...")
    snapshot_download(
        repo_id=MODEL_NAME,
        local_dir=f"{MODEL_DIR}/deepseek-ocr",
        local_dir_use_symlinks=False,
    )
    model_volume.commit()
    print(f"✅ Model {MODEL_NAME} downloaded and committed to volume")


@app.function(
    image=vllm_image,
    gpu=modal.gpu.L4(count=1),
    scaledown_window=15 * MINUTES,
    timeout=30 * MINUTES,
    volumes={MODEL_DIR: model_volume, "/root/.cache/huggingface": hf_cache_vol},
    container_idle_timeout=20 * MINUTES,
    concurrency_limit=8,  # Reduced for stability
)
@modal.web_server(port=PORT, startup_timeout=300)  # 5 minute startup timeout
def serve():
    # vLLM serve command with DeepSeek-OCR specific parameters
    # Use the model from the persistent volume
    cmd = [
        "python", "-m", "vllm.entrypoints.openai.api_server",
        "--model", f"{MODEL_DIR}/deepseek-ocr",
        "--served-model-name", MODEL_NAME,
        "--host", "0.0.0.0",
        "--port", str(PORT),
        "--tensor-parallel-size", str(N_GPU),
        "--enforce-eager",  # Faster cold start
        "--gpu-memory-utilization", "0.9",  # Use 90% of GPU memory
        "--max-num-batched-tokens", "8192",  # Limit for cost control
        "--max-model-len", "4096",  # Limit context length
    ]

    # Start the vLLM server process
    subprocess.Popen(cmd)
    wait_port("127.0.0.1", PORT, timeout_s=900)
    print("✅ DeepSeek-OCR OpenAI server ready on port 8000 (/v1/*).")