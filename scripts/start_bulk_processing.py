# -*- coding: utf-8 -*-
"""Start Bulk OCR Processing Job."""

import requests
import json

BASE_URL = "http://localhost:8000"

def main():
    # Login
    print("=== LOGIN ===")
    login_resp = requests.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"email": "admin@localhost.com", "password": "admin123"}
    )

    if login_resp.status_code != 200:
        print(f"Login fehlgeschlagen: {login_resp.text}")
        return

    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("Login erfolgreich!")

    # Check training stats
    print("\n=== TRAINING STATS ===")
    stats_resp = requests.get(
        f"{BASE_URL}/api/v1/training/stats/overview",
        headers=headers
    )
    if stats_resp.status_code == 200:
        stats = stats_resp.json()
        print(json.dumps(stats, indent=2, ensure_ascii=False))
    else:
        print(f"Stats Fehler: {stats_resp.status_code} - {stats_resp.text}")

    # Check existing jobs
    print("\n=== BESTEHENDE JOBS ===")
    jobs_resp = requests.get(
        f"{BASE_URL}/api/v1/training/bulk-processing/jobs",
        headers=headers
    )
    if jobs_resp.status_code == 200:
        jobs = jobs_resp.json()
        print(json.dumps(jobs, indent=2, ensure_ascii=False))

        # Check if a job is already running
        for job in jobs.get("jobs", []):
            if job.get("status") in ["pending", "running"]:
                print(f"\nJob '{job['job_name']}' laeuft bereits ({job['status']})")
                print(f"Progress: {job.get('processed_documents', 0)}/{job.get('total_documents', 0)}")
                return
    else:
        print(f"Jobs Fehler: {jobs_resp.status_code} - {jobs_resp.text}")

    # Start new bulk processing job
    print("\n=== STARTE NEUEN BULK PROCESSING JOB ===")
    job_data = {
        "name": "Initial Bulk OCR - All Backends",
        "backends": ["deepseek", "got_ocr", "surya_gpu", "surya_cpu"],
        "description": "Initiale OCR-Verarbeitung aller 9.997 Dokumente durch alle 4 Backends"
    }

    create_resp = requests.post(
        f"{BASE_URL}/api/v1/training/bulk-processing/jobs",
        headers=headers,
        json=job_data
    )

    if create_resp.status_code in [200, 201, 202]:
        result = create_resp.json()
        print("Job erfolgreich gestartet!")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Job Start fehlgeschlagen: {create_resp.status_code}")
        print(create_resp.text)


if __name__ == "__main__":
    main()
