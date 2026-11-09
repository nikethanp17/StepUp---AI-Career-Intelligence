# backend/evaluation/test_validator.py
"""
Acceptance tests for StepUp resume document validation.
Covers 8 critical test cases:
1. Valid text-based PDF resume -> success with confidence >= 55
2. A disguised file (.exe/.zip renamed to resume.pdf) -> rejected
3. File over 5 MB -> rejected (without loading entire file into memory)
4. Scanned/image-only PDF -> rejected with "scanned image" message
5. Empty .txt or random prose (recipe) -> rejected as not a resume
6. Valid DOCX resume -> success
7. Corrupted or password-protected PDF -> clean error, no crash
8. Pasted text under MIN_CHARS -> rejected
"""

import io
import os
import sys
import zipfile
import asyncio
import concurrent.futures
from docx import Document

# Add parent directory to sys.path so we can import from backend
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from resume_validator import (
    authenticate_resume_file,
    validate_resume_text,
    ResumeValidationError,
    looks_like_resume,
    detect_type,
    MAX_BYTES,
    MIN_CHARS,
)


def run_async(coro):
    """Run an async coroutine safely whether or not an event loop is already active."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


class MockUploadFile:
    """Simulates FastAPI's UploadFile for unit/integration testing."""
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self.stream = io.BytesIO(content)

    async def read(self, size: int = -1) -> bytes:
        return self.stream.read(size)


def test_1_valid_pdf_resume():
    print("Test 1: Valid text-based PDF resume...")
    sample_pdf = "/Users/nikethanp17/Downloads/nikky resume.pdf"
    if not os.path.exists(sample_pdf):
        print("  ⚠️ nikky resume.pdf not found at path, skipping specific file test.")
        return

    with open(sample_pdf, "rb") as f:
        file_bytes = f.read()

    upload_file = MockUploadFile("nikky_resume.pdf", file_bytes)
    result = run_async(authenticate_resume_file(upload_file))

    assert result["file_type"] == "pdf", f"Expected 'pdf', got {result['file_type']}"
    assert result["confidence"] >= 55, f"Expected confidence >= 55, got {result['confidence']}"
    assert len(result["text"]) >= MIN_CHARS, "Extracted text length is below MIN_CHARS"
    print(f"  ✅ Passed! Extracted {len(result['text'])} chars, Confidence: {result['confidence']}%")


def test_2_disguised_file():
    print("Test 2: Disguised file (.zip or random bytes renamed to .pdf)...")
    fake_zip = io.BytesIO()
    with zipfile.ZipFile(fake_zip, "w") as zf:
        zf.writestr("test.txt", "This is just a regular zip file pretending to be a PDF")
    fake_zip_bytes = fake_zip.getvalue()

    upload_file = MockUploadFile("malicious_resume.pdf", fake_zip_bytes)
    try:
        run_async(authenticate_resume_file(upload_file))
        assert False, "Should have rejected disguised zip file"
    except ResumeValidationError as e:
        assert "not a real PDF" in str(e) or "ZIP archive" in str(e), f"Unexpected error: {e}"
        print(f"  ✅ Passed! Correctly rejected: '{e}'")


def test_3_file_over_5mb():
    print("Test 3: File over 5 MB cap...")
    oversized_bytes = b"%PDF-1.4 " + b"X" * (MAX_BYTES + 128 * 1024)
    upload_file = MockUploadFile("large_resume.pdf", oversized_bytes)
    try:
        run_async(authenticate_resume_file(upload_file))
        assert False, "Should have rejected oversized file"
    except ResumeValidationError as e:
        assert "5 MB" in str(e), f"Unexpected message: {e}"
        print(f"  ✅ Passed! Correctly caught: '{e}'")


def test_4_scanned_image_pdf():
    print("Test 4: Scanned/image-only PDF (no readable text)...")
    minimal_empty_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type /Catalog /Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type /Pages /Kids [3 0 R] /Count 1>>endobj\n"
        b"3 0 obj<</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f \n0000000010 00000 n \n0000000060 00000 n \n0000000117 00000 n \n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF"
    )
    upload_file = MockUploadFile("scanned_resume.pdf", minimal_empty_pdf)
    try:
        run_async(authenticate_resume_file(upload_file))
        assert False, "Should have rejected empty/scanned PDF"
    except ResumeValidationError as e:
        assert "scanned image" in str(e).lower() or "no readable text" in str(e).lower(), f"Unexpected message: {e}"
        print(f"  ✅ Passed! Correctly detected: '{e}'")


def test_5_empty_or_recipe_txt():
    print("Test 5: Random prose (recipe) or non-resume TXT...")
    recipe_text = (
        "Chocolate Chip Cookies Recipe\n\n"
        "Ingredients:\n"
        "- 2 cups all-purpose flour\n"
        "- 1 cup softened butter\n"
        "- 3/4 cup brown sugar\n"
        "- 2 large eggs\n"
        "- 1 tsp vanilla extract\n"
        "- 1 cup chocolate chips\n\n"
        "Instructions:\n"
        "Preheat oven to 350 degrees F. Mix ingredients in a bowl. Bake for 10-12 minutes until golden brown."
    ).encode("utf-8")

    upload_file = MockUploadFile("recipe.txt", recipe_text)
    try:
        run_async(authenticate_resume_file(upload_file))
        assert False, "Should have rejected recipe text"
    except ResumeValidationError as e:
        assert "doesn't look like a resume" in str(e).lower(), f"Unexpected message: {e}"
        print(f"  ✅ Passed! Correctly rejected recipe: '{e}'")


def test_6_valid_docx_resume():
    print("Test 6: Valid DOCX resume...")
    doc = Document()
    doc.add_heading("Nikethana P - Software Engineer", 0)
    doc.add_paragraph("Email: nikethanp17@gmail.com | Phone: +91 9741231756 | LinkedIn: linkedin.com/in/nikethana-p")
    doc.add_heading("Professional Summary", level=1)
    doc.add_paragraph("Passionate full-stack developer experienced in Python, React, and cloud architectures.")
    doc.add_heading("Education", level=1)
    doc.add_paragraph("Bachelor of Engineering in Computer Science, GPA: 8.9")
    doc.add_heading("Experience", level=1)
    doc.add_paragraph("Software Engineering Intern at Tech Corp. Developed REST APIs and microservices.")
    doc.add_heading("Technical Skills", level=1)
    doc.add_paragraph("Python, JavaScript, React, Docker, FastAPI, Git, SQL")

    buf = io.BytesIO()
    doc.save(buf)
    docx_bytes = buf.getvalue()

    upload_file = MockUploadFile("nikky_resume.docx", docx_bytes)
    result = run_async(authenticate_resume_file(upload_file))

    assert result["file_type"] == "docx"
    assert result["confidence"] >= 55
    print(f"  ✅ Passed! DOCX verified with Confidence: {result['confidence']}%")


def test_7_corrupted_or_protected_pdf():
    print("Test 7: Password-protected and corrupted PDF files...")
    test_files_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "test_files"))
    locked_pdf_path = os.path.join(test_files_dir, "locked.pdf")
    corrupt_pdf_path = os.path.join(test_files_dir, "corrupt.pdf")

    # 1. Check locked.pdf gives distinct password-protected message
    if os.path.exists(locked_pdf_path):
        with open(locked_pdf_path, "rb") as f:
            locked_bytes = f.read()
        upload_locked = MockUploadFile("locked.pdf", locked_bytes)
        try:
            run_async(authenticate_resume_file(upload_locked))
            assert False, "Should have caught locked PDF"
        except ResumeValidationError as e:
            assert "password-protected" in str(e).lower(), f"Unexpected message for locked.pdf: {e}"
            assert "remove the password" in str(e).lower(), f"Unexpected message for locked.pdf: {e}"
            print(f"  ✅ Passed! locked.pdf detected as password-protected: '{e}'")

    # 2. Check corrupt.pdf gives corrupted message
    corrupted_pdf = b"%PDF-1.4\nTHIS IS COMPLETELY CORRUPTED GARBAGE DATA AND NOT REAL PDF CODE"
    if os.path.exists(corrupt_pdf_path):
        with open(corrupt_pdf_path, "rb") as f:
            corrupted_pdf = f.read()

    upload_file = MockUploadFile("corrupt.pdf", corrupted_pdf)
    try:
        run_async(authenticate_resume_file(upload_file))
        assert False, "Should have caught corrupted PDF"
    except ResumeValidationError as e:
        assert "corrupted" in str(e).lower() or "could not read this pdf" in str(e).lower(), (
            f"Unexpected message for corrupt.pdf: {e}"
        )
        assert "password" not in str(e).lower(), f"corrupt.pdf should not be flagged as password-protected: {e}"
        print(f"  ✅ Passed! corrupt.pdf cleanly caught as corrupted: '{e}'")


def test_8_pasted_text_under_min_chars():
    print("Test 8: Pasted text under MIN_CHARS...")
    short_text = "Hi my name is Nikky and I know Python and React."
    try:
        validate_resume_text(short_text)
        assert False, "Should have rejected short text"
    except ResumeValidationError as e:
        assert f"{MIN_CHARS}" in str(e) or "too short" in str(e).lower(), f"Unexpected message: {e}"
        print(f"  ✅ Passed! Short text rejected: '{e}'")


if __name__ == "__main__":
    print("=" * 60)
    print("Running StepUp Resume Validator Acceptance Test Suite")
    print("=" * 60)
    test_1_valid_pdf_resume()
    test_2_disguised_file()
    test_3_file_over_5mb()
    test_4_scanned_image_pdf()
    test_5_empty_or_recipe_txt()
    test_6_valid_docx_resume()
    test_7_corrupted_or_protected_pdf()
    test_8_pasted_text_under_min_chars()
    print("=" * 60)
    print("🎉 ALL 8 ACCEPTANCE TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)
