import os
from openai import OpenAI

# REPLACE THIS with your actual deployed URL from `modal deploy`
# Example: "https://your-workspace--docuflow-granite-docling-cpu-serve.modal.run"
BASE_URL = "https://ap3617180--docuflow-granite-docling-cpu-serve.modal.run"

if "YOUR_CPU" in BASE_URL:
    print("❌ Error: Please update BASE_URL with your deployed Modal CPU URL")
    exit(1)

# llama.cpp server provides an OpenAI compatible endpoint at /v1
client = OpenAI(
    base_url=f"{BASE_URL}/v1",
    api_key="sk-dummy-key"
)

print(f"Testing CPU Granite Docling (VLM) at: {BASE_URL}")

try:
    # Proper VLM Request: Image + Prompt
    # Granite Docling is a Visual Language Model designed for document images
    response = client.chat.completions.create(
        model="granite-docling",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Convert this page to docling. Extract structured information from the document image."}, # Required prompt
                    {
                        "type": "image_url",
                        "image_url": {"url": "https://modal-public-assets.s3.amazonaws.com/golden-gate-bridge.jpg"}
                    }
                ]
            }
        ],
        max_tokens=512,
        temperature=0.1
    )

    print("\n✅ Success! Result:")
    print("-" * 40)
    result_content = response.choices[0].message.content
    print(result_content)
    print("-" * 40)
    
    # Verify the response format
    if result_content and len(result_content.strip()) > 0:
        print("✅ Response contains data")
        # Check if it looks like structured data (contains JSON-like elements or markdown)
        if '{' in result_content or '|' in result_content or '#' in result_content:
            print("✅ Response appears to contain structured data")
        else:
            print("⚠️  Response may not contain structured data as expected")
    else:
        print("❌ Response is empty")

except Exception as e:
    print(f"\n❌ Failed: {e}")
    print(f"   Error type: {type(e).__name__}")