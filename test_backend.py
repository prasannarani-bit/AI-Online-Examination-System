import requests
import os

BASE_URL = "http://localhost:5000/api"

# 1. Login
login_res = requests.post(f"{BASE_URL}/login", json={
    "username": "john_faculty",
    "password": "password123"
})
token = login_res.json()['token']
headers = {"Authorization": f"Bearer {token}"}

# 2. Test Extract Paper
exam_id = 9
file_path = "c:/projects/AI_exam_system/sample_exam.txt"

with open(file_path, "rb") as f:
    files = {"file": f}
    res = requests.post(f"{BASE_URL}/faculty/exams/{exam_id}/extract_paper", headers=headers, files=files)
    print("Extract Paper Response Status:", res.status_code)
    print("Extract Paper Response JSON:", res.json())

# 3. Test Generate AI
with open(file_path, "rb") as f:
    files = {"file": f}
    data = {"num_questions": 2}
    res = requests.post(f"{BASE_URL}/faculty/exams/{exam_id}/generate_ai", headers=headers, files=files, data=data)
    print("Generate AI Response Status:", res.status_code)
    print("Generate AI Response JSON:", res.json())
