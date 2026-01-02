import os
from openai import OpenAI

# REPLACE THIS with your actual deployed URL from `modal deploy`
# Example: "https://your-workspace--docuflow-deepseek-ocr-openai-serve.modal.run"
BASE_URL = "https://ap3617180--docuflow-deepseek-ocr-openai-serve.modal.run"

if "YOUR_GPU" in BASE_URL:
    print("❌ Error: Please update BASE_URL with your deployed Modal GPU URL")
    exit(1)

# vLLM OpenAI-compatible server uses /v1
client = OpenAI(
    base_url=f"{BASE_URL}/v1",
    api_key="sk-dummy-key"  # vLLM ignores this unless auth is configured
)

print(f"Testing GPU DeepSeek-OCR at: {BASE_URL}")

try:
    response = client.chat.completions.create(
        model="deepseek-ai/DeepSeek-OCR",  # Updated model name to match implementation
        messages=[
            {"role": "system", "content": "You are an OCR engine. Return only extracted text."},
            {"role": "user", "content": [
                {"type": "text", "text": "OCR this image and return structured data:"},
                {"type": "image_url", "image_url": {"url": "https://modal-public-assets.s3.amazonaws.com/golden-gate-bridge.jpg"}}
            ]}
        ],
        max_tokens=512,
        temperature=0.1,
        stream=False
    )

    print("\n✅ Success! OCR Result:")
    print("-" * 40)
    result_content = response.choices[0].message.content
    print(result_content)
    print("-" * 40)
    
    # Verify the response format
    if result_content and len(result_content.strip()) > 0:
        print("✅ Response contains data")
        # Check if it looks like extracted text (OCR output)
        if len(result_content.strip()) > 10:  # At least some content
            print("✅ Response appears to contain OCR text data")
            # Check if it contains typical OCR elements
            if any(char.isdigit() for char in result_content) or any(word in result_content.lower() for word in ['golden', 'gate', 'bridge', 'california']):
                print("✅ Response contains recognizable text elements")
            else:
                print("⚠️  Response may not contain expected OCR content")
        else:
            print("⚠️  Response may be too short to be meaningful OCR output")
    else:
        print("❌ Response is empty")

except Exception as e:
    print(f"\n❌ Failed: {e}")
    print(f"   Error type: {type(e).__name__}")