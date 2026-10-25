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


def test_holidays_view_renders_smoke():
    """Smoke test that Holidays view renders without unhandled exceptions for an agent."""
    from unittest import mock
    from dashboard.api_client import HelpdeskAPIClient

    with mock.patch.object(
        HelpdeskAPIClient,
        "list_holidays",
        return_value=[{"id": 1, "holiday_date": "2026-01-01", "name": "New Year"}],
    ):
        at = AppTest.from_file(str(DASHBOARD_APP_PATH), default_timeout=10)
        at.session_state["token"] = "fake-jwt-token"
        at.session_state["user"] = {"id": 2, "email": "agent@example.com", "role": "agent"}
        at.session_state["current_page"] = "Holidays"
        at.run()
        assert not at.exception
