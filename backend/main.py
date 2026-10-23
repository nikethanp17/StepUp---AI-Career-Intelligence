# backend/main.py
import os
import re
import json
import io
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import spacy
from sentence_transformers import SentenceTransformer, util
from google import genai
from dotenv import load_dotenv
from pypdf import PdfReader
from docx import Document

TECH_SKILLS_DICT = [
    "python", "java", "javascript", "js", "react", "angular", "vue", "nodejs", "node.js",
    "sql", "postgresql", "mysql", "mongodb", "aws", "azure", "gcp", "docker", "kubernetes",
    "git", "figma", "adobe xd", "sketch", "html", "css", "tailwind", "typescript", "c++", "c#",
    "machine learning", "ai", "data science", "rest api", "graphql", "ci/cd", "agile", "scrum",
    "wireframing", "prototyping", "user research", "usability testing", "design systems", "responsive design"
]

# Load environment variables from .env file
load_dotenv()

# --- 1. Load ML Models at Startup ---
print("Loading ML Model 1: spaCy NER...")
nlp = spacy.load("en_core_web_sm")
print("✅ ML Model 1 Loaded!")

print("Loading ML Model 2: Sentence-Transformers...")
model_semantic = SentenceTransformer('all-MiniLM-L6-v2') 
print("✅ ML Model 2 Loaded!")

print("Loading ML Model 3: Gemini API...")
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    gemini_client = genai.Client(api_key=api_key)
    GEMINI_MODEL_NAME = 'models/gemini-2.5-flash' 
    print(f"✅ ML Model 3 Loaded! (Using {GEMINI_MODEL_NAME})")
else:
    print("⚠️ WARNING: GEMINI_API_KEY not found in .env file!")
    gemini_client = None

# Initialize the FastAPI app
app = FastAPI(
    title="StepUp API",
    description="Backend for StepUp - AI Career Intelligence Platform",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 2. Data Models (Pydantic) ---
class ResumeTextRequest(BaseModel):
    text: str

class SkillMatchRequest(BaseModel):
    resume_skills: list[str]
    jd_text: str

class BlueprintRequest(BaseModel):
    missing_skills: list[str]
    target_role: str

# --- 3. API ROUTES ---

@app.get("/")
def read_root():
    return {"message": "Welcome to StepUp! The backend is alive."}

@app.get("/health")
def health_check():
    return {"status": "success", "message": "StepUp Backend is ready for ML models!"}

# --- NEW: FILE UPLOAD ENDPOINT ---
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
            pdf_reader = PdfReader(io.BytesIO(contents))
            for page in pdf_reader.pages:
                text = page.extract_text()
                if text:
                    # Remove weird PDF artifacts and ligatures
                    text = text.replace('ﬁ', 'fi').replace('ﬂ', 'fl').replace('ﬀ', 'ff')
                    text = text.replace('¶', '').replace('§', '').replace('†', '')
                    text = text.replace('–', '-').replace('—', '-')
                    # Remove non-printable characters but keep basic punctuation
                    text = ''.join(c for c in text if ord(c) < 128 or c in '•·')
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
        
        # Clean up weird PDF/DOCX extraction artifacts
        extracted_text = re.sub(r'[^\x00-\x7F]+', ' ', extracted_text)  # Remove non-ASCII
        extracted_text = re.sub(r'\s+', ' ', extracted_text).strip()    # Normalise whitespace

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
    
    common_skills = ["python", "java", "react", "sql", "aws", "machine learning", "api", "git", "docker", "nodejs"]
    found_skills = [skill for skill in common_skills if skill in data.text.lower()]

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
    # 1. Extract ONLY real tech/design skills from the JD text
    jd_text_lower = data.jd_text.lower()
    jd_skills_found = [skill for skill in TECH_SKILLS_DICT if skill in jd_text_lower]
    
    # 2. Normalize resume skills to lowercase for better matching
    resume_skills_lower = [skill.lower() for skill in data.resume_skills]
    
    # 3. Calculate Overall Semantic Match Score
    resume_text = " ".join(data.resume_skills)
    emb_resume = model_semantic.encode(resume_text, convert_to_tensor=True)
    emb_jd = model_semantic.encode(data.jd_text, convert_to_tensor=True)
    overall_score = util.cos_sim(emb_resume, emb_jd).item() * 100
    
    # 4. Find Missing Skills
    missing_skills = []
    if jd_skills_found:
        # If resume is empty, use a dummy embedding to avoid errors
        emb_resume_list = model_semantic.encode(resume_skills_lower, convert_to_tensor=True) if resume_skills_lower else model_semantic.encode(["none"], convert_to_tensor=True)
        
        for jd_skill in jd_skills_found:
            emb_jd_skill = model_semantic.encode(jd_skill, convert_to_tensor=True)
            sims = util.cos_sim(emb_jd_skill, emb_resume_list)[0]
            max_sim = max(sims).item()
            # If the best semantic match is less than 65%, it's considered missing
            if max_sim < 0.65:
                missing_skills.append(jd_skill.title()) # Capitalize for display
                
    return {
        "status": "success",
        "ml_model_used": "Sentence-Transformers (all-MiniLM-L6-v2)",
        "semantic_match_score": round(overall_score, 2),
        "missing_skills": list(set(missing_skills)) # Remove duplicates
    }

# --- BLOCK 4: ML MODEL 3 (GENERATIVE AI) ENDPOINT ---
@app.post("/api/generate-blueprint")
def generate_blueprint(data: BlueprintRequest):
    if not gemini_client:
        return {"status": "error", "message": "Gemini API Key is missing. Check your .env file."}

    skills_str = ", ".join(data.missing_skills)
    
    prompt = f"""
    You are an expert AI Career Coach and Senior Technical Recruiter. 
    A student is applying for a '{data.target_role}' role.
    They are missing the following skills: {skills_str}.
    
    Generate a "Proof-to-Job" Project Blueprint to help them learn and prove these skills in one weekend.
    
    YOU MUST RETURN ONLY VALID JSON. Do not include markdown formatting like ```json or any conversational text.
    
    Use this exact JSON structure:
    {{
      "project_name": "A catchy, professional project name",
      "description": "A 2-sentence description of what the project does and the problem it solves",
      "core_features": ["Feature 1", "Feature 2", "Feature 3"],
      "tech_stack": ["Tech 1", "Tech 2", "Tech 3"],
      "resume_bullet_point": "One powerful, metric-driven, ATS-friendly bullet point they can add to their resume after completing this project."
    }}
    """
    
    try:
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL_NAME,
            contents=prompt
        )
        
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        blueprint_data = json.loads(clean_text)
        
        return {
            "status": "success",
            "ml_model_used": GEMINI_MODEL_NAME,
            "blueprint": blueprint_data
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

# --- BLOCK 5: ML MODEL 3 (GENERATIVE AI) — INTERVIEW QUESTIONS ---
class InterviewRequest(BaseModel):
    missing_skills: list[str]
    target_role: str

@app.post("/api/generate-interview")
def generate_interview(data: InterviewRequest):
    if not gemini_client:
        return {"status": "error", "message": "No API Key"}
    prompt = (
        f"You are a strict technical interviewer for a {data.target_role} role. "
        f"The candidate is missing these skills: {', '.join(data.missing_skills)}. "
        "Generate exactly 3 tough, realistic interview questions to test them on these gaps. "
        "For each question, provide a 'Hint' on how to answer it. "
        "Return ONLY valid JSON in this format: "
        '{ "questions": [ { "q": "Question text", "hint": "Hint text" } ] }'
    )
    try:
        response = gemini_client.models.generate_content(model=GEMINI_MODEL_NAME, contents=prompt)
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        return {"status": "success", "data": json.loads(clean_text)}
    except Exception as e:
        return {"status": "error", "message": str(e)}