# backend/resume_validator.py
# Resume document validation helpers.
# Pure stdlib + pdfplumber + python-docx — no ML imports, so it stays fast and testable.

import io
import re
import zipfile

import pdfplumber
from docx import Document

# ── Constants ──────────────────────────────────────────────────────────────────
MAX_BYTES = 5 * 1024 * 1024        # 5 MB hard cap
MIN_CHARS = 150                     # Minimum characters for meaningful resume text
CHUNK = 64 * 1024                   # Read in 64 KB chunks to avoid loading huge files
ZIP_BOMB_LIMIT = 50 * 1024 * 1024   # 50 MB uncompressed limit for DOCX zip inspection


# ── Custom exception ──────────────────────────────────────────────────────────
class ResumeValidationError(Exception):
    """Carries a user-friendly message to send back in the API response."""
    pass


# ── Size-limited reader ───────────────────────────────────────────────────────
async def read_limited(file) -> bytes:
    """Read an UploadFile in chunks; abort as soon as size exceeds MAX_BYTES.
    Never loads the whole file into RAM if it is oversized."""
    buf = bytearray()
    while True:
        chunk = await file.read(CHUNK)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > MAX_BYTES:
            raise ResumeValidationError(
                "File is larger than 5 MB. Please upload a smaller resume."
            )
    return bytes(buf)


# ── Magic-byte file type detection ────────────────────────────────────────────
def detect_type(content: bytes) -> str:
    """Detect file type from actual bytes, ignoring the extension and browser Content-Type.
    Returns 'pdf', 'docx', 'txt', or raises ResumeValidationError."""

    # PDF: starts with %PDF-
    if content[:5] == b"%PDF-":
        return "pdf"

    # DOCX: a ZIP archive containing word/document.xml
    if content[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                # Guard against zip bombs: check total uncompressed size
                total_uncompressed = sum(info.file_size for info in zf.infolist())
                if total_uncompressed > ZIP_BOMB_LIMIT:
                    raise ResumeValidationError(
                        "This archive is suspiciously large. Upload a normal resume file."
                    )
                names = zf.namelist()
                if "word/document.xml" in names:
                    return "docx"
        except zipfile.BadZipFile:
            pass
        # It's a ZIP but not a DOCX — reject
        raise ResumeValidationError(
            "This file is not a real PDF, DOCX, or TXT. It appears to be a ZIP archive."
        )

    # TXT: no NUL bytes in the first 4096 bytes and decodes as UTF-8
    sample = content[:4096]
    if b"\x00" not in sample:
        try:
            content.decode("utf-8")
            return "txt"
        except UnicodeDecodeError:
            pass

    raise ResumeValidationError(
        "This file is not a real PDF, DOCX, or TXT. "
        "Please upload a genuine resume in one of these formats."
    )


# ── Text extraction (reuses the same logic from main.py) ─────────────────────
def extract_text(content: bytes, ftype: str) -> str:
    """Extract text from the file bytes based on detected type.
    Raises ResumeValidationError for corrupted or password-protected files."""

    text = ""

    if ftype == "pdf":
        try:
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text(x_tolerance=2)
                    if page_text:
                        # Remove CID font references like (cid:131)
                        page_text = re.sub(r'\(cid:\d+\)', ' ', page_text)
                        text += page_text + "\n"
        except Exception as e:
            # Detect password/encryption by exception type or message/repr
            is_password_protected = False
            try:
                from pdfminer.pdfdocument import PDFPasswordIncorrect, PDFEncryptionError
                if isinstance(e, (PDFPasswordIncorrect, PDFEncryptionError)):
                    is_password_protected = True
                for arg in getattr(e, "args", ()):
                    if isinstance(arg, (PDFPasswordIncorrect, PDFEncryptionError)):
                        is_password_protected = True
            except ImportError:
                pass

            err_details = f"{type(e).__name__} {e} {repr(e)}".lower()
            if is_password_protected or "password" in err_details or "encrypt" in err_details:
                raise ResumeValidationError(
                    "This PDF is password-protected. Remove the password and upload it again."
                )
            raise ResumeValidationError(
                "Could not read this PDF — it may be corrupted. "
                "Try re-saving or converting it."
            )

    elif ftype == "docx":
        try:
            doc = Document(io.BytesIO(content))
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
        except Exception:
            raise ResumeValidationError(
                "Could not read this DOCX — it may be corrupted. "
                "Try re-saving or converting it."
            )

    elif ftype == "txt":
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            raise ResumeValidationError(
                "Could not decode this text file. Please ensure it is UTF-8 encoded."
            )

    # Light cleanup: normalise whitespace
    text = re.sub(r'[ \t]+', ' ', text)       # Collapse horizontal spaces
    text = re.sub(r'\n{3,}', '\n\n', text)    # Collapse excessive blank lines
    text = text.strip()

    return text


# ── Resume-likeness heuristic ────────────────────────────────────────────────
# Section headings commonly found in resumes
_SECTION_KEYWORDS = [
    "education", "experience", "skills", "projects", "summary",
    "certifications", "internship", "achievements", "objective",
    "work history", "professional experience", "technical skills",
    "qualifications", "training", "awards", "publications",
]

# Compiled patterns for contact info
_EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
_PHONE_RE = re.compile(r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,5}[-.\s]?\d{3,5}')
_LINK_RE  = re.compile(r'(?:linkedin\.com|github\.com|gitlab\.com|bitbucket\.org)', re.IGNORECASE)


def looks_like_resume(text: str) -> tuple[bool, int, dict]:
    """Heuristic check: is this text plausibly a resume?
    Returns (is_valid, confidence_score_0_100, checks_dict)."""

    lower = text.lower()
    checks = {}

    # 1. Section keywords found
    found_sections = [kw for kw in _SECTION_KEYWORDS if kw in lower]
    checks["sections_found"] = found_sections
    section_count = len(found_sections)

    # 2. Contact information
    has_email = bool(_EMAIL_RE.search(text))
    has_phone = bool(_PHONE_RE.search(text))
    has_link  = bool(_LINK_RE.search(text))
    checks["has_email"] = has_email
    checks["has_phone"] = has_phone
    checks["has_profile_link"] = has_link

    # 3. Scoring: each section keyword is worth 8 points (max 56 from 7+),
    #    email +15, phone +12, profile link +8, length bonus up to +9
    score = min(56, section_count * 8)
    if has_email:
        score += 15
    if has_phone:
        score += 12
    if has_link:
        score += 8

    # Length bonus: longer resumes are more likely real (up to +9 for 1500+ chars)
    char_len = len(text)
    if char_len >= 1500:
        score += 9
    elif char_len >= 800:
        score += 5
    elif char_len >= 400:
        score += 2

    score = min(100, max(0, score))
    checks["confidence"] = score

    # Valid if at least 2 section keywords AND (email OR phone)
    is_valid = section_count >= 2 and (has_email or has_phone)

    return is_valid, score, checks


# ── Main file authentication pipeline ────────────────────────────────────────
async def authenticate_resume_file(file) -> dict:
    """Full validation pipeline: size → type → extract → min-length → resume-likeness.
    Returns {"text", "file_type", "confidence", "checks"} on success.
    Raises ResumeValidationError with a friendly message on failure."""

    # 1. Size check (chunked read)
    content = await read_limited(file)

    # 2. File type detection (magic bytes)
    ftype = detect_type(content)

    # 3. Text extraction
    text = extract_text(content, ftype)

    # 4. Minimum length check
    if len(text) < MIN_CHARS:
        if ftype == "pdf":
            raise ResumeValidationError(
                "No readable text found. This looks like a scanned image. "
                "Upload a text-based file or paste your resume text."
            )
        raise ResumeValidationError(
            "The file has very little text (under 150 characters). "
            "Upload a complete resume or paste the full text."
        )

    # 5. Resume-likeness check
    is_valid, confidence, checks = looks_like_resume(text)
    if not is_valid:
        raise ResumeValidationError(
            "This doesn't look like a resume (missing sections or contact info). "
            "Make sure your resume has at least an email/phone and sections like "
            "Education, Experience, or Skills."
        )

    return {
        "text": text,
        "file_type": ftype,
        "confidence": confidence,
        "checks": checks,
    }


# ── Pasted text validation ───────────────────────────────────────────────────
def validate_resume_text(text: str) -> dict:
    """Validate pasted resume text. Returns the same structure as authenticate_resume_file.
    Raises ResumeValidationError on failure."""

    text = text.strip()

    # Min length
    if len(text) < MIN_CHARS:
        raise ResumeValidationError(
            f"Text is too short ({len(text)} characters). "
            f"Please paste at least {MIN_CHARS} characters of your resume."
        )

    # Resume-likeness
    is_valid, confidence, checks = looks_like_resume(text)
    if not is_valid:
        raise ResumeValidationError(
            "This doesn't look like a resume (missing sections or contact info). "
            "Make sure your text has at least an email/phone and sections like "
            "Education, Experience, or Skills."
        )

    return {
        "text": text,
        "file_type": "text",
        "confidence": confidence,
        "checks": checks,
    }

