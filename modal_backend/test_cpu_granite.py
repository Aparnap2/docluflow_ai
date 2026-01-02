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

print(f"Testing CPU Granite Docling at: {BASE_URL}")

try:
    # Granite Docling is a multimodal model for document understanding
    # Using completion endpoint since llama.cpp server may expose it differently
    response = client.chat.completions.create(
        model="granite-docling",  # Model identifier
        messages=[
            {"role": "system", "content": "You are a document understanding engine. Extract structured information from the provided text."},
            {"role": "user", "content": "Extract structured fields from this invoice: \nInvoice #: INV-2024-001\nDate: 2024-01-15\nAmount: $1,250.50\nVendor: ABC Company"}
        ],
        max_tokens=512,
        temperature=0.1
    )

    print("\n✅ Success! Extraction Result:")
    print("-" * 40)
    print(response.choices[0].message.content)
    print("-" * 40)

except Exception as e:
    print(f"\n❌ Failed: {e}")
    print(f"   Error type: {type(e).__name__}")