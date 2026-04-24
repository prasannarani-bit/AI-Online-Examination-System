from google import genai
import os

client = genai.Client(api_key="AIzaSyB7EDZN0rCy891KkgFtzcJFQZMZhhxB9oE")

try:
    for model in client.models.list():
        print(f"Model: {model.name}, Supported: {model.supported_actions}")
except Exception as e:
    print("Error listing models:", e)
