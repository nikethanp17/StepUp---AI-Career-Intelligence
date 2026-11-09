# backend/evaluation/test_skill_matching.py
"""
Backend tests for skill matching with required_skills field as source of truth.
"""

import os
import sys

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from resume_validator import extract_text
from skills import find_skills
from main import match_skills, SkillMatchRequest


def test_junior_data_scientist_required_skills_evaluation():
    """
    Test case from prompt:
    Job description 'Required Skills':
    'Python, SQL, Scikit-learn, TensorFlow, Tableau, Data Visualization, Statistical Analysis'
    Assert that exactly 7 evaluated skills (matched + missing == 7) are returned
    for valid_resume.pdf's skills.
    """
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    pdf_path = os.path.join(base_dir, "test_files", "valid_resume.pdf")

    assert os.path.exists(pdf_path), f"Test file not found: {pdf_path}"

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    text = extract_text(pdf_bytes, "pdf")
    resume_skills = find_skills(text)

    req_skills = [
        "Python",
        "SQL",
        "Scikit-learn",
        "TensorFlow",
        "Tableau",
        "Data Visualization",
        "Statistical Analysis"
    ]
    jd_text = (
        "Job Title: Junior Data Scientist\n"
        "Company: Analytics Corp\n"
        "Responsibilities: Analyze complex datasets and build statistical models.\n"
        "Required Skills: " + ", ".join(req_skills)
    )

    request = SkillMatchRequest(
        resume_skills=resume_skills,
        jd_text=jd_text,
        resume_text=text,
        required_skills=req_skills
    )

    result = match_skills(request)

    assert result["status"] == "success"
    matched = result["matched_skills"]
    missing = result["missing_skills"]
    total_evaluated = len(matched) + len(missing)

    assert total_evaluated == 7, (
        f"Expected exactly 7 evaluated skills, but got {total_evaluated}. "
        f"Matched: {matched}, Missing: {missing}"
    )

    # Verify all 7 requested skills are present in match_details
    evaluated_names = [d["skill"] for d in result["match_details"]]
    for expected in ["Python", "SQL", "Scikit-learn", "TensorFlow", "Tableau", "Data Visualization", "Statistical Analysis"]:
        assert expected in evaluated_names, f"Expected '{expected}' in evaluated skills: {evaluated_names}"


def test_required_skill_not_in_vocabulary_matched_via_resume_text():
    """
    (a) required 'Selenium' present in resume text -> matched via 'mentioned in resume text'
    """
    resume_text = "Experienced quality assurance engineer proficient in Selenium automated test suites."
    request = SkillMatchRequest(
        resume_skills=[],  # Selenium is not in find_skills vocabulary
        jd_text="Responsibilities: Run end-to-end testing.",
        resume_text=resume_text,
        required_skills=["Selenium"]
    )
    result = match_skills(request)
    assert "Selenium" in result["matched_skills"]
    assert len(result["missing_skills"]) == 0
    detail = next(d for d in result["match_details"] if d["skill"] == "Selenium")
    assert detail["via"] == "mentioned in resume text"


def test_homographs_produce_no_skills():
    """
    (b) 'Excel in teamwork' and 'Spring 2025' produce no skills
    """
    assert find_skills("Excel in teamwork") == []
    assert find_skills("Spring 2025") == []


def test_tfidf_does_not_match_tensorflow():
    """
    (c) 'TF-IDF' does not match TensorFlow
    """
    skills = find_skills("Implemented text vectorization using TF-IDF.")
    assert "tensorflow" not in skills


def test_skills_display_names():
    """
    (d) display names for AWS/SQL/Node.js in skills_display from /api/extract-entities
    """
    from main import extract_entities, ResumeTextRequest
    sample_text = "Proficient in AWS cloud, SQL queries, and Node.js backend development."
    res = extract_entities(ResumeTextRequest(text=sample_text))
    assert res["status"] == "success"
    assert "skills_display" in res
    for expected in ["AWS", "SQL", "Node.js"]:
        assert expected in res["skills_display"], f"Expected '{expected}' in {res['skills_display']}"


