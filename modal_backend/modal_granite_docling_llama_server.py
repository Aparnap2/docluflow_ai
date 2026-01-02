import modal
import os
import time
import socket
import subprocess

APP_NAME = "docuflow-granite-docling-cpu"

HF_REPO_ID = "infil00p/granite-docling-258M-GGUF"
MODEL_DIR = "/models/granite-gguf"
MODEL_FILE = "granite-docling-258M-Q4_K_M.gguf"
MMPROJ_FILE = "mmproj-granite-docling-258M-f16.gguf"

PORT = 8000
MINUTES = 60

# Build llama.cpp from source to get latest Granite support
image = (
    modal.Image.from_registry("python:3.12-slim")
    .apt_install("git", "build-essential", "cmake", "wget", "libcurl4-openssl-dev")
    .pip_install("huggingface_hub")
    .run_commands(
        "git clone https://github.com/ggml-org/llama.cpp /root/llama.cpp",
        "cd /root/llama.cpp && cmake -B build -DGGML_NATIVE=OFF -DGGML_OPENMP=ON && cmake --build build --config Release -j $(nproc)",
        "cp /root/llama.cpp/build/bin/llama-server /usr/local/bin/llama-server"
    )
)

app = modal.App(APP_NAME)
model_volume = modal.Volume.from_name("granite-models-v2", create_if_missing=True)

def wait_port(host: str, port: int, timeout_s: int = 180) -> None:
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            with socket.create_connection((host, port), timeout=1):
                return
        except OSError:
            time.sleep(1)
    raise RuntimeError(f"Port did not open in {timeout_s}s: {host}:{port}")

@app.function(
    image=image,
    volumes={MODEL_DIR: model_volume},
    timeout=20 * MINUTES
)
def download_model():
    from huggingface_hub import hf_hub_download
    import shutil

    print(f"Downloading models from {HF_REPO_ID}...")
    path1 = hf_hub_download(repo_id=HF_REPO_ID, filename=MODEL_FILE)
    shutil.copy(path1, os.path.join(MODEL_DIR, MODEL_FILE))

    path2 = hf_hub_download(repo_id=HF_REPO_ID, filename=MMPROJ_FILE)
    shutil.copy(path2, os.path.join(MODEL_DIR, MMPROJ_FILE))
    print("✅ Download complete.")

@app.function(
    image=image,
    cpu=8.0,
    memory=8192,
    scaledown_window=15 * MINUTES,  # how long should we stay up with no requests?
    timeout=10 * MINUTES,  # how long should we wait for container start?
    volumes={MODEL_DIR: model_volume},
)
@modal.concurrent(  # how many requests can one replica handle? tune carefully!
    max_inputs=20
)
@modal.web_server(port=PORT, startup_timeout=10 * MINUTES)
def serve():
    model_path = os.path.join(MODEL_DIR, MODEL_FILE)
    mmproj_path = os.path.join(MODEL_DIR, MMPROJ_FILE)

    if not os.path.exists(model_path):
        subprocess.run(["huggingface-cli", "download", HF_REPO_ID, MODEL_FILE, "--local-dir", MODEL_DIR, "--local-dir-use-symlinks", "False"])
        subprocess.run(["huggingface-cli", "download", HF_REPO_ID, MMPROJ_FILE, "--local-dir", MODEL_DIR, "--local-dir-use-symlinks", "False"])

    # llama-server (latest build) with parameters aligned to documentation
    cmd = [
        "/usr/local/bin/llama-server",
        "--model", model_path,
        "--mmproj", mmproj_path,
        "--host", "0.0.0.0",
        "--port", str(PORT),
        "--n-gpu-layers", "0",  # Pure CPU
        "--threads", "8",
        "--ctx-size", "4096",  # Context window for docs
        "--batch-size", "512",  # Batch size for processing
        "--parallel", "4",      # Handle concurrent requests
        "--log-disable"         # Reduce logging overhead
    ]

    print("Starting compiled llama-server...")
    subprocess.Popen(cmd)
    wait_port("127.0.0.1", PORT, timeout_s=180)
    print("✅ Granite llama server ready on port 8000.")

