# backend/evaluation/conftest.py
"""Pytest fixtures and summary hooks for StepUp evaluation tests."""

import warnings
import pytest

# Suppress PytestRemovedIn10Warning for plugin-defined class fixtures
warnings.filterwarnings("ignore", category=pytest.PytestRemovedIn10Warning)


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "live: marks tests as calling live external APIs like Gemini")


@pytest.fixture(scope="session")
def base_url():
    """Provides base_url fixture at module level."""
    return "http://127.0.0.1:8000"


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Prints a structured pass/fail table and screenshot paths in terminal summary."""
    try:
        from test_browser import TEST_RESULTS
    except ImportError:
        try:
            from evaluation.test_browser import TEST_RESULTS
        except ImportError:
            TEST_RESULTS = []

    if not TEST_RESULTS:
        return

    terminalreporter.write_sep("=", "STEPUP RESUME VALIDATION - AUTOMATED BROWSER TEST RESULTS", bold=True, cyan=True)
    header = f"{'Test Case':<42} | {'Status':<8} | {'Screenshot Path'}"
    terminalreporter.write_line(header)
    terminalreporter.write_line("-" * 95)
    for r in TEST_RESULTS:
        status_color = {"green": True} if r["status"] == "PASS" else {"red": True}
        line = f"{r['name']:<42} | {r['status']:<8} | {r['screenshot']}"
        terminalreporter.write_line(line, **status_color)
        if r.get("details"):
            terminalreporter.write_line(f"   ↳ {r['details']}", yellow=True)
    terminalreporter.write_sep("=", bold=True, cyan=True)
