<div align="center">
  <img src="logo.png" alt="StepUp Logo" width="700"/>
  <h1>🚀 StepUp: AI Career Intelligence Platform</h1>
  <p><i>Your Career Starts Here.</i></p>
</div>

> **Transforming resume analysis from simple keyword matching to actionable, AI-driven career roadmaps.**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com/)
[![HTML5](https://img.shields.io/badge/Frontend-HTML5%20%2B%20Vanilla%20JS-orange.svg)](https://developer.mozilla.org/en-US/docs/Web/HTML)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 🌟 Overview

Traditional resume scanners (like Jobscan or ResumeGuru) rely on basic keyword counting, which encourages "keyword stuffing" and fails to understand context.

**StepUp** is a next-generation AI Career Intelligence Platform that uses a **3-Model Machine Learning Pipeline** to not only analyze resume-to-job-description fit but also generate personalized, actionable **"Proof-to-Job" Project Blueprints**. It doesn't just tell candidates what they're missing; it gives them the exact roadmap to learn it and prove it to recruiters.

---

## ✨ Key Features

- 📄 **Smart Document Parsing**: Automatically extracts and cleans text from PDF, DOCX, and TXT resumes.
- 🧠 **ML Model 1: Named Entity Recognition (NER)**: Uses `spaCy` to intelligently extract companies, dates, and technical skills.
- 🔗 **ML Model 2: Semantic Skill Matching**: Uses `Sentence-Transformers` (all-MiniLM-L6-v2) to calculate cosine similarity, understanding that "JS" and "JavaScript" are a match, drastically reducing false negatives.
- 🤖 **ML Model 3: Generative AI Blueprint**: Leverages `Google Gemini` to generate a customized weekend project, tech stack, and ATS-friendly resume bullet points to bridge identified skill gaps.
- 🎙️ **AI Mock Interviews**: Generates targeted interview questions with hints based on the user's specific skill gaps.
- 🎨 **Zero-Dependency Frontend**: A sleek, responsive, dual-theme (Light/Dark) dashboard built with pure HTML5, Vanilla JavaScript, Tailwind CSS (CDN), and Chart.js.

---

## 🏗️ Tech Stack

| Category             | Technologies                                      |
| :------------------- | :------------------------------------------------ |
| **Backend**          | Python, FastAPI, Uvicorn, Pydantic                |
| **Machine Learning** | spaCy, Sentence-Transformers, Scikit-Learn        |
| **Generative AI**    | Google Gemini API (`google-genai`)                |
| **Frontend**         | HTML5, Vanilla JavaScript, Tailwind CSS, Chart.js |
| **Utilities**        | `pypdf`, `python-docx`, `python-dotenv`           |

---

## ⚙️ How It Works (The Pipeline)

1. **Upload**: User uploads a resume (PDF/DOCX/TXT) and fills out a structured Job Description form.
2. **Extract**: Backend parses the document, cleans PDF artifacts, and uses `spaCy` to identify existing skills.
3. **Match**: `Sentence-Transformers` compares the resume skills against the JD requirements semantically, calculating a fit score and identifying true skill gaps.
4. **Generate**: `Gemini AI` takes the missing skills and target role to generate a structured, actionable project blueprint and mock interview questions.

---

## 🚀 Installation & Local Setup

### Prerequisites

- Python 3.10+
- A valid [Google Gemini API Key](https://makersuite.google.com/app/apikey)
- A modern web browser (Chrome, Firefox, Edge)

### 1. Backend Setup

```bash
# Navigate to the backend folder
cd backend

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Download the spaCy English model
python -m spacy download en_core_web_sm

# Create a .env file and add your API key
echo "GEMINI_API_KEY=your_actual_api_key_here" > .env

# Run the FastAPI server
uvicorn main:app --reload
```

### 2. Frontend Setup

```bash
No build tools or npm required!
Simply open the index.html file located in the root directory in your web browser, or use a lightweight local server like the VS Code Live Server extension for the best experience.
```

📚 Academic & Research Alignment

This project architecture is directly inspired by recent advancements in AI-driven recruitment:
SMART-HIRING Framework: Utilizes NER for structural parsing and semantic embeddings for contextual matching.
H3S (Hybrid Semantic-Structural Skill) Model: Validates the use of transformer-based embeddings over traditional TF-IDF/BM25 keyword matching to reduce bias and false negatives in candidate screening.

🔮 Future Scope

Integration with LinkedIn API for one-click profile importing.
User authentication (JWT) and persistent dashboard history.
Multi-language resume support using multilingual transformer models.

👨‍💻 Author
nikethanp17

Built with ❤️ for the future of fair, actionable, and intelligent career development.
