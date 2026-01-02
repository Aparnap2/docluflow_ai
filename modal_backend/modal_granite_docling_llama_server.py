import modal
import os
import time
import socket
import subprocess
from huggingface_hub import hf_hub_download

APP_NAME = "docuflow-granite-docling-cpu"

# FIX: Correct Repo ID (was 'infl002')
HF_REPO_ID = "infil00p/granite-docling-258M-GGUF"
MODEL_DIR = "/models/granite-gguf"
MODEL_FILE = "granite-docling-258M-Q4_K_M.gguf"
MMPROJ_FILE = "mmproj-granite-docling-258M-f16.gguf"

PORT = 8000
MINUTES = 60

image = (
    modal.Image.from_registry("python:3.11-slim")
    .apt_install("wget", "tar", "ca-certificates")
    .pip_install("huggingface_hub")  # Added for download_model
    .run_commands(
        # Install llama-server (llama.cpp)
        "wget -q -O /tmp/llama.tar.gz https://github.com/ggerganov/llama.cpp/releases/download/b4408/llama-b4408-bin-linux-x64-cpu_avx2.tar.gz",
        "tar -xzf /tmp/llama.tar.gz -C /tmp",
        "find /tmp -type f -name llama-server -exec mv {} /usr/local/bin/llama-server \\;",
        "chmod +x /usr/local/bin/llama-server",
    )
)

app = modal.App(APP_NAME)
model_volume = modal.Volume.from_name("granite-models-v2", create_if_missing=True)

# --- HELPER: Wait for Port ---
def wait_port(host: str, port: int, timeout_s: int = 180) -> None:
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            with socket.create_connection((host, port), timeout=1):
                return
        except OSError:
            time.sleep(1)
    raise RuntimeError(f"Port did not open in {timeout_s}s: {host}:{port}")

# --- SETUP: Download Model to Volume (Run Once) ---
@app.function(
    image=image,
    volumes={MODEL_DIR: model_volume},
    timeout=20 * MINUTES
)
def download_model():
    from huggingface_hub import hf_hub_download
    import shutil

    print(f"Downloading models from {HF_REPO_ID}...")

    # 1. Download Main Model (GGUF)
    print(f"Fetching {MODEL_FILE}...")
    path1 = hf_hub_download(repo_id=HF_REPO_ID, filename=MODEL_FILE)
    shutil.copy(path1, os.path.join(MODEL_DIR, MODEL_FILE))

    # 2. Download Vision Adapter (mmproj) - REQUIRED for Docling
    print(f"Fetching {MMPROJ_FILE}...")
    path2 = hf_hub_download(repo_id=HF_REPO_ID, filename=MMPROJ_FILE)
    shutil.copy(path2, os.path.join(MODEL_DIR, MMPROJ_FILE))

    print("✅ Download complete. Files saved to Volume.")
    print(os.listdir(MODEL_DIR))

# --- SERVER: Run llama-server ---
@app.function(
    image=image,
    cpu=8.0,
    memory=8192,
    timeout=30 * MINUTES,
    scaledown_window=10 * MINUTES, # Fixed param name
    volumes={MODEL_DIR: model_volume},
)
@modal.concurrent(max_inputs=20)
@modal.web_server(port=PORT, startup_timeout=15 * MINUTES)
def serve():
    model_path = os.path.join(MODEL_DIR, MODEL_FILE)
    mmproj_path = os.path.join(MODEL_DIR, MMPROJ_FILE)

    # Check if files exist (just in case download_model wasn't run)
    if not os.path.exists(model_path):
        print("⚠️ Model not found! Running download...")
        # Fallback download (slower on boot)
        subprocess.run(["huggingface-cli", "download", HF_REPO_ID, MODEL_FILE, "--local-dir", MODEL_DIR, "--local-dir-use-symlinks", "False"])
        subprocess.run(["huggingface-cli", "download", HF_REPO_ID, MMPROJ_FILE, "--local-dir", MODEL_DIR, "--local-dir-use-symlinks", "False"])

    cmd = [
        "/usr/local/bin/llama-server",
        "-m", model_path,
        "--mmproj", mmproj_path,
        "--host", "0.0.0.0",
        "--port", str(PORT),
        "--n-gpu-layers", "0", # Pure CPU
        "--threads", "8",
        "--ctx-size", "4096", # Context window for docs
        "--parallel", "4"     # Handle concurrent requests
    ]

    print("Starting llama-server...")
    subprocess.Popen(cmd)
    wait_port("127.0.0.1", PORT, timeout_s=180)
    print("✅ Granite llama-server ready on port 8000.")