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

# 1. Define Image (Pinned vLLM 0.6.3+ for DeepSeek-OCR support)
vllm_image = (
    modal.Image.from_registry("nvidia/cuda:12.4.1-devel-ubuntu22.04", add_python="3.11")
    .entrypoint([])
    .uv_pip_install(
        "vllm==0.6.3.post1",
        "huggingface-hub",
        "flashinfer-python",
        "pillow",
        "numpy<2",  # Avoids numpy 2.0 binary incompatibility
    )
    .env({"HF_XET_HIGH_PERFORMANCE": "1"})
)

# 2. Define Volumes (Persistent Cache)
hf_cache_vol = modal.Volume.from_name("huggingface-cache", create_if_missing=True)
vllm_cache_vol = modal.Volume.from_name("vllm-cache", create_if_missing=True)
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


# --- DOWNLOAD: Run this ONCE to pre-download weights to persistent volume ---
# Usage: modal run modal_backend/modal_deepseek_ocr_vllm.py::download_model
@app.function(
    image=vllm_image,
    volumes={MODEL_DIR: model_volume},
    timeout=60 * 20,
)
def download_model():
    print(f"Downloading {MODEL_NAME} to {MODEL_DIR}/deepseek-ocr...")
    snapshot_download(
        repo_id=MODEL_NAME,
        local_dir=f"{MODEL_DIR}/deepseek-ocr",
        local_dir_use_symlinks=False,
    )
    model_volume.commit()
    print(f"✅ Model {MODEL_NAME} downloaded and committed to volume")


# --- MAIN SERVER ---
@app.function(
    image=vllm_image,
    gpu=f"L4:{N_GPU}",  # Correct syntax
    scaledown_window=15 * MINUTES,  # Keep warm for 15 mins
    timeout=25 * MINUTES,
    volumes={
        MODEL_DIR: model_volume,  # Model volume
        "/root/.cache/huggingface": hf_cache_vol,
        "/root/.cache/vllm": vllm_cache_vol,
    },
    enable_memory_snapshot=True,
)
@modal.concurrent(max_inputs=16)
@modal.web_server(port=PORT, startup_timeout=25 * MINUTES)
def serve():
    # Use the model from the persistent volume
    model_path = f"{MODEL_DIR}/deepseek-ocr"

    cmd = [
        "vllm",
        "serve",
        "--uvicorn-log-level=info",
        model_path,  # Use model from persistent volume
        "--served-model-name",
        MODEL_NAME,
        "llm",
        "--host",
        "0.0.0.0",
        "--port",
        str(PORT),
    ]

    cmd += ["--enforce-eager" if FAST_BOOT else "--no-enforce-eager"]
    cmd += ["--tensor-parallel-size", str(N_GPU)]

    # DeepSeek-OCR specifics
    cmd += [
        "--no-enable-prefix-caching",
        "--mm-processor-cache-gb", "0",
        "--logits-processors", "vllm.model_executor.models.deepseek_ocr:NGramPerReqLogitsProcessor",
    ]

    subprocess.Popen(" ".join(cmd), shell=True)
    wait_port("127.0.0.1", PORT, timeout_s=900)
    print("✅ DeepSeek-OCR OpenAI server ready on port 8000 (/v1/*).")


# --- SMOKE TEST (Run locally to verify) ---
# Usage: modal run modal_backend/modal_deepseek_ocr_vllm.py
@app.local_entrypoint()
async def test():
    import aiohttp
    print(f"Spinning up server...")
    url = serve.web_url
    print(f"Server URL: {url}")

    async with aiohttp.ClientSession() as session:
        # 1. Health
        print("Checking health...")
        async with session.get(f"{url}/health", timeout=300) as resp:
            print(f"Health: {resp.status}")

        # 2. OCR Test
        print("Sending OCR request...")
        payload = {
            "model": MODEL_NAME,
            "messages": [
                {"role": "system", "content": "You are an OCR engine."},
                {"role": "user", "content": "OCR: https://modal-public-assets.s3.amazonaws.com/golden-gate-bridge.jpg"}
            ],
            "max_tokens": 100,
            "stream": False
        }
        async with session.post(f"{url}/v1/chat/completions", json=payload, timeout=300) as resp:
            if resp.status != 200:
                print(f"Error: {await resp.text()}")
            else:
                data = await resp.json()
                print(f"✅ Success! Output: {data['choices'][0]['message']['content'][:100]}...")

