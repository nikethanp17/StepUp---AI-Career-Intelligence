from google import genai
from dotenv import load_dotenv
import os

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

print("Testing API Key:", api_key[:10] + "..." if api_key else "No Key Found!")

client = genai.Client(api_key=api_key)

try:
    # Using gemini-1.5-flash as it is the most stable and widely available
    response = client.models.generate_content(
        model='gemini-1.5-flash',
        contents='Say hello to Nikky in one sentence.'
    )
    print("✅ SUCCESS!")
    print("Response:", response.text)
except Exception as e:
    print("❌ ERROR:", str(e))