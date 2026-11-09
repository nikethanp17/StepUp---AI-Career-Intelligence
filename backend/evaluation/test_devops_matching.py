# backend/evaluation/test_devops_matching.py
"""
Test skill matching for DevOps candidate resume (devops_resume.docx).
Evaluates Cases A, B, and C against the /api/match-skills endpoint.
"""

import os
import sys
import pytest
from fastapi.testclient import TestClient

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from resume_validator import extract_text
from skills import find_skills
from main import app

client = TestClient(app)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEVOPS_RESUME_PATH = os.path.join(BASE_DIR, "test_files", "devops_resume.docx")


@pytest.fixture(scope="module")
def devops_resume_data():
    """Extract text and skills from test_files/devops_resume.docx."""
    assert os.path.exists(DEVOPS_RESUME_PATH), f"File not found: {DEVOPS_RESUME_PATH}"
    with open(DEVOPS_RESUME_PATH, "rb") as f:
        doc_bytes = f.read()

    text = extract_text(doc_bytes, "docx")
    skills = find_skills(text)
    return {"text": text, "skills": skills}


def test_case_a_devops_core_skills(devops_resume_data):
    """
    Case A:
    required_skills = Docker, Kubernetes, Terraform, Jenkins, Linux, Cloud
    -> assert matched contains Docker, Kubernetes, Linux, Cloud;
       missing is exactly Terraform, Jenkins.
    Assert matched + missing == number of required skills (6).
    """
    req_skills = ["Docker", "Kubernetes", "Terraform", "Jenkins", "Linux", "Cloud"]
    payload = {
        "resume_skills": devops_resume_data["skills"],
        "jd_text": "Role: DevOps Engineer\nRequired Skills: " + ", ".join(req_skills),
        "resume_text": devops_resume_data["text"],
        "required_skills": req_skills,
    }

    res = client.post("/api/match-skills", json=payload)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"

    data = res.json()
    assert data["status"] == "success"

    matched = data["matched_skills"]
    missing = data["missing_skills"]

    # Assert matched contains Docker, Kubernetes, Linux, Cloud
    for skill in ["Docker", "Kubernetes", "Linux", "Cloud"]:
        assert skill in matched, f"Expected '{skill}' in matched skills: {matched}"

    # Assert missing is exactly Terraform, Jenkins
    assert set(missing) == {"Terraform", "Jenkins"}, (
        f"Expected missing to be exactly {{'Terraform', 'Jenkins'}}, got: {missing}"
    )

    # In all cases assert matched + missing == number of required skills
    assert len(matched) + len(missing) == len(req_skills), (
        f"Expected matched + missing to equal {len(req_skills)}, got {len(matched) + len(missing)}"
    )


def test_case_b_k8s_docker_alias_matching(devops_resume_data):
    """
    Case B:
    required_skills = k8s, Docker
    -> both matched.
    Assert matched + missing == number of required skills (2).
    """
    req_skills = ["k8s", "Docker"]
    payload = {
        "resume_skills": devops_resume_data["skills"],
        "jd_text": "Role: Container Specialist\nRequired Skills: " + ", ".join(req_skills),
        "resume_text": devops_resume_data["text"],
        "required_skills": req_skills,
    }

    res = client.post("/api/match-skills", json=payload)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"

    data = res.json()
    assert data["status"] == "success"

    matched = data["matched_skills"]
    missing = data["missing_skills"]

    # Assert both matched
    assert "k8s" in matched or "Kubernetes" in matched, f"Expected k8s in matched: {matched}"
    assert "Docker" in matched, f"Expected Docker in matched: {matched}"
    assert len(missing) == 0, f"Expected no missing skills, got: {missing}"

    # Assert matched + missing == number of required skills
    assert len(matched) + len(missing) == len(req_skills), (
        f"Expected matched + missing to equal {len(req_skills)}, got {len(matched) + len(missing)}"
    )


def test_case_c_data_science_skills_on_devops_resume(devops_resume_data):
    """
    Case C:
    the 7 data-science skills:
    Python, SQL, Scikit-learn, TensorFlow, Tableau, Data Visualization, Statistical Analysis
    -> Python matched, the other 6 missing.
    Assert matched + missing == number of required skills (7).
    """
    req_skills = [
        "Python",
        "SQL",
        "Scikit-learn",
        "TensorFlow",
        "Tableau",
        "Data Visualization",
        "Statistical Analysis",
    ]
    payload = {
        "resume_skills": devops_resume_data["skills"],
        "jd_text": "Role: Data Scientist\nRequired Skills: " + ", ".join(req_skills),
        "resume_text": devops_resume_data["text"],
        "required_skills": req_skills,
    }

    res = client.post("/api/match-skills", json=payload)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"

    data = res.json()
    assert data["status"] == "success"

    matched = data["matched_skills"]
    missing = data["missing_skills"]

    # Assert Python matched
    assert "Python" in matched, f"Expected 'Python' in matched skills: {matched}"
    assert len(matched) == 1, f"Expected only Python to be matched, got: {matched}"

    # The other 6 missing
    expected_missing = {
        "SQL",
        "Scikit-learn",
        "TensorFlow",
        "Tableau",
        "Data Visualization",
        "Statistical Analysis",
    }
    assert set(missing) == expected_missing, (
        f"Expected missing to be exactly {expected_missing}, got: {set(missing)}"
    )

    # In all cases assert matched + missing == number of required skills
    assert len(matched) + len(missing) == len(req_skills), (
        f"Expected matched + missing to equal {len(req_skills)}, got {len(matched) + len(missing)}"
    )

