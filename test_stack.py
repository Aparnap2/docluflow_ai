import asyncio
import os
import httpx
from openai import AsyncOpenAI

# --- CONFIG ---
# Replace with your actual URLs from 'modal deploy' output
GPU_BASE_URL = "https://YOUR_WORKSPACE--docuflow-deepseek-ocr-openai-serve.modal.run"
CPU_BASE_URL = "https://YOUR_WORKSPACE--docuflow-granite-docling-cpu-serve.modal.run"

# A stable public image for testing OCR
TEST_IMAGE = "https://modal-public-assets.s3.amazonaws.com/golden-gate-bridge.jpg"

async def test_gpu_deepseek():
    print(f"Testing GPU (DeepSeek-OCR) at {GPU_BASE_URL}...")
    client = AsyncOpenAI(base_url=f"{GPU_BASE_URL}/v1", api_key="sk-test")
    
    try:
        resp = await client.chat.completions.create(
            model="deepseek-ai/DeepSeek-OCR",
            messages=[
                {"role": "system", "content": "You are an OCR engine. Return only text."},
                {"role": "user", "content": f"OCR this image:\n{TEST_IMAGE}"}
            ],
            max_tokens=500
        )
        text = resp.choices[0].message.content
        print(f"✅ GPU Success! Length: {len(text)} chars")
        print(f"   Sample: {text[:50]}...")
        return text
    except Exception as e:
        print(f"❌ GPU Failed: {e}")
        return None

async def test_cpu_granite(input_text):
    print(f"\nTesting CPU (Granite Docling) at {CPU_BASE_URL}...")
    if not input_text:
        print("   Skipping CPU test (GPU failed to provide input).")
        return

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            # llama-server /completion endpoint
            payload = {
                "prompt": f"Extract JSON fields from:\n{input_text}",
                "n_predict": 256
            }
            resp = await client.post(f"{CPU_BASE_URL}/completion", json=payload)
            resp.raise_for_status()
            data = resp.json()
            # Handle different llama-server versions returning 'content' vs 'completion'
            result = data.get("content") or data.get("completion") or str(data)
            print(f"✅ CPU Success! Response length: {len(result)}")
            print(f"   Sample: {result[:50]}...")
        except Exception as e:
            print(f"❌ CPU Failed: {e}")

async def main():
    ocr_text = await test_gpu_deepseek()
    await test_cpu_granite(ocr_text)

if __name__ == "__main__":
    if "YOUR_WORKSPACE" in GPU_BASE_URL:
        print("⚠️  UPDATE THE URLs IN THE SCRIPT FIRST!")
    else:
        asyncio.run(main())