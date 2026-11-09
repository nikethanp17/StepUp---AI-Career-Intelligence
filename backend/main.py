# backend/main.py
import os
import re
import json
import time
from fastapi import FastAPI, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import spacy
from sentence_transformers import SentenceTransformer, util
from google import genai
from google.genai import types
from dotenv import load_dotenv

from skills import (
    TECH_SKILLS_DICT, find_skills, normalize_skill, expand_with_groups, display_name,
)
from resume_validator import (
    authenticate_resume_file, validate_resume_text, ResumeValidationError,
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
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash")
if api_key:
    gemini_client = genai.Client(api_key=api_key)
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

# In-memory caches for Gemini generation keyed by (target_role, sorted missing skills, jd_text)
_BLUEPRINT_CACHE: dict = {}
_INTERVIEW_CACHE: dict = {}


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
    text: str = Field(..., max_length=100000)

class ValidateTextRequest(BaseModel):
    text: str = Field(..., max_length=100000)

class SkillMatchRequest(BaseModel):
    resume_skills: list[str] = Field(default=[], max_length=200)
    jd_text: str = Field(..., max_length=50000)
    resume_text: str = Field(default="", max_length=100000)
    required_skills: list[str] = Field(default=[], max_length=50)

class BlueprintRequest(BaseModel):
    missing_skills: list[str] = Field(default=[], max_length=50)
    target_role: str = Field(..., max_length=200)
    matched_skills: list[str] = Field(default=[], max_length=50)
    jd_text: str = Field(default="", max_length=50000)

class InterviewRequest(BaseModel):
    missing_skills: list[str] = Field(default=[], max_length=50)
    target_role: str = Field(..., max_length=200)
    matched_skills: list[str] = Field(default=[], max_length=50)
    jd_text: str = Field(default="", max_length=50000)


# --- 3. API ROUTES ---

@app.get("/")
def read_root():
    return {"message": "Welcome to StepUp! The backend is alive."}

@app.get("/health")
def health_check():
    return {"status": "success", "message": "StepUp Backend is ready for ML models!"}


# --- FILE UPLOAD ENDPOINT (with resume validation) ---
@app.post("/api/upload-resume")
async def upload_resume(file: UploadFile = File(...)):
    """
    Accepts PDF, DOCX, or TXT resume files.
    Validates the file (size, type, content) and extracts text.
    Returns HTTP 200 with status:'error' on failure (frontend reads this).
    """
    try:
        result = await authenticate_resume_file(file)
        return {
            "status": "success",
            "filename": file.filename,
            "extracted_text": result["text"],
            "validation": {
                "file_type": result["file_type"],
                "confidence": result["confidence"],
                "checks": result["checks"],
            }
        }
    except ResumeValidationError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": f"Failed to process file: {str(e)}"}


# --- PASTED TEXT VALIDATION ENDPOINT ---
class ValidateTextRequest(BaseModel):
    text: str

@app.post("/api/validate-text")
def validate_text(data: ValidateTextRequest):
    """Validate pasted resume text (min length + resume-likeness)."""
    try:
        result = validate_resume_text(data.text)
        return {
            "status": "success",
            "extracted_text": result["text"],
            "validation": {
                "file_type": result["file_type"],
                "confidence": result["confidence"],
                "checks": result["checks"],
            }
        }
    except ResumeValidationError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": f"Text validation failed: {str(e)}"}


# --- BLOCK 2: ML MODEL 1 (NER) ENDPOINT ---
@app.post("/api/extract-entities")
def extract_entities(data: ResumeTextRequest):
    doc = nlp(data.text)
    companies = list(set([ent.text for ent in doc.ents if ent.label_ == "ORG"]))
    dates = list(set([ent.text for ent in doc.ents if ent.label_ == "DATE"]))
    people = list(set([ent.text for ent in doc.ents if ent.label_ == "PERSON"]))

    # Whole-word match against the full skills vocabulary (handles aliases like "Node.js", "k8s")
    found_skills = find_skills(data.text)
    skills_disp = [display_name(s) for s in found_skills]

    return {
        "status": "success",
        "ml_model_used": "spaCy (en_core_web_sm)",
        "extracted_entities": {
            "companies_worked_at": companies,
            "experience_dates": dates,
            "names_found_for_anonymization": people
        },
        "skills_identified": found_skills,
        "skills_display": skills_disp
    }


# --- BLOCK 3: ML MODEL 2 (SEMANTIC MATCHING) ENDPOINT ---
@app.post("/api/match-skills")
def match_skills(data: SkillMatchRequest):
    # 1. Build jd_skills:
    # If required_skills is non-empty, use only required_skills (skip find_skills entirely).
    # Otherwise, run find_skills ONLY on the Responsibilities text (not Company/Title).
    original_skills_map = {}
    jd_skills = []
    seen = set()

    has_required = any(s.strip() for s in data.required_skills) if data.required_skills else False
    if has_required:
        for s in data.required_skills:
            s_clean = s.strip()
            if not s_clean:
                continue
            canon = normalize_skill(s_clean)
            if canon not in seen:
                seen.add(canon)
                jd_skills.append(canon)
                original_skills_map[canon] = s_clean
    else:
        # Run find_skills only on the Responsibilities section of jd_text
        jd_text = data.jd_text
        resp_match = re.search(
            r'(?:responsibilities|key responsibilities|duties)[:\s]*(.*?)(?=(?:required skills|requirements|qualifications|$))',
            jd_text,
            re.IGNORECASE | re.DOTALL
        )
        target_text = resp_match.group(1).strip() if resp_match else jd_text
        for canon in find_skills(target_text):
            if canon not in seen:
                seen.add(canon)
                jd_skills.append(canon)

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
    resume_raw_text = data.resume_text or ""

    for skill in jd_skills:
        orig = original_skills_map.get(skill, skill)
        disp = display_name(skill, orig)
        if skill in resume_covered:
            matched.append(disp)
            details.append({"skill": disp, "status": "matched", "via": "exact/group"})
            continue

        # For required skills NOT in SKILL_INDEX, check whole-word presence in resume_text
        if skill not in SKILL_INDEX and resume_raw_text:
            search_terms = [orig]
            if orig.lower() != skill.lower():
                search_terms.append(skill)
            found_in_text = False
            for term in search_terms:
                if not term.strip():
                    continue
                escaped = re.escape(term.strip())
                pattern = rf'(?<![A-Za-z0-9+#.]){escaped}(?![A-Za-z0-9+#])'
                if re.search(pattern, resume_raw_text, re.IGNORECASE):
                    found_in_text = True
                    break
            if found_in_text:
                matched.append(disp)
                details.append({"skill": disp, "status": "matched", "via": "mentioned in resume text"})
                continue

        best_sim = 0.0
        if emb_resume_skills is not None:
            if skill in SKILL_INDEX:
                skill_emb = SKILL_EMB[SKILL_INDEX[skill]]
            else:
                skill_emb = model_semantic.encode(skill, convert_to_tensor=True)
            best_sim = util.cos_sim(skill_emb, emb_resume_skills)[0].max().item()

        if best_sim >= SEMANTIC_THRESHOLD:
            matched.append(disp)
            details.append({"skill": disp, "status": "matched",
                            "via": f"semantic ({best_sim:.2f})"})
        else:
            missing.append(disp)
            details.append({"skill": disp, "status": "missing",
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

    cache_key = (
        data.target_role.strip().lower(),
        tuple(sorted(s.strip().lower() for s in data.missing_skills)),
        data.jd_text.strip(),
    )
    if cache_key in _BLUEPRINT_CACHE:
        return {
            "status": "success",
            "ml_model_used": f"{GEMINI_MODEL_NAME} (cached)",
            "blueprint": _BLUEPRINT_CACHE[cache_key]
        }

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

    Design a highly tailored, production-grade portfolio project plan specifically demonstrating mastery in these missing skills ({skills_str}) while leveraging their existing strengths.
    The project plan must be realistic, impressive to technical recruiters, and directly relevant to the target role '{data.target_role}'.

    YOU MUST RETURN ONLY VALID JSON. Do not include markdown formatting like ```json or any conversational text.

    Use this exact JSON structure:
    {{
      "project_name": "A catchy, professional, industry-grade project name",
      "description": "A concise 2-sentence plan written in present/future tense (e.g. 'This project will build... It aims to solve...') describing the problem to be solved and the core architecture. It must be phrased as a proposed project plan, not an already completed project.",
      "core_features": ["Feature 1 highlighting a missing skill", "Feature 2 highlighting another gap", "Feature 3 on production-grade reliability"],
      "tech_stack": ["Tech 1", "Tech 2", "Tech 3"],
      "resume_bullet_point": "One powerful, metric-driven, ATS-friendly resume bullet point for when the project is completed. You MUST use bracketed placeholders like [X]%, [N]ms, or [N] users instead of invented numbers (e.g., 'Architected a distributed data pipeline with Python and Docker, reducing query latency by [X]% across [N] datasets.')."
    }}
    """

    try:
        blueprint_data = ask_gemini_json(prompt)
        _BLUEPRINT_CACHE[cache_key] = blueprint_data
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

    cache_key = (
        data.target_role.strip().lower(),
        tuple(sorted(s.strip().lower() for s in data.missing_skills)),
        data.jd_text.strip(),
    )
    if cache_key in _INTERVIEW_CACHE:
        return {"status": "success", "data": _INTERVIEW_CACHE[cache_key]}

    skills_str = ", ".join(data.missing_skills) if data.missing_skills else "advanced architecture and production troubleshooting"
    matched_str = ", ".join(data.matched_skills) if data.matched_skills else "core development"

    prompt = f"""
    You are a Lead Hiring Manager and Senior Technical Interviewer assessing a candidate for a '{data.target_role}' position.
    Job Description Context:
    \"\"\"{data.jd_text[:800]}\"\"\"

    Candidate skill assessment:
    - Proven skills: {matched_str}
    - Specific skill gaps: {skills_str}

    Generate exactly 3 challenging, realistic interview questions specifically testing the candidate on their gap areas ({skills_str}).
    CRITICAL REQUIREMENTS:
    1. DOMAIN & CONTEXT: All questions and scenarios MUST stay strictly within the domain, industry, company context, and responsibilities described in the Job Description.
    2. PLAIN TEXT ONLY: DO NOT use markdown backticks or markdown formatting anywhere (no `code` formatting). Present code, SQL statements, and technical keywords inline in plain text without backticks.
    3. HINTS: For each question, provide a structured 'Hint' in plain text explaining what key concepts, architectural considerations, or tradeoffs an interviewer expects to hear.

    Return ONLY valid JSON in this format:
    {{ "questions": [ {{ "q": "Question text in plain text", "hint": "Hint text in plain text" }} ] }}
    """
    try:
        data_res = ask_gemini_json(prompt)
        _INTERVIEW_CACHE[cache_key] = data_res
        return {"status": "success", "data": data_res}
    except Exception as e:
        return {"status": "error", "message": str(e)}