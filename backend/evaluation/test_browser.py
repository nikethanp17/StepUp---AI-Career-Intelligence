# backend/evaluation/test_browser.py
"""
Automated browser test suite for StepUp resume validation feature using Playwright.

Covers 8 end-to-end frontend behaviors:
1. fake_resume.pdf -> rejected with 'not a real PDF' message, file card reset
2. valid_resume.pdf -> green 'Valid resume' badge with confidence appears on selection
3. Single upload flow -> upload-resume called exactly once, results panel loads
4. Paste-text path -> short text rejected, results panel stays hidden
5. .doc rejection -> input accept excludes .doc, client rejects without API call
6. big_resume.pdf -> client rejects file >5MB with '5 MB' message, no API call
7. scanned.pdf, recipe.txt, locked.pdf -> each rejected with backend error message
8. Regression -> valid_resume.docx full analysis completes without JS errors

Run with:
    pytest backend/evaluation/test_browser.py -v
"""

import os
import re
import json
import tempfile
import pytest
from playwright.sync_api import Page, expect

# Paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
INDEX_HTML_PATH = os.path.join(BASE_DIR, "index.html")
INDEX_HTML_URL = f"file://{INDEX_HTML_PATH}"
TEST_FILES_DIR = os.path.join(BASE_DIR, "test_files")
SCREENSHOTS_DIR = os.path.join(os.path.dirname(__file__), "screenshots")

os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

# Track test results for terminal report table
TEST_RESULTS = []


def record_result(test_name: str, status: str, screenshot_name: str, details: str = ""):
    screenshot_path = os.path.join(SCREENSHOTS_DIR, screenshot_name)
    TEST_RESULTS.append({
        "name": test_name,
        "status": status,
        "screenshot": screenshot_path,
        "details": details
    })


CANNED_BLUEPRINT = {
    "status": "success",
    "ml_model_used": "mocked",
    "blueprint": {
        "project_name": "Full-Stack Performance Dashboard",
        "description": "This project will build a high-performance web dashboard. It aims to showcase responsive architecture.",
        "core_features": [
            "Develop responsive UI components in React",
            "Integrate RESTful backend endpoints",
            "Implement production observability"
        ],
        "tech_stack": ["React", "HTML", "CSS", "Docker", "Figma"],
        "resume_bullet_point": "Engineered a high-performance web dashboard using React and Docker, improving latency by [X]% for [N] users."
    }
}

CANNED_INTERVIEW = {
    "status": "success",
    "data": {
        "questions": [
            {
                "q": "How do you optimize render performance in a complex React frontend?",
                "hint": "Discuss memoization, lazy loading, and virtual DOM diffing tradeoffs."
            }
        ]
    }
}


def mock_gemini_routes(page: Page):
    """Intercept Gemini endpoints with canned valid JSON so tests are independent of API quota."""
    page.route(
        "**/api/generate-blueprint",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(CANNED_BLUEPRINT)
        )
    )
    page.route(
        "**/api/generate-interview",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(CANNED_INTERVIEW)
        )
    )


def test_1_fake_resume_rejection(page: Page):
    """Test 1: fake_resume.pdf -> error banner visible with 'not a real PDF', file card reset."""
    test_name = "1. fake_resume.pdf rejection"
    screenshot = "test_1.png"
    try:
        mock_gemini_routes(page)
        page.goto(INDEX_HTML_URL)
        fake_file = os.path.join(TEST_FILES_DIR, "fake_resume.pdf")

        page.set_input_files("#file-input", fake_file)
        page.wait_for_selector("#error-banner:not(.hidden)", timeout=10000)

        error_banner = page.locator("#error-banner")
        expect(error_banner).to_be_visible()

        error_text = page.locator("#error-text").text_content() or ""
        assert "not a real pdf" in error_text.lower(), (
            f"Expected 'not a real PDF' in error message, got: '{error_text}'"
        )

        file_card = page.locator("#file-card")
        file_card_class = file_card.get_attribute("class") or ""
        assert "hidden" in file_card_class, "File card should be hidden/reset after error"

        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, screenshot))
        record_result(test_name, "PASS", screenshot, f"Caught message: {error_text.strip()}")
    except Exception as e:
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, screenshot))
        record_result(test_name, "FAIL", screenshot, str(e))
        raise


def test_2_valid_resume_badge(page: Page):
    """Test 2: valid_resume.pdf -> green 'Valid resume' badge with confidence appears without clicking Analyze."""
    test_name = "2. valid_resume.pdf badge display"
    screenshot = "test_2.png"
    try:
        mock_gemini_routes(page)
        page.goto(INDEX_HTML_URL)
        valid_file = os.path.join(TEST_FILES_DIR, "valid_resume.pdf")

        page.set_input_files("#file-input", valid_file)
        page.wait_for_selector("#validation-badge:not(.hidden)", timeout=10000)

        file_card = page.locator("#file-card")
        expect(file_card).to_be_visible()

        badge = page.locator("#validation-badge")
        expect(badge).to_be_visible()

        badge_text = badge.text_content() or ""
        assert "valid resume" in badge_text.lower(), (
            f"Expected 'Valid resume' in badge, got: '{badge_text}'"
        )

        match = re.search(r"\d+%", badge_text)
        assert match is not None, f"Expected confidence percentage in badge, got: '{badge_text}'"

        badge_class = badge.get_attribute("class") or ""
        assert "emerald" in badge_class or "green" in badge_class, (
            f"Expected green/emerald styling on badge, got: '{badge_class}'"
        )

        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, screenshot))
        record_result(test_name, "PASS", screenshot, f"Badge text: {badge_text.strip()}")
    except Exception as e:
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, screenshot))
        record_result(test_name, "FAIL", screenshot, str(e))
        raise


def test_3_single_upload_flow(page: Page):
    """Test 3: After test 2, fill fields and click Analyze -> assert /api/upload-resume POSTed exactly ONCE."""
    test_name = "3. Single upload count verification"
    screenshot = "test_3.png"
    try:
        mock_gemini_routes(page)
        upload_requests = []
        page.on(
            "request",
            lambda req: upload_requests.append(req.url)
            if "/api/upload-resume" in req.url and req.method == "POST"
            else None
        )

        page.goto(INDEX_HTML_URL)
        valid_file = os.path.join(TEST_FILES_DIR, "valid_resume.pdf")
        page.set_input_files("#file-input", valid_file)

        page.wait_for_selector("#validation-badge:not(.hidden)", timeout=6000)
        assert len(upload_requests) == 1, (
            f"Expected 1 upload request after file selection, got {len(upload_requests)}"
        )

        # Fill required fields
        page.fill("#target-role", "Frontend Developer")
        page.fill("#jd-title", "Frontend Developer")
        page.fill("#jd-skills", "Figma, HTML, CSS, React")

        page.click("#analyze-btn")
        page.wait_for_selector("#results-panel:not(.hidden)", timeout=60000)

        expect(page.locator("#results-panel")).to_be_visible()

        # Assert /api/upload-resume was NOT called again during analysis
        assert len(upload_requests) == 1, (
            f"Expected exactly 1 POST to /api/upload-resume, but got {len(upload_requests)}"
        )

        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, screenshot))
        record_result(test_name, "PASS", screenshot, f"POSTs to /api/upload-resume: {len(upload_requests)}")
    except Exception as e:
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, screenshot))
        record_result(test_name, "FAIL", screenshot, str(e))
        raise


def test_4_paste_text_validation(page: Page):
    """Test 4: Paste-text path -> 'hello world' rejected as too short, results-panel stays hidden."""
    test_name = "4. Paste text too-short validation"
    screenshot = "test_4.png"
    try:
        mock_gemini_routes(page)
        page.goto(INDEX_HTML_URL)

        # Click the fallback toggle button
        toggle_btn = page.locator("button:has-text('Prefer to paste text instead?')")
        toggle_btn.click()
        page.wait_for_selector("#fallback-area:not(.hidden)", timeout=3000)

        # Type short text
        page.fill("#resume-text", "hello world")

        # Fill required fields
        page.fill("#target-role", "Frontend Developer")
        page.fill("#jd-title", "Frontend Developer")
        page.fill("#jd-skills", "React, CSS")

        page.click("#analyze-btn")

        page.wait_for_selector("#error-banner:not(.hidden)", timeout=5000)
        error_text = page.locator("#error-text").text_content() or ""
        assert "too short" in error_text.lower(), (
            f"Expected 'too short' in error banner, got: '{error_text}'"
        )

        # Confirm results panel is still hidden
        results_class = page.locator("#results-panel").get_attribute("class") or ""
        assert "hidden" in results_class, "Results panel must stay hidden on validation error"

        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, screenshot))
        record_result(test_name, "PASS", screenshot, f"Error: {error_text.strip()}")
    except Exception as e:
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, screenshot))
        record_result(test_name, "FAIL", screenshot, str(e))
        raise


def test_5_doc_file_rejection(page: Page):
    """Test 5: .doc file -> rejected client-side (no upload request sent), accept attribute excludes .doc."""
    test_name = "5. Legacy .doc client rejection"
    screenshot = "test_5.png"
    upload_requests = []
    temp_doc_path = None
    try:
        # Create a temporary .doc file
        with tempfile.NamedTemporaryFile(suffix=".doc", delete=False) as f:
            f.write(b"Legacy binary word document")
            temp_doc_path = f.name

        page.on(
            "request",
            lambda req: upload_requests.append(req.url)
            if "/api/upload-resume" in req.url
            else None
        )

        page.goto(INDEX_HTML_URL)

        # Verify file input accept attribute does not contain .doc
        accept_attr = page.locator("#file-input").get_attribute("accept") or ""
        accepted_extensions = [ext.strip().lower() for ext in accept_attr.split(",")]
        assert ".doc" not in accepted_extensions, (
            f"File input accept attribute should not contain '.doc', found: {accept_attr}"
        )

        # Set .doc file on input
        page.set_input_files("#file-input", temp_doc_path)
        page.wait_for_selector("#error-banner:not(.hidden)", timeout=5000)

        error_text = page.locator("#error-text").text_content() or ""
        assert "unsupported file type" in error_text.lower() or ".doc" in error_text.lower(), (
            f"Expected unsupported file type error, got: '{error_text}'"
        )

        file_card_class = page.locator("#file-card").get_attribute("class") or ""
        assert "hidden" in file_card_class, "File card should remain hidden"

        # Assert no network request was sent
        assert len(upload_requests) == 0, (
            f"Expected 0 upload requests, but found {len(upload_requests)}"
        )

        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, screenshot))
        record_result(test_name, "PASS", screenshot, f"Accept: '{accept_attr}', Uploads: 0")
    except Exception as e:
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, screenshot))
        record_result(test_name, "FAIL", screenshot, str(e))
        raise
    finally:
        if temp_doc_path and os.path.exists(temp_doc_path):
            os.remove(temp_doc_path)


def test_6_big_resume_client_rejection(page: Page):
    """Test 6: big_resume.pdf -> rejected client-side (mentions 5 MB), no upload request sent."""
    test_name = "6. File > 5MB client rejection"
    screenshot = "test_6.png"
    upload_requests = []
    try:
        page.on(
            "request",
            lambda req: upload_requests.append(req.url)
            if "/api/upload-resume" in req.url
            else None
        )

        page.goto(INDEX_HTML_URL)
        big_file = os.path.join(TEST_FILES_DIR, "big_resume.pdf")

        page.set_input_files("#file-input", big_file)
        page.wait_for_selector("#error-banner:not(.hidden)", timeout=5000)

        error_text = page.locator("#error-text").text_content() or ""
        assert "5 mb" in error_text.lower(), (
            f"Expected '5 MB' mention in error text, got: '{error_text}'"
        )

        file_card_class = page.locator("#file-card").get_attribute("class") or ""
        assert "hidden" in file_card_class, "File card should remain hidden"

        assert len(upload_requests) == 0, (
            f"Expected 0 upload requests for oversized file, got {len(upload_requests)}"
        )

        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, screenshot))
        record_result(test_name, "PASS", screenshot, f"Caught message: {error_text.strip()}")
    except Exception as e:
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, screenshot))
        record_result(test_name, "FAIL", screenshot, str(e))
        raise


def test_7_scanned_recipe_locked_files(page: Page):
    """Test 7: scanned.pdf, recipe.txt, locked.pdf -> each shows backend error, file card reset."""
    test_name = "7. scanned, recipe, locked file rejection"
    screenshot = "test_7.png"
    try:
        mock_gemini_routes(page)
        page.goto(INDEX_HTML_URL)
        files_to_test = ["scanned.pdf", "recipe.txt", "locked.pdf"]
        details = []

        for fname in files_to_test:
            fpath = os.path.join(TEST_FILES_DIR, fname)
            page.set_input_files("#file-input", fpath)

            page.wait_for_selector("#error-banner:not(.hidden)", timeout=6000)
            err_msg = page.locator("#error-text").text_content() or ""
            assert len(err_msg.strip()) > 0, f"Expected non-empty error message for {fname}"

            # Specific assertions per file
            if fname == "locked.pdf":
                assert "password-protected" in err_msg.lower(), (
                    f"Expected 'password-protected' in error message for locked.pdf, got: '{err_msg}'"
                )
            elif fname == "scanned.pdf":
                assert "scanned image" in err_msg.lower() or "no readable text" in err_msg.lower(), (
                    f"Expected scanned image error for scanned.pdf, got: '{err_msg}'"
                )
            elif fname == "recipe.txt":
                assert "doesn't look like a resume" in err_msg.lower(), (
                    f"Expected non-resume error for recipe.txt, got: '{err_msg}'"
                )

            file_card_class = page.locator("#file-card").get_attribute("class") or ""
            assert "hidden" in file_card_class, f"File card should be hidden for {fname}"

            details.append(f"{fname}: '{err_msg.strip()[:35]}...'")

            # Reset error banner before next file
            page.evaluate("hideError()")
            page.wait_for_timeout(300)

        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, screenshot))
        record_result(test_name, "PASS", screenshot, " | ".join(details))
    except Exception as e:
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, screenshot))
        record_result(test_name, "FAIL", screenshot, str(e))
        raise


def test_8_regression_full_analysis(page: Page):
    """Test 8: Regression valid_resume.docx -> full pipeline completes, valid outputs, no JS errors."""
    test_name = "8. Regression full analysis flow"
    screenshot = "test_8.png"

    # Allow 60s timeout
    page.set_default_timeout(60000)

    # Check for GEMINI_API_KEY
    env_file = os.path.join(BASE_DIR, "backend", ".env")
    has_gemini_key = bool(os.getenv("GEMINI_API_KEY"))
    if not has_gemini_key and os.path.exists(env_file):
        with open(env_file) as f:
            if "GEMINI_API_KEY=" in f.read():
                has_gemini_key = True

    if not has_gemini_key:
        record_result(test_name, "SKIPPED", screenshot, "GEMINI_API_KEY is missing")
        pytest.skip("GEMINI_API_KEY is missing; skipping full generative pipeline test.")

    uncaught_errors = []
    page.on("pageerror", lambda err: uncaught_errors.append(str(err)))

    try:
        mock_gemini_routes(page)
        page.goto(INDEX_HTML_URL)
        docx_file = os.path.join(TEST_FILES_DIR, "valid_resume.docx")

        page.set_input_files("#file-input", docx_file)
        page.wait_for_selector("#validation-badge:not(.hidden)", timeout=10000)

        page.fill("#target-role", "Frontend Developer")
        page.fill("#jd-title", "Frontend Developer")
        page.fill("#jd-skills", "Figma, HTML, CSS, React, Docker")

        page.click("#analyze-btn")
        page.wait_for_selector("#results-panel:not(.hidden)", timeout=55000)

        # 1. Score number is not "0%"
        score_text = page.locator("#score-number").text_content() or ""
        assert score_text != "0%" and score_text != "", f"Expected score != '0%', got '{score_text}'"

        # 2. Score ring #score-arc has stroke-dashoffset below 339.3 (ring is filled)
        dashoffset_str = page.locator("#score-arc").get_attribute("stroke-dashoffset") or "339.3"
        dashoffset = float(dashoffset_str)
        assert dashoffset < 339.3, f"Expected stroke-dashoffset < 339.3, got {dashoffset}"

        # 3. #performanceChart exists and is visible
        chart = page.locator("#performanceChart")
        assert chart.count() > 0, "#performanceChart canvas does not exist"
        expect(chart).to_be_visible()

        # 4. Skill pills contains at least one missing skill (Figma or Docker)
        pills_text = page.locator("#skill-pills").text_content() or ""
        assert (
            "figma" in pills_text.lower() or "docker" in pills_text.lower()
        ), f"Expected 'Figma' or 'Docker' in skill pills, got: '{pills_text}'"

        # 5. Matched skills container is non-empty
        matched_text = page.locator("#matched-skills").text_content() or ""
        assert len(matched_text.strip()) > 0, "Matched skills container should be non-empty"

        # 6. Blueprint name is non-empty
        bp_name = page.locator("#bp-name").text_content() or ""
        assert len(bp_name.strip()) > 0, "Blueprint project name should be non-empty"

        # 7. No uncaught JavaScript console errors
        assert len(uncaught_errors) == 0, f"Uncaught JavaScript console errors: {uncaught_errors}"

        # Scroll #results-panel into view and capture screenshots
        page.locator("#results-panel").scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "test_8_full.png"), full_page=True)
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, screenshot))

        record_result(test_name, "PASS", screenshot, f"Score: {score_text}, Dashoffset: {dashoffset:.1f}, BP: {bp_name[:25]}")
    except Exception as e:
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, screenshot))
        record_result(test_name, "FAIL", screenshot, str(e))
        raise


def test_9_drag_and_drop_upload(page: Page):
    """Test 9: Simulate drag-and-drop of valid_resume.pdf on #dropzone -> badge appears, file-card visible."""
    test_name = "9. Drag-and-drop upload"
    screenshot = "test_9.png"
    try:
        mock_gemini_routes(page)
        page.goto(INDEX_HTML_URL)
        valid_file = os.path.join(TEST_FILES_DIR, "valid_resume.pdf")
        with open(valid_file, "rb") as f:
            pdf_bytes = list(f.read())

        # Dispatch real drop event with file dataTransfer
        page.evaluate("""
            ([bytes]) => {
                const arr = new Uint8Array(bytes);
                const file = new File([arr], 'valid_resume.pdf', { type: 'application/pdf' });
                const dt = new DataTransfer();
                dt.items.add(file);
                const dropzone = document.getElementById('dropzone');
                dropzone.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true }));
            }
        """, [pdf_bytes])

        page.wait_for_selector("#validation-badge:not(.hidden)", timeout=6000)

        badge = page.locator("#validation-badge")
        expect(badge).to_be_visible()

        badge_text = badge.text_content() or ""
        assert "valid resume" in badge_text.lower(), (
            f"Expected 'Valid resume' in badge, got: '{badge_text}'"
        )

        file_card = page.locator("#file-card")
        expect(file_card).to_be_visible()

        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, screenshot))
        record_result(test_name, "PASS", screenshot, f"Badge text: {badge_text.strip()}")
    except Exception as e:
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, screenshot))
        record_result(test_name, "FAIL", screenshot, str(e))
        raise


def test_10_blueprint_error_graceful_degradation(page: Page):
    """Test 10: Mock /api/generate-blueprint with HTTP 429 -> results-panel is visible,
    score shown, skill pills present, and blueprint card shows fallback message."""
    test_name = "10. Blueprint error graceful degradation"
    screenshot = "test_10.png"
    try:
        # Mock blueprint with 429 rate limit error
        page.route(
            "**/api/generate-blueprint",
            lambda route: route.fulfill(
                status=429,
                content_type="application/json",
                body=json.dumps({
                    "status": "error",
                    "message": "429 RESOURCE_EXHAUSTED. Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests"
                })
            )
        )
        page.route(
            "**/api/generate-interview",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(CANNED_INTERVIEW)
            )
        )

        page.goto(INDEX_HTML_URL)
        valid_file = os.path.join(TEST_FILES_DIR, "valid_resume.pdf")
        page.set_input_files("#file-input", valid_file)
        page.wait_for_selector("#validation-badge:not(.hidden)", timeout=10000)

        page.fill("#target-role", "Frontend Developer")
        page.fill("#jd-title", "Frontend Developer")
        page.fill("#jd-skills", "Figma, HTML, CSS, React")

        page.click("#analyze-btn")
        page.wait_for_selector("#results-panel:not(.hidden)", timeout=20000)

        # 1. Assert #results-panel is visible
        expect(page.locator("#results-panel")).to_be_visible()

        # 2. Assert score is shown (not empty or 0%)
        score_text = page.locator("#score-number").text_content() or ""
        assert score_text != "" and score_text != "0%", f"Expected valid score, got '{score_text}'"

        # 3. Assert skill pills are present
        pills_text = page.locator("#skill-pills").text_content() or ""
        assert len(pills_text.strip()) > 0, "Expected skill pills to be present"

        # 4. Assert blueprint card shows fallback message
        fallback = page.locator("#bp-error")
        expect(fallback).to_be_visible()
        fallback_msg = page.locator("#bp-error-msg").text_content() or ""
        assert "temporarily unavailable" in fallback_msg.lower(), (
            f"Expected 'temporarily unavailable' in fallback message, got '{fallback_msg}'"
        )

        # 5. Assert retry button is present
        retry_btn = page.locator("#bp-retry-btn")
        expect(retry_btn).to_be_visible()

        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, screenshot))
        record_result(test_name, "PASS", screenshot, f"Score: {score_text}, Fallback: '{fallback_msg}'")
    except Exception as e:
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, screenshot))
        record_result(test_name, "FAIL", screenshot, str(e))
        raise


@pytest.mark.live
def test_live_gemini_analysis(page: Page, pytestconfig):
    """Live Gemini integration test (skipped by default in regular test runs)."""
    marker_expr = pytestconfig.getoption("-m", default="")
    if "live" not in marker_expr:
        pytest.skip("Skipped by default; run with `pytest -m live` to execute live Gemini test.")

    test_name = "Live Gemini analysis flow"
    screenshot = "test_live_gemini.png"

    env_file = os.path.join(BASE_DIR, "backend", ".env")
    has_gemini_key = bool(os.getenv("GEMINI_API_KEY"))
    if not has_gemini_key and os.path.exists(env_file):
        with open(env_file) as f:
            if "GEMINI_API_KEY=" in f.read():
                has_gemini_key = True

    if not has_gemini_key:
        pytest.skip("GEMINI_API_KEY is missing; skipping live Gemini test.")

    try:
        page.goto(INDEX_HTML_URL)
        docx_file = os.path.join(TEST_FILES_DIR, "valid_resume.docx")
        page.set_input_files("#file-input", docx_file)
        page.wait_for_selector("#validation-badge:not(.hidden)", timeout=10000)

        page.fill("#target-role", "Frontend Developer")
        page.fill("#jd-title", "Frontend Developer")
        page.fill("#jd-skills", "Figma, HTML, CSS, React, Docker")

        page.click("#analyze-btn")
        page.wait_for_selector("#results-panel:not(.hidden)", timeout=55000)
        expect(page.locator("#results-panel")).to_be_visible()

        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, screenshot))
        record_result(test_name, "PASS", screenshot, "Live Gemini analysis completed successfully")
    except Exception as e:
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, screenshot))
        record_result(test_name, "FAIL", screenshot, str(e))
        raise

