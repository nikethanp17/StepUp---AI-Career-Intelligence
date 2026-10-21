from google import genai
from dotenv import load_dotenv
import os

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=api_key)

print("Checking available models for your API key...\n")

try:
    for model in client.models.list():
        # Just print the name to avoid attribute errors
        print(f"Model: {model.name}")
except Exception as e:
    print(f"Error listing models: {e}")