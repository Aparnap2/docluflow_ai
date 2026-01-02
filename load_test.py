import modal

# 1. Define the Load Test Environment
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("locust==2.31.5")
)

app = modal.App("docuflow-load-test")

# --- CONFIG ---
# Target your GPU endpoint. No trailing slash.
TARGET_HOST = "https://YOUR_WORKSPACE--docuflow-deepseek-ocr-openai-serve.modal.run"
# ----------------

@app.function(image=image, timeout=60 * 60)
@modal.web_server(port=8089, startup_timeout=60)
def serve():
    import subprocess
    # Launches Locust Web UI on port 8089
    cmd = [
        "locust",
        "-f", "/root/locustfile.py",
        "--host", TARGET_HOST,
        "--web-host", "0.0.0.0",
        "--web-port", "8089"
    ]
    subprocess.Popen(cmd)


# 2. The Locust Test Definition (written to container)
locust_file_content = """
from locust import HttpUser, task, between
import json

class OCRUser(HttpUser):
    # Simulates a user waiting 2-5 seconds between documents
    wait_time = between(2, 5)

    @task
    def ocr_request(self):
        payload = {
            "model": "deepseek-ai/DeepSeek-OCR",
            "messages": [
                {"role": "system", "content": "You are an OCR engine."},
                {"role": "user", "content": "OCR this image: https://modal-public-assets.s3.amazonaws.com/golden-gate-bridge.jpg"}
            ],
            "max_tokens": 1024,
            "stream": False
        }
        
        # We expect a 200 OK. Timeout set high for OCR/LLM latency.
        with self.client.post("/v1/chat/completions", json=payload, catch_response=True, timeout=120) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status {response.status_code}: {response.text}")

"""

@app.function(image=image)
def setup_locust():
    # Write the locustfile to the container filesystem
    with open("/root/locustfile.py", "w") as f:
        f.write(locust_file_content)

@app.local_entrypoint()
def run():
    if "YOUR_WORKSPACE" in TARGET_HOST:
        print("❌ Error: You must update TARGET_HOST in load_test.py before running.")
        return

    # 1. Setup the file
    setup_locust.remote()
    print("✅ Locustfile created.")
    
    # 2. Tell user how to start
    print("\n🚀 READY TO LAUNCH!")
    print("Run this command to start the Locust UI:")
    print("------------------------------------------")
    print("modal serve load_test.py")
    print("------------------------------------------")