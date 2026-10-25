from unittest import mock
import pytest
import requests

from dashboard.api_client import (
    APIConnectionError,
    APIError,
    HelpdeskAPIClient,
    SessionExpiredError,
)


@pytest.fixture
def api_client():
    """Create a test HelpdeskAPIClient instance."""
    return HelpdeskAPIClient(base_url="http://testserver/api/v1", timeout=5.0)


def test_login_success(api_client: HelpdeskAPIClient):
    """Test successful login saves the token and returns response data."""
    mock_resp = mock.MagicMock(spec=requests.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"access_token": "valid_token_xyz", "token_type": "bearer"}

    with mock.patch("requests.request", return_value=mock_resp) as mock_req:
        result = api_client.login("agent@example.com", "password123")
        assert result["access_token"] == "valid_token_xyz"
        assert api_client.token == "valid_token_xyz"
        mock_req.assert_called_once_with(
            method="POST",
            url="http://testserver/api/v1/auth/login",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            params=None,
            json={"email": "agent@example.com", "password": "password123"},
            timeout=5.0,
        )


def test_login_failure(api_client: HelpdeskAPIClient):
    """Test login failure raises SessionExpiredError/APIError on 401."""
    mock_resp = mock.MagicMock(spec=requests.Response)
    mock_resp.status_code = 401
    mock_resp.json.return_value = {"error": {"message": "Invalid email or password"}}

    with mock.patch("requests.request", return_value=mock_resp):
        with pytest.raises(SessionExpiredError) as exc_info:
            api_client.login("user@example.com", "wrongpass")
        assert exc_info.value.status_code == 401
        assert "Session expired, please log in again" in str(exc_info.value)


def test_auth_header_added(api_client: HelpdeskAPIClient):
    """Test Authorization Bearer header is included on authenticated requests."""
    api_client.set_token("my_secret_token_123")

    mock_resp = mock.MagicMock(spec=requests.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": 1, "email": "me@example.com", "role": "agent"}

    with mock.patch("requests.request", return_value=mock_resp) as mock_req:
        res = api_client.get_me()
        assert res["email"] == "me@example.com"
        call_kwargs = mock_req.call_args[1]
        assert call_kwargs["headers"]["Authorization"] == "Bearer my_secret_token_123"


def test_401_handling_raises_session_expired(api_client: HelpdeskAPIClient):
    """Test 401 response on any route raises SessionExpiredError."""
    api_client.set_token("expired_jwt_token")

    mock_resp = mock.MagicMock(spec=requests.Response)
    mock_resp.status_code = 401
    mock_resp.json.return_value = {"error": {"message": "Token expired"}}

    with mock.patch("requests.request", return_value=mock_resp):
        with pytest.raises(SessionExpiredError) as exc_info:
            api_client.get_me()
        assert exc_info.value.status_code == 401
        assert "Session expired, please log in again" in str(exc_info.value)


def test_list_tickets_with_filters_and_pagination(api_client: HelpdeskAPIClient):
    """Test list_tickets serializes pagination, sorting, search, and filters accurately."""
    api_client.set_token("token_abc")

    mock_resp = mock.MagicMock(spec=requests.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"items": [], "total": 0, "page": 2, "page_size": 15}

    with mock.patch("requests.request", return_value=mock_resp) as mock_req:
        res = api_client.list_tickets(
            page=2,
            page_size=15,
            status="open",
            priority="urgent",
            assignee_id=5,
            overdue=True,
            q="database issue",
            sort_by="due_at",
            order="asc",
        )
        assert res["page"] == 2
        call_kwargs = mock_req.call_args[1]
        expected_params = {
            "page": 2,
            "page_size": 15,
            "status": "open",
            "priority": "urgent",
            "assignee_id": 5,
            "overdue": "true",
            "q": "database issue",
            "sort_by": "due_at",
            "order": "asc",
        }
        assert call_kwargs["params"] == expected_params


def test_create_ticket(api_client: HelpdeskAPIClient):
    """Test create_ticket passes title, description, priority in body."""
    api_client.set_token("token_abc")

    mock_resp = mock.MagicMock(spec=requests.Response)
    mock_resp.status_code = 201
    mock_resp.json.return_value = {
        "id": 101,
        "title": "Email server offline",
        "description": "Port 25 unreachable",
        "priority": "urgent",
        "due_at": "2026-10-25T18:00:00Z",
    }

    with mock.patch("requests.request", return_value=mock_resp) as mock_req:
        ticket = api_client.create_ticket("Email server offline", "Port 25 unreachable", priority="urgent")
        assert ticket["id"] == 101
        call_kwargs = mock_req.call_args[1]
        assert call_kwargs["method"] == "POST"
        assert call_kwargs["url"] == "http://testserver/api/v1/tickets"
        assert call_kwargs["json"] == {
            "title": "Email server offline",
            "description": "Port 25 unreachable",
            "priority": "urgent",
        }


def test_change_status_409(api_client: HelpdeskAPIClient):
    """Test 409 Conflict status update parses error message and raises APIError."""
    api_client.set_token("token_abc")

    mock_resp = mock.MagicMock(spec=requests.Response)
    mock_resp.status_code = 409
    mock_resp.json.return_value = {
        "error": {"message": "Cannot transition ticket status from 'open' to 'closed'"}
    }

    with mock.patch("requests.request", return_value=mock_resp):
        with pytest.raises(APIError) as exc_info:
            api_client.update_ticket_status(ticket_id=12, status="closed")
        assert exc_info.value.status_code == 409
        assert "Cannot transition ticket status from 'open' to 'closed'" in str(exc_info.value)


def test_connection_error(api_client: HelpdeskAPIClient):
    """Test connection error raises APIConnectionError with user-friendly message."""
    with mock.patch("requests.request", side_effect=requests.exceptions.ConnectionError("Connection refused")):
        with pytest.raises(APIConnectionError) as exc_info:
            api_client.get_me()
        assert "Cannot reach the API at http://testserver/api/v1" in str(exc_info.value)


def test_reports_methods_and_routes(api_client: HelpdeskAPIClient):
    """Test report client methods invoke the correct endpoints."""
    api_client.set_token("token_abc")

    mock_resp = mock.MagicMock(spec=requests.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = []

    with mock.patch("requests.request", return_value=mock_resp) as mock_req:
        api_client.get_report_tickets_by_status()
        assert mock_req.call_args[1]["url"].endswith("/reports/tickets-by-status")

        api_client.get_report_overdue()
        assert mock_req.call_args[1]["url"].endswith("/reports/overdue")

        api_client.get_report_resolution_time()
        assert mock_req.call_args[1]["url"].endswith("/reports/resolution-time")

        api_client.get_report_agent_ranking()
        assert mock_req.call_args[1]["url"].endswith("/reports/agent-ranking")

        api_client.get_report_daily_volume(days=14)
        assert mock_req.call_args[1]["url"].endswith("/reports/daily-volume")
        assert mock_req.call_args[1]["params"] == {"days": 14}
