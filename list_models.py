from google import genai
import os

API_KEY = os.environ.get("API_KEY")

if not API_KEY:
    raise ValueError("API_KEY is not set in environment variables")

client = genai.Client(api_key=API_KEY)

try:
    for model in client.models.list():
        print(f"Model: {model.name}, Supported: {model.supported_actions}")
except Exception as e:
    print("Error listing models:", e)
