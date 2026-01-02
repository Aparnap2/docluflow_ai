import time
import socket
import subprocess
import modal
from huggingface_hub import snapshot_download

APP_NAME = "docuflow-deepseek-ocr-openai"

MODEL_NAME = "deepseek-ai/DeepSeek-OCR"
# Use the specific model revision to avoid surprises when repos update
MODEL_REVISION = None  # DeepSeek-OCR doesn't typically use revisions
FAST_BOOT = True

N_GPU = 1
MINUTES = 60
VLLM_PORT = 8000

# Updated image to match documentation standards
vllm_image = (
    modal.Image.from_registry("nvidia/cuda:12.8.0-devel-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    .uv_pip_install(
        "vllm==0.11.2",
        "huggingface-hub==0.36.0",
        "flashinfer-python==0.5.2",
    )
    .env({"HF_XET_HIGH_PERFORMANCE": "1"})  # faster model transfers
)

# Use Modal Volumes for caching model weights and vLLM artifacts
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

@app.function(
    image=vllm_image,
    gpu=f"L4:{N_GPU}",
    scaledown_window=15 * MINUTES,  # how long should we stay up with no requests?
    timeout=10 * MINUTES,  # how long should we wait for container start?
    volumes={
        "/root/.cache/huggingface": hf_cache_vol,
        "/root/.cache/vllm": vllm_cache_vol,
    },
)
@modal.concurrent(  # how many requests can one replica handle? tune carefully!
    max_inputs=16
)
@modal.web_server(port=VLLM_PORT, startup_timeout=10 * MINUTES)
def serve():
    # Use the model from the persistent volume
    model_path = f"{MODEL_DIR}/deepseek-ocr"

    cmd = [
        "vllm",
        "serve",
        "--uvicorn-log-level=info",
        model_path,
        "--served-model-name",
        MODEL_NAME,
        "llm",
        "--host",
        "0.0.0.0",
        "--port",
        str(VLLM_PORT),
    ]

    # enforce-eager disables both Torch compilation and CUDA graph capture
    # default is no-enforce-eager. see the --compilation-config flag for tighter control
    cmd += ["--enforce-eager" if FAST_BOOT else "--no-enforce-eager"]

    # assume multiple GPUs are for splitting up large matrix multiplications
    cmd += ["--tensor-parallel-size", str(N_GPU)]

    # DeepSeek-OCR specific configurations
    cmd += [
        "--trust-remote-code",  # Required for DeepSeek-OCR's custom architecture
        "--max-model-len", "4096",  # Safe default to avoid OOM
    ]

    print(cmd)

    subprocess.Popen(" ".join(cmd), shell=True)

# --- SMOKE TEST (Run locally to verify) ---
# Usage: modal run modal_backend/modal_deepseek_ocr_vllm.py
@app.local_entrypoint()
async def test():
    import aiohttp
    import json
    url = serve.get_web_url()

    system_prompt = {
        "role": "system",
        "content": "You are an OCR engine. Return only extracted text.",
    }
    content = "OCR: https://modal-public-assets.s3.amazonaws.com/golden-gate-bridge.jpg"

    messages = [  # OpenAI chat format
        system_prompt,
        {"role": "user", "content": content},
    ]

    async with aiohttp.ClientSession(base_url=url) as session:
        print(f"Running health check for server at {url}")
        async with session.get("/health", timeout=9 * MINUTES) as resp:
            up = resp.status == 200
        assert up, f"Failed health check for server at {url}"
        print(f"Successful health check for server at {url}")

        print(f"Sending messages to {url}:", *messages, sep="\n\t")
        await _send_request(session, MODEL_NAME, messages)


async def _send_request(
    session: aiohttp.ClientSession, model: str, messages: list
) -> None:
    # `stream=True` tells an OpenAI-compatible backend to stream chunks
    payload = {"messages": messages, "model": model, "stream": False, "max_tokens": 500}

    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}

    async with session.post(
        "/v1/chat/completions", json=payload, headers=headers, timeout=1 * MINUTES
    ) as resp:
        resp.raise_for_status()
        response_data = await resp.json()
        print(f"✅ Success! Output: {response_data['choices'][0]['message']['content'][:100]}...")

