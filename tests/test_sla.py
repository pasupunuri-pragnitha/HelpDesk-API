from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.sla import SLA_HOURS_BY_PRIORITY
from app.models.enums import TicketPriority, TicketStatus
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.ticket import TicketCreate
from app.services.tickets import create_ticket


def test_due_at_per_priority(client: TestClient, requester_auth_headers: dict[str, str]):
    """Test that on creation, due_at is calculated as created_at + SLA hours for each priority."""
    for priority_str, expected_hours in SLA_HOURS_BY_PRIORITY.items():
        res = client.post(
            "/api/v1/tickets",
            json={
                "title": f"SLA {priority_str.value} Ticket",
                "description": "Checking SLA calculation",
                "priority": priority_str.value,
            },
            headers=requester_auth_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["due_at"] is not None

        created_dt = datetime.fromisoformat(data["created_at"])
        due_dt = datetime.fromisoformat(data["due_at"])

        # Compare difference in seconds
        delta_hours = round((due_dt - created_dt).total_seconds() / 3600)
        assert delta_hours == expected_hours


def test_priority_change_recalculates_due_at(
    client: TestClient,
    requester_auth_headers: dict[str, str],
    agent_auth_headers: dict[str, str],
    admin_auth_headers: dict[str, str],
):
    """
    Test that priority change recalculates due_at from created_at while open or in_progress,
    but does NOT change due_at once the ticket is resolved or closed.
    """
    # 1. Create ticket with low priority (72h)
    create_res = client.post(
        "/api/v1/tickets",
        json={"title": "Recalculate SLA", "description": "Desc", "priority": "low"},
        headers=requester_auth_headers,
    )
    ticket_id = create_res.json()["id"]
    created_dt = datetime.fromisoformat(create_res.json()["created_at"])
    initial_due_dt = datetime.fromisoformat(create_res.json()["due_at"])
    assert round((initial_due_dt - created_dt).total_seconds() / 3600) == 72

    # 2. Change priority to high (8h) while OPEN -> due_at recalculates
    patch_open = client.patch(
        f"/api/v1/tickets/{ticket_id}",
        headers=requester_auth_headers,
        json={"priority": "high"},
    )
    assert patch_open.status_code == 200
    new_due_dt = datetime.fromisoformat(patch_open.json()["due_at"])
    assert round((new_due_dt - created_dt).total_seconds() / 3600) == 8

    # 3. Move to IN_PROGRESS
    client.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        headers=agent_auth_headers,
        json={"status": "in_progress"},
    )

    # 4. Change priority to urgent (2h) while IN_PROGRESS -> due_at recalculates
    patch_in_progress = client.patch(
        f"/api/v1/tickets/{ticket_id}",
        headers=admin_auth_headers,
        json={"priority": "urgent"},
    )
    assert patch_in_progress.status_code == 200
    urgent_due_dt = datetime.fromisoformat(patch_in_progress.json()["due_at"])
    assert round((urgent_due_dt - created_dt).total_seconds() / 3600) == 2

    # 5. Move to RESOLVED
    client.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        headers=agent_auth_headers,
        json={"status": "resolved"},
    )

    # 6. Change priority to low while RESOLVED -> due_at does NOT change
    patch_resolved = client.patch(
        f"/api/v1/tickets/{ticket_id}",
        headers=admin_auth_headers,
        json={"priority": "low"},
    )
    assert patch_resolved.status_code == 200
    resolved_due_dt = datetime.fromisoformat(patch_resolved.json()["due_at"])
    assert resolved_due_dt == urgent_due_dt  # Kept unchanged

    # 7. Move to CLOSED
    client.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        headers=agent_auth_headers,
        json={"status": "closed"},
    )

    # 8. Change priority while CLOSED -> due_at does NOT change
    patch_closed = client.patch(
        f"/api/v1/tickets/{ticket_id}",
        headers=admin_auth_headers,
        json={"priority": "medium"},
    )
    assert patch_closed.status_code == 200
    closed_due_dt = datetime.fromisoformat(patch_closed.json()["due_at"])
    assert closed_due_dt == urgent_due_dt  # Kept unchanged


def test_overdue_flag_scenarios(
    client: TestClient,
    db_session: Session,
    requester_user: User,
    requester_auth_headers: dict[str, str],
    agent_auth_headers: dict[str, str],
):
    """
    Test is_overdue flag behavior:
    - False before due_at.
    - True after due_at for open and in_progress.
    - False after due_at for resolved and closed.
    """
    # Case A: Future due_at (not overdue)
    future_ticket_res = client.post(
        "/api/v1/tickets",
        json={"title": "Future ticket", "description": "Desc", "priority": "low"},
        headers=requester_auth_headers,
    )
    assert future_ticket_res.status_code == 201
    assert future_ticket_res.json()["is_overdue"] is False

    # Case B: Create ticket in the past (due_at in the past) using current_time injection
    past_time = datetime.now(timezone.utc) - timedelta(days=5)
    past_ticket = create_ticket(
        db=db_session,
        ticket_in=TicketCreate(title="Past Ticket", description="Desc", priority=TicketPriority.URGENT),
        current_user=requester_user,
        current_time=past_time,
    )

    # 1. Ticket is OPEN and due_at is in past -> is_overdue is True
    res_open = client.get(f"/api/v1/tickets/{past_ticket.id}", headers=requester_auth_headers)
    assert res_open.status_code == 200
    assert res_open.json()["is_overdue"] is True

    # 2. Ticket moves to IN_PROGRESS and due_at is in past -> is_overdue is True
    client.patch(
        f"/api/v1/tickets/{past_ticket.id}/status",
        headers=agent_auth_headers,
        json={"status": "in_progress"},
    )
    res_in_prog = client.get(f"/api/v1/tickets/{past_ticket.id}", headers=requester_auth_headers)
    assert res_in_prog.status_code == 200
    assert res_in_prog.json()["is_overdue"] is True

    # 3. Ticket moves to RESOLVED and due_at is in past -> is_overdue is False
    client.patch(
        f"/api/v1/tickets/{past_ticket.id}/status",
        headers=agent_auth_headers,
        json={"status": "resolved"},
    )
    res_resolved = client.get(f"/api/v1/tickets/{past_ticket.id}", headers=requester_auth_headers)
    assert res_resolved.status_code == 200
    assert res_resolved.json()["is_overdue"] is False

    # 4. Ticket moves to CLOSED and due_at is in past -> is_overdue is False
    client.patch(
        f"/api/v1/tickets/{past_ticket.id}/status",
        headers=agent_auth_headers,
        json={"status": "closed"},
    )
    res_closed = client.get(f"/api/v1/tickets/{past_ticket.id}", headers=requester_auth_headers)
    assert res_closed.status_code == 200
    assert res_closed.json()["is_overdue"] is False
