from pathlib import Path
from streamlit.testing.v1 import AppTest

DASHBOARD_APP_PATH = Path(__file__).resolve().parent.parent.parent / "dashboard" / "app.py"


def test_login_screen_renders_smoke():
    """Smoke test that the HelpDesk dashboard login screen renders without unhandled exceptions."""
    at = AppTest.from_file(str(DASHBOARD_APP_PATH), default_timeout=10)
    at.run()
    assert not at.exception
    # Verifies the login gate is rendered with tabs and inputs
    assert len(at.tabs) >= 2 or len(at.text_input) >= 1
