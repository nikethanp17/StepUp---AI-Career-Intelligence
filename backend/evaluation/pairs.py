import requests
B = "http://127.0.0.1:8000"
pairs = [  # (resume skill, JD skill)
    ("azure", "aws"), ("gcp", "aws"), ("mysql", "postgresql"),
    ("react", "angular"), ("javascript", "typescript"),
    ("docker", "kubernetes"), ("html", "css"), ("python", "java"),
]
for r, j in pairs:
    res = requests.post(f"{B}/api/match-skills",
                        json={"resume_skills": [r], "jd_text": f"Required Skills: {j}"}).json()
    covered = j.title() not in res["missing_skills"]
    print(f"resume={r:12} jd={j:12} -> {'COVERED' if covered else 'missing'}")