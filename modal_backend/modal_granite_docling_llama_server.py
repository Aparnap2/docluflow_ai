import modal
import os
import time
import socket
import subprocess
from huggingface_hub import hf_hub_download

APP_NAME = "docuflow-granite-docling-cpu"

MODEL_DIR = "/models/granite-gguf"
MODEL_FILE = "granite-docling-258M-Q4_K_M.gguf"
MMPROJ_FILE = "mmproj-granite-docling-258M-f16.gguf"

MODEL_REPO = "infl002/granite-docling-258M-GGUF"

PORT = 8000
MINUTES = 60

# Build llama.cpp from source with multimodal support
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "build-essential", "cmake", "wget", "curl", "libcurl4-openssl-dev")
    .run_commands(
        "git clone https://github.com/ggerganov/llama.cpp.git /opt/llama.cpp",
        "cd /opt/llama.cpp && mkdir build && cd build && cmake .. && make -j$(nproc) llama-server",
        "ln -s /opt/llama.cpp/build/bin/llama-server /usr/bin/llama-server",
    )
    .pip_install("huggingface-hub==0.24.7")
)

app = modal.App(APP_NAME)
model_volume = modal.Volume.from_name("granite-models-v2", create_if_missing=True)


def wait_port(host: str, port: int, timeout_s: int = 300) -> None:  # Increased timeout
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            with socket.create_connection((host, port), timeout=5):
                return
        except OSError:
            time.sleep(2)
    raise RuntimeError(f"Port did not open in {timeout_s}s: {host}:{port}")


@app.function(
    image=image,
    volumes={MODEL_DIR: model_volume},
    timeout=600,  # 10 minutes for download
)
def download_model():
    """Download Granite-Docling model to Modal volume."""
    print(f"Downloading {MODEL_REPO} to {MODEL_DIR}...")

    # Download the model file
    hf_hub_download(
        repo_id=MODEL_REPO,
        filename=MODEL_FILE,
        local_dir=MODEL_DIR,
        local_dir_use_symlinks=False,
    )

    # Download the multimodal projector file
    hf_hub_download(
        repo_id=MODEL_REPO,
        filename=MMPROJ_FILE,
        local_dir=MODEL_DIR,
        local_dir_use_symlinks=False,
    )

    model_volume.commit()
    print(f"✅ Model {MODEL_REPO} files downloaded and committed to volume")


@app.function(
    image=image,
    cpu=8.0,
    memory=16384,  # Increased memory for multimodal processing
    timeout=20 * MINUTES,
    container_idle_timeout=15 * MINUTES,
    volumes={MODEL_DIR: model_volume},
)
@modal.web_server(port=PORT, startup_timeout=300)  # 5 minute startup timeout
def serve():
    model_path = os.path.join(MODEL_DIR, MODEL_FILE)
    mmproj_path = os.path.join(MODEL_DIR, MMPROJ_FILE)

    # Check if model files exist
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model file not found: {model_path}")
    if not os.path.exists(mmproj_path):
        raise FileNotFoundError(f"MMProj file not found: {mmproj_path}")

    cmd = [
        "/usr/bin/llama-server",
        "--model", model_path,
        "--mmproj", mmproj_path,
        "--host", "0.0.0.0",
        "--port", str(PORT),
        "--n-gpu-layers", "0",  # CPU only
        "--threads", "6",  # Use 6 threads
        "--ctx-size", "4096",  # Context size
        "--batch-size", "512",  # Batch size
        "--n-parallel", "4",  # Parallel requests
    ]

    # Start the llama.cpp server process
    subprocess.Popen(cmd)
    wait_port("127.0.0.1", PORT, timeout_s=300)
    print("✅ Granite llama-server ready on port 8000.")