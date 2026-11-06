# backend/main.py
import os
import re
import json
import io
import time
from fastapi import FastAPI, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import spacy
from sentence_transformers import SentenceTransformer, util
from google import genai
from google.genai import types
from dotenv import load_dotenv
import pdfplumber
from docx import Document

from skills import (
    TECH_SKILLS_DICT, find_skills, normalize_skill, expand_with_groups, display_name,
)

# Cosine-similarity cut-off for "this resume skill is semantically close enough".
# Calibrated: truly related skills (React≈React.js) score ~0.6-0.9,
# somewhat related (Python≈Java) ~0.4-0.55, unrelated ~0.03-0.35.
SEMANTIC_THRESHOLD = 0.55

# Load environment variables from .env file
load_dotenv()

# --- 1. Load ML Models at Startup ---
print("Loading ML Model 1: spaCy NER...")
nlp = spacy.load("en_core_web_sm")
print("✅ ML Model 1 Loaded!")

print("Loading ML Model 2: Sentence-Transformers...")
model_semantic = SentenceTransformer('all-MiniLM-L6-v2')
# Pre-compute embeddings for every known skill ONCE (also warms the model up).
# Per-request work then only encodes the resume side.
SKILL_EMB = model_semantic.encode(TECH_SKILLS_DICT, convert_to_tensor=True)
SKILL_INDEX = {skill: i for i, skill in enumerate(TECH_SKILLS_DICT)}
print("✅ ML Model 2 Loaded! (skill embeddings cached)")

print("Loading ML Model 3: Gemini API...")
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    gemini_client = genai.Client(api_key=api_key)
    GEMINI_MODEL_NAME = 'models/gemini-2.5-flash'
    # JSON mode removes markdown fences; thinking_budget=0 skips the slow "thinking" phase.
    # (If your google-genai version rejects ThinkingConfig, delete the thinking_config line.)
    GEMINI_CONFIG = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.7,
        max_output_tokens=2048,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    print(f"✅ ML Model 3 Loaded! (Using {GEMINI_MODEL_NAME})")
else:
    print("⚠️ WARNING: GEMINI_API_KEY not found in .env file!")
    gemini_client = None


def ask_gemini_json(prompt: str) -> dict:
    """Call Gemini and return its reply parsed as a Python dict."""
    response = gemini_client.models.generate_content(
        model=GEMINI_MODEL_NAME, contents=prompt, config=GEMINI_CONFIG
    )
    clean_text = response.text.replace("```json", "").replace("```", "").strip()
    return json.loads(clean_text)


# Initialize the FastAPI app
app = FastAPI(
    title="StepUp API",
    description="Backend for StepUp - AI Career Intelligence Platform",
    version="1.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Logs how long every request takes: use these numbers for the latency metric in the report.
@app.middleware("http")
async def log_request_time(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - start) * 1000
    print(f"⏱  {request.method} {request.url.path} -> {ms:.0f} ms")
    response.headers["X-Process-Time-ms"] = f"{ms:.0f}"
    return response


# --- 2. Data Models (Pydantic) ---
class ResumeTextRequest(BaseModel):
    text: str

class SkillMatchRequest(BaseModel):
    resume_skills: list[str]
    jd_text: str
    resume_text: str = ""

class BlueprintRequest(BaseModel):
    missing_skills: list[str]
    target_role: str
    matched_skills: list[str] = []
    jd_text: str = ""

class InterviewRequest(BaseModel):
    missing_skills: list[str]
    target_role: str
    matched_skills: list[str] = []
    jd_text: str = ""


# --- 3. API ROUTES ---

@app.get("/")
def read_root():
    return {"message": "Welcome to StepUp! The backend is alive."}

@app.get("/health")
def health_check():
    return {"status": "success", "message": "StepUp Backend is ready for ML models!"}


# --- FILE UPLOAD ENDPOINT ---
@app.post("/api/upload-resume")
async def upload_resume(file: UploadFile = File(...)):
    """
    Accepts PDF, DOCX, or TXT resume files and extracts text.
    """
    try:
        contents = await file.read()
        filename = file.filename.lower()
        extracted_text = ""

        if filename.endswith('.pdf'):
            with pdfplumber.open(io.BytesIO(contents)) as pdf:
                for page in pdf.pages:
                    text = page.extract_text(x_tolerance=2)
                    if text:
                        # Remove CID font references like (cid:131)
                        text = re.sub(r'\(cid:\d+\)', ' ', text)
                        extracted_text += text + "\n"
        elif filename.endswith('.docx'):
            doc = Document(io.BytesIO(contents))
            for paragraph in doc.paragraphs:
                extracted_text += paragraph.text + "\n"
        elif filename.endswith('.txt'):
            extracted_text = contents.decode('utf-8')
        else:
            return {
                "status": "error",
                "message": "Unsupported file format. Please upload PDF, DOCX, or TXT."
            }

        # Light cleanup: normalise whitespace (pdfplumber output is already clean)
        extracted_text = re.sub(r'[ \t]+', ' ', extracted_text)    # Collapse horizontal spaces
        extracted_text = re.sub(r'\n{3,}', '\n\n', extracted_text) # Collapse excessive blank lines
        extracted_text = extracted_text.strip()

        return {
            "status": "success",
            "filename": filename,
            "extracted_text": extracted_text
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to process file: {str(e)}"
        }


# --- BLOCK 2: ML MODEL 1 (NER) ENDPOINT ---
@app.post("/api/extract-entities")
def extract_entities(data: ResumeTextRequest):
    doc = nlp(data.text)
    companies = list(set([ent.text for ent in doc.ents if ent.label_ == "ORG"]))
    dates = list(set([ent.text for ent in doc.ents if ent.label_ == "DATE"]))
    people = list(set([ent.text for ent in doc.ents if ent.label_ == "PERSON"]))

    # Whole-word match against the full skills vocabulary (handles aliases like "Node.js", "k8s")
    found_skills = find_skills(data.text)

    return {
        "status": "success",
        "ml_model_used": "spaCy (en_core_web_sm)",
        "extracted_entities": {
            "companies_worked_at": companies,
            "experience_dates": dates,
            "names_found_for_anonymization": people
        },
        "skills_identified": found_skills
    }


# --- BLOCK 3: ML MODEL 2 (SEMANTIC MATCHING) ENDPOINT ---
@app.post("/api/match-skills")
def match_skills(data: SkillMatchRequest):
    # 1. Skills the job requires (whole-word match, aliases resolved)
    jd_skills = find_skills(data.jd_text)

    # 2. Skills the resume has: normalise aliases, then add implied broad concepts (aws -> cloud)
    resume_canon = {normalize_skill(s) for s in data.resume_skills if s.strip()}
    resume_covered = expand_with_groups(resume_canon)

    # 3. Overall semantic similarity between the resume skills and the full JD text
    resume_text = " ".join(data.resume_skills) if data.resume_skills else "none"
    emb_resume, emb_jd = model_semantic.encode([resume_text, data.jd_text], convert_to_tensor=True)
    overall_score = max(0.0, util.cos_sim(emb_resume, emb_jd).item() * 100)

    # 4. Per-skill decision: exact/alias/group match first, semantic similarity as fallback
    resume_list = sorted(resume_canon)
    emb_resume_skills = (
        model_semantic.encode(resume_list, convert_to_tensor=True) if resume_list else None
    )

    matched, missing, details = [], [], []
    for skill in jd_skills:
        if skill in resume_covered:
            matched.append(display_name(skill))
            details.append({"skill": display_name(skill), "status": "matched", "via": "exact/group"})
            continue

        best_sim = 0.0
        if emb_resume_skills is not None:
            best_sim = util.cos_sim(SKILL_EMB[SKILL_INDEX[skill]], emb_resume_skills)[0].max().item()

        if best_sim >= SEMANTIC_THRESHOLD:
            matched.append(display_name(skill))
            details.append({"skill": display_name(skill), "status": "matched",
                            "via": f"semantic ({best_sim:.2f})"})
        else:
            missing.append(display_name(skill))
            details.append({"skill": display_name(skill), "status": "missing",
                            "via": f"best similarity {best_sim:.2f}"})

    coverage = round(100 * len(matched) / len(jd_skills), 1) if jd_skills else 0.0

    # Composite ATS Score:
    # 70% weighted by concrete skill coverage (matched vs required skills)
    # 30% weighted by contextual semantic alignment across full text
    if jd_skills:
        ats_score = round((0.70 * coverage) + (0.30 * min(100.0, overall_score * 1.5)), 1)
    else:
        ats_score = round(min(100.0, overall_score * 1.5), 1)

    # Dynamic Profile Breakdown for Radar Chart (0-100 scale computed from actual resume data)
    resume_lower = data.resume_text.lower() if data.resume_text else ""
    
    # 1. Technical Skills score: tied directly to skill coverage
    tech_score = int(coverage) if jd_skills else int(min(100.0, overall_score * 1.4))

    # 2. Experience score: check experience indicators, projects, internships, years
    exp_matches = len(re.findall(r'\b(experience|intern|internship|project|developed|architected|built|engineered|spearheaded|led)\b', resume_lower))
    exp_score = min(95, max(35, 40 + exp_matches * 5))

    # 3. Education score: check degrees, universities, academic terms
    has_degree = bool(re.search(r'\b(bachelor|master|b\.e|b\.tech|m\.tech|bca|mca|degree|university|institute|college|cgpa|gpa)\b', resume_lower))
    edu_score = 85 if has_degree else 60

    # 4. Soft skills: check collaborative and organizational indicators
    soft_matches = len(re.findall(r'\b(collaborat|communicat|lead|mentor|agile|scrum|team|problem.solving|adapt|passionate|ownership)\b', resume_lower))
    soft_score = min(90, max(40, 45 + soft_matches * 6))

    # 5. Domain Knowledge: semantic alignment with target role/JD
    domain_score = int(min(95, max(30, overall_score * 1.6)))

    radar_breakdown = {
        "technical_skills": tech_score,
        "experience": exp_score,
        "education": edu_score,
        "soft_skills": soft_score,
        "domain_knowledge": domain_score
    }

    return {
        "status": "success",
        "ml_model_used": "Sentence-Transformers (all-MiniLM-L6-v2)",
        "ats_score": ats_score,
        "semantic_match_score": round(overall_score, 2),
        "skill_coverage": coverage,
        "threshold": SEMANTIC_THRESHOLD,
        "matched_skills": matched,
        "missing_skills": missing,
        "match_details": details,
        "radar_breakdown": radar_breakdown
    }


# --- BLOCK 4: ML MODEL 3 (GENERATIVE AI) ENDPOINT ---
@app.post("/api/generate-blueprint")
def generate_blueprint(data: BlueprintRequest):
    if not gemini_client:
        return {"status": "error", "message": "Gemini API Key is missing. Check your .env file."}

    skills_str = ", ".join(data.missing_skills) if data.missing_skills else "advanced specialization and system design"
    matched_str = ", ".join(data.matched_skills) if data.matched_skills else "fundamental programming skills"

    prompt = f"""
    You are an expert Senior Staff Software Architect and Career Coach.
    A candidate is targeting the role: '{data.target_role}'.
    Job Description context:
    \"\"\"{data.jd_text[:800]}\"\"\"

    Candidate background:
    - Already proven skills: {matched_str}
    - Critical skill gaps to bridge: {skills_str}

    Design a highly tailored, production-grade portfolio project specifically demonstrating mastery in these missing skills ({skills_str}) while leveraging their existing strengths.
    The project must be realistic, impressive to technical recruiters, and directly relevant to the target role '{data.target_role}'.

    YOU MUST RETURN ONLY VALID JSON. Do not include markdown formatting like ```json or any conversational text.

    Use this exact JSON structure:
    {{
      "project_name": "A catchy, professional, industry-grade project name",
      "description": "A concise 2-sentence description of the problem solved and core architecture",
      "core_features": ["Feature 1 highlighting a missing skill", "Feature 2 highlighting another gap", "Feature 3 on production-grade reliability"],
      "tech_stack": ["Tech 1", "Tech 2", "Tech 3"],
      "resume_bullet_point": "One powerful, metric-driven, ATS-friendly resume bullet point quantifying impact and architecture."
    }}
    """

    try:
        blueprint_data = ask_gemini_json(prompt)
        return {
            "status": "success",
            "ml_model_used": GEMINI_MODEL_NAME,
            "blueprint": blueprint_data
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# --- BLOCK 5: ML MODEL 3 (GENERATIVE AI) — INTERVIEW QUESTIONS ---
@app.post("/api/generate-interview")
def generate_interview(data: InterviewRequest):
    if not gemini_client:
        return {"status": "error", "message": "No API Key"}
    
    skills_str = ", ".join(data.missing_skills) if data.missing_skills else "advanced architecture and production troubleshooting"
    matched_str = ", ".join(data.matched_skills) if data.matched_skills else "core development"
    
    prompt = f"""
    You are a Lead Hiring Manager and Senior Technical Interviewer assessing a candidate for a '{data.target_role}' position.
    Job Description Context:
    \"\"\"{data.jd_text[:800]}\"\"\"

    Candidate skill assessment:
    - Proven skills: {matched_str}
    - Specific skill gaps: {skills_str}

    Generate exactly 3 challenging, realistic interview questions specifically testing the candidate on their gap areas ({skills_str}) within the practical context of a '{data.target_role}'.
    Include realistic scenario-based problems (e.g. system design tradeoffs, debugging edge cases, or architecture decisions).
    For each question, provide a structured 'Hint' explaining what concepts an interviewer wants to hear.

    Return ONLY valid JSON in this format:
    {{ "questions": [ {{ "q": "Question text", "hint": "Hint text" }} ] }}
    """
    try:
        return {"status": "success", "data": ask_gemini_json(prompt)}
    except Exception as e:
        return {"status": "error", "message": str(e)}