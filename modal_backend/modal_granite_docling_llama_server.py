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

# Build llama.cpp from source with CUDA support (for consistency with documentation)
LLAMA_CPP_RELEASE = "b4408"  # Use a stable release
cuda_version = "12.4.0"
flavor = "devel"
operating_sys = "ubuntu22.04"
tag = f"{cuda_version}-{flavor}-{operating_sys}"

image = (
    modal.Image.from_registry(f"nvidia/cuda:{tag}", add_python="3.12")
    .apt_install("git", "build-essential", "cmake", "curl", "libcurl4-openssl-dev")
    .run_commands("git clone https://github.com/ggerganov/llama.cpp")
    .run_commands(
        "cmake llama.cpp -B llama.cpp/build "
        "-DBUILD_SHARED_LIBS=OFF -DGGML_CUDA=OFF -DLLAMA_CURL=ON "  # CPU only version
    )
    .run_commands(  # this builds the necessary binaries
        "cmake --build llama.cpp/build --config Release -j --clean-first --target llama-server"
    )
    .run_commands("cp llama.cpp/build/bin/llama-* llama.cpp")
    .entrypoint([])  # remove NVIDIA base container entrypoint
)

# Use Modal Volumes for caching model weights
model_cache = modal.Volume.from_name("granite-models-v2", create_if_missing=True)
cache_dir = "/root/.cache/llama.cpp"

app = modal.App(APP_NAME)

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
    image=modal.Image.debian_slim(python_version="3.12").pip_install("huggingface-hub==0.36.0"),
    volumes={cache_dir: model_cache},
    timeout=30 * MINUTES
)
def download_model():
    from huggingface_hub import snapshot_download

    print(f"🦙 downloading model from {HF_REPO_ID} if not present")

    # Download both the model and the multimodal projector
    snapshot_download(
        repo_id=HF_REPO_ID,
        local_dir=cache_dir,
        allow_patterns=[MODEL_FILE, MMPROJ_FILE],
    )

    model_cache.commit()  # ensure other Modal Functions can see our writes before we quit

    print("✅ Model downloaded and committed to volume")

@app.function(
    image=image,
    cpu=8.0,
    memory=8192,
    scaledown_window=15 * MINUTES,  # how long should we stay up with no requests?
    timeout=10 * MINUTES,  # how long should we wait for container start?
    volumes={cache_dir: model_cache},
)
@modal.concurrent(  # how many requests can one replica handle? tune carefully!
    max_inputs=20
)
@modal.web_server(port=PORT, startup_timeout=10 * MINUTES)
def serve():
    model_path = os.path.join(cache_dir, MODEL_FILE)
    mmproj_path = os.path.join(cache_dir, MMPROJ_FILE)

    # llama-server command aligned with documentation best practices
    cmd = [
        "/llama.cpp/llama-server",
        "--model", model_path,
        "--mmproj", mmproj_path,
        "--host", "0.0.0.0",
        "--port", str(PORT),
        "--n-gpu-layers", "0",  # Pure CPU
        "--threads", "8",
        "--ctx-size", "4096",  # Context window for docs
        "--batch-size", "512",  # Batch size for processing
        "--parallel", "4",      # Handle concurrent requests
        "--log-disable",        # Reduce logging overhead
        # Additional parameters from documentation for better performance
        "--cache-type-k", "q4_0",
        "--cache-type-v", "q4_0",
    ]

    print(f"Starting llama-server with command: {' '.join(cmd)}")
    subprocess.Popen(cmd)
    wait_port("127.0.0.1", PORT, timeout_s=180)
    print("✅ Granite llama server ready on port 8000.")

