import time, statistics, requests
B = "http://127.0.0.1:8000"
jd = "Job Title: Backend Dev\nRequired Skills: Python, AWS, Docker, SQL, Kubernetes"
resume = "Python developer with SQL and Git experience"
times = []
for _ in range(10):
    t = time.perf_counter()
    sk = requests.post(f"{B}/api/extract-entities", json={"text": resume}).json()["skills_identified"]
    m = requests.post(f"{B}/api/match-skills", json={"resume_skills": sk, "jd_text": jd}).json()
    requests.post(f"{B}/api/generate-blueprint",
                  json={"missing_skills": m["missing_skills"], "target_role": "Backend Developer"})
    times.append(time.perf_counter() - t)
print(f"mean {statistics.mean(times):.2f}s, median {statistics.median(times):.2f}s, max {max(times):.2f}s")