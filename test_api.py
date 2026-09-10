import requests
import time

API_URL = "http://localhost:8000/api/jobs"
# Python handles Arabic UTF-8 natively with no hassle
payload = {
    "input_types": ["scanned_journal"],
    "keywords": ["الامتحانات", "التربيه", "الوطنيه"],
    "file_path": "tests/01_safe_press_review_test.pdf"
}

print("1. Submitting job...")
response = requests.post(API_URL, json=payload)
job_data = response.json()
job_id = job_data["job_id"]
print(f"Job created! ID: {job_id}")

print("2. Polling for completion...")
while True:
    status_res = requests.get(f"{API_URL}/{job_id}")
    status_data = status_res.json()
    
    print(f"Status: {status_data['status']} | Progress: {status_data['progress']}% | Step: {status_data['current_step']}")
    
    if status_data['status'] in ['completed', 'failed']:
        print(f"\nFinal Result Path: {status_data.get('result_path')}")
        break
        
    time.sleep(3) # Wait 3 seconds before checking again