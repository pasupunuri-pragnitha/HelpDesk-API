from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import TicketPriority, TicketStatus, UserRole
from app.models.history import TicketStatusHistory
from app.models.ticket import Ticket
from app.models.user import User


def test_reports_forbidden_for_requester(
    client: TestClient,
    requester_auth_headers: dict[str, str],
):
    """Test that all report endpoints return 403 Forbidden for requesters."""
    endpoints = [
        "/api/v1/reports/tickets-by-status",
        "/api/v1/reports/overdue",
        "/api/v1/reports/resolution-time",
        "/api/v1/reports/agent-ranking",
        "/api/v1/reports/daily-volume",
    ]
    for url in endpoints:
        res = client.get(url, headers=requester_auth_headers)
        assert res.status_code == 403
        assert res.json()["error"]["message"] == "You do not have permission to access this resource"


def test_daily_volume_validation_errors(
    client: TestClient,
    agent_auth_headers: dict[str, str],
):
    """Test that invalid days query parameter (<1 or >90) returns 422 in standard error format."""
    # days = 0 (min is 1)
    res_zero = client.get("/api/v1/reports/daily-volume?days=0", headers=agent_auth_headers)
    assert res_zero.status_code == 422
    assert "error" in res_zero.json()
    assert "days" in res_zero.json()["error"]["message"]

    # days = 91 (max is 90)
    res_large = client.get("/api/v1/reports/daily-volume?days=91", headers=agent_auth_headers)
    assert res_large.status_code == 422
    assert "error" in res_large.json()
    assert "days" in res_large.json()["error"]["message"]

    # days = not an integer
    res_invalid = client.get("/api/v1/reports/daily-volume?days=invalid", headers=agent_auth_headers)
    assert res_invalid.status_code == 422
    assert "error" in res_invalid.json()


def test_report_tickets_by_status(
    client: TestClient,
    agent_auth_headers: dict[str, str],
    db_session: Session,
    requester_user: User,
):
    """Test tickets-by-status report returns accurate counts per status and priority."""
    now = datetime.now(timezone.utc)

    # Seed tickets
    tickets = [
        Ticket(title="T1", description="D", status=TicketStatus.OPEN, priority=TicketPriority.HIGH, requester_id=requester_user.id, created_at=now, updated_at=now),
        Ticket(title="T2", description="D", status=TicketStatus.OPEN, priority=TicketPriority.HIGH, requester_id=requester_user.id, created_at=now, updated_at=now),
        Ticket(title="T3", description="D", status=TicketStatus.OPEN, priority=TicketPriority.LOW, requester_id=requester_user.id, created_at=now, updated_at=now),
        Ticket(title="T4", description="D", status=TicketStatus.IN_PROGRESS, priority=TicketPriority.URGENT, requester_id=requester_user.id, created_at=now, updated_at=now),
        Ticket(title="T5", description="D", status=TicketStatus.RESOLVED, priority=TicketPriority.MEDIUM, requester_id=requester_user.id, created_at=now, updated_at=now),
    ]
    db_session.add_all(tickets)
    db_session.commit()

    res = client.get("/api/v1/reports/tickets-by-status", headers=agent_auth_headers)
    assert res.status_code == 200
    data = res.json()

    # Convert to lookup dict: (status, priority) -> count
    counts = {(row["status"], row["priority"]): row["count"] for row in data}
    assert counts.get(("open", "high")) == 2
    assert counts.get(("open", "low")) == 1
    assert counts.get(("in_progress", "urgent")) == 1
    assert counts.get(("resolved", "medium")) == 1


def test_report_overdue(
    client: TestClient,
    agent_auth_headers: dict[str, str],
    agent_user: User,
    db_session: Session,
    requester_user: User,
):
    """
    Test overdue report:
    - Returns tickets with due_at in the past and status open or in_progress.
    - Includes requester_name and assignee_name.
    - Handles unassigned ticket properly (assignee_id=None, assignee_name=None).
    """
    now = datetime.now(timezone.utc)

    # 1. Assigned overdue ticket (OPEN, past due_at)
    t_assigned = Ticket(
        title="Assigned Overdue",
        description="Desc",
        status=TicketStatus.OPEN,
        priority=TicketPriority.HIGH,
        requester_id=requester_user.id,
        assignee_id=agent_user.id,
        due_at=now - timedelta(days=2),
        created_at=now - timedelta(days=5),
        updated_at=now,
    )
    # 2. Unassigned overdue ticket (IN_PROGRESS, past due_at, assignee_id=None)
    t_unassigned = Ticket(
        title="Unassigned Overdue",
        description="Desc",
        status=TicketStatus.IN_PROGRESS,
        priority=TicketPriority.URGENT,
        requester_id=requester_user.id,
        assignee_id=None,
        due_at=now - timedelta(days=1),
        created_at=now - timedelta(days=3),
        updated_at=now,
    )
    # 3. Past due_at but RESOLVED (should NOT be included)
    t_resolved = Ticket(
        title="Resolved Past Due",
        description="Desc",
        status=TicketStatus.RESOLVED,
        priority=TicketPriority.LOW,
        requester_id=requester_user.id,
        assignee_id=agent_user.id,
        due_at=now - timedelta(days=3),
        created_at=now - timedelta(days=6),
        updated_at=now,
    )
    # 4. Future due_at (should NOT be included)
    t_future = Ticket(
        title="Future Ticket",
        description="Desc",
        status=TicketStatus.OPEN,
        priority=TicketPriority.MEDIUM,
        requester_id=requester_user.id,
        assignee_id=agent_user.id,
        due_at=now + timedelta(days=2),
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([t_assigned, t_unassigned, t_resolved, t_future])
    db_session.commit()

    res = client.get("/api/v1/reports/overdue", headers=agent_auth_headers)
    assert res.status_code == 200
    data = res.json()

    # Exactly 2 overdue tickets returned
    returned_ids = {row["id"] for row in data}
    assert returned_ids == {t_assigned.id, t_unassigned.id}

    # Verify assigned ticket includes assignee name and requester name
    assigned_row = next(r for r in data if r["id"] == t_assigned.id)
    assert assigned_row["requester_name"] == requester_user.full_name
    assert assigned_row["assignee_id"] == agent_user.id
    assert assigned_row["assignee_name"] == agent_user.full_name

    # Verify unassigned ticket handles null assignee
    unassigned_row = next(r for r in data if r["id"] == t_unassigned.id)
    assert unassigned_row["requester_name"] == requester_user.full_name
    assert unassigned_row["assignee_id"] is None
    assert unassigned_row["assignee_name"] is None


def test_report_resolution_time(
    client: TestClient,
    agent_auth_headers: dict[str, str],
    agent_user: User,
    db_session: Session,
    requester_user: User,
):
    """
    Test resolution-time report:
    - Calculates average hours from ticket creation to first 'resolved' entry in ticket_status_history.
    - Groups per assignee.
    - Only counts tickets with a resolved history entry.
    """
    now = datetime.now(timezone.utc)

    # Create second agent
    agent2 = User(
        email="agent2_reports@example.com",
        full_name="Second Agent",
        hashed_password="agentpass2",
        role=UserRole.AGENT,
        is_active=True,
    )
    db_session.add(agent2)
    db_session.flush()

    # Agent 1: Ticket 1 created 10 hours ago, resolved 6 hours ago (duration: 4.0 hours)
    t1 = Ticket(
        title="Agent 1 - T1",
        description="Desc",
        status=TicketStatus.RESOLVED,
        priority=TicketPriority.MEDIUM,
        requester_id=requester_user.id,
        assignee_id=agent_user.id,
        created_at=now - timedelta(hours=10),
        updated_at=now,
    )
    # Agent 1: Ticket 2 created 8 hours ago, resolved 2 hours ago (duration: 6.0 hours)
    t2 = Ticket(
        title="Agent 1 - T2",
        description="Desc",
        status=TicketStatus.RESOLVED,
        priority=TicketPriority.MEDIUM,
        requester_id=requester_user.id,
        assignee_id=agent_user.id,
        created_at=now - timedelta(hours=8),
        updated_at=now,
    )
    # Agent 2: Ticket 3 created 4 hours ago, resolved 2 hours ago (duration: 2.0 hours)
    t3 = Ticket(
        title="Agent 2 - T3",
        description="Desc",
        status=TicketStatus.CLOSED,
        priority=TicketPriority.HIGH,
        requester_id=requester_user.id,
        assignee_id=agent2.id,
        created_at=now - timedelta(hours=4),
        updated_at=now,
    )
    # Unresolved ticket: created 5 hours ago, still OPEN (should NOT be counted)
    t_open = Ticket(
        title="Still Open",
        description="Desc",
        status=TicketStatus.OPEN,
        priority=TicketPriority.LOW,
        requester_id=requester_user.id,
        assignee_id=agent_user.id,
        created_at=now - timedelta(hours=5),
        updated_at=now,
    )
    db_session.add_all([t1, t2, t3, t_open])
    db_session.flush()

    # Record status history
    h1 = TicketStatusHistory(ticket_id=t1.id, changed_by_id=agent_user.id, from_status=TicketStatus.IN_PROGRESS, to_status=TicketStatus.RESOLVED, created_at=now - timedelta(hours=6))
    h2 = TicketStatusHistory(ticket_id=t2.id, changed_by_id=agent_user.id, from_status=TicketStatus.IN_PROGRESS, to_status=TicketStatus.RESOLVED, created_at=now - timedelta(hours=2))
    h3 = TicketStatusHistory(ticket_id=t3.id, changed_by_id=agent2.id, from_status=TicketStatus.IN_PROGRESS, to_status=TicketStatus.RESOLVED, created_at=now - timedelta(hours=2))
    # Add a second 'resolved' history row to t1 (to test that the CTE strictly takes MIN/first resolved_at)
    h1_second = TicketStatusHistory(ticket_id=t1.id, changed_by_id=agent_user.id, from_status=TicketStatus.IN_PROGRESS, to_status=TicketStatus.RESOLVED, created_at=now - timedelta(hours=1))
    db_session.add_all([h1, h2, h3, h1_second])
    db_session.commit()

    res = client.get("/api/v1/reports/resolution-time", headers=agent_auth_headers)
    assert res.status_code == 200
    data = res.json()

    res_by_agent = {row["assignee_id"]: row for row in data}

    # Agent 2: (2.0 hours) / 1 ticket = 2.0
    assert agent2.id in res_by_agent
    assert round(res_by_agent[agent2.id]["avg_resolution_hours"], 1) == 2.0
    assert res_by_agent[agent2.id]["ticket_count"] == 1

    # Agent 1: (4.0 + 6.0) / 2 tickets = 5.0 hours
    assert agent_user.id in res_by_agent
    assert round(res_by_agent[agent_user.id]["avg_resolution_hours"], 1) == 5.0
    assert res_by_agent[agent_user.id]["ticket_count"] == 2


def test_report_agent_ranking_with_ties(
    client: TestClient,
    agent_auth_headers: dict[str, str],
    agent_user: User,
    db_session: Session,
    requester_user: User,
):
    """
    Test agent-ranking report:
    - Ranks agents by count of tickets resolved using RANK() window function.
    - Verifies tied agents share the same rank.
    """
    now = datetime.now(timezone.utc)

    # Create 2 more agents
    agent_bob = User(email="bob@example.com", full_name="Bob Agent", hashed_password="h", role=UserRole.AGENT, is_active=True)
    agent_charlie = User(email="charlie@example.com", full_name="Charlie Agent", hashed_password="h", role=UserRole.AGENT, is_active=True)
    db_session.add_all([agent_bob, agent_charlie])
    db_session.flush()

    # Agent User resolves 2 tickets
    t1 = Ticket(title="T1", description="D", status=TicketStatus.RESOLVED, priority=TicketPriority.LOW, requester_id=requester_user.id, assignee_id=agent_user.id, created_at=now, updated_at=now)
    t2 = Ticket(title="T2", description="D", status=TicketStatus.CLOSED, priority=TicketPriority.LOW, requester_id=requester_user.id, assignee_id=agent_user.id, created_at=now, updated_at=now)

    # Bob resolves 2 tickets (tied with Agent User!)
    t3 = Ticket(title="T3", description="D", status=TicketStatus.RESOLVED, priority=TicketPriority.LOW, requester_id=requester_user.id, assignee_id=agent_bob.id, created_at=now, updated_at=now)
    t4 = Ticket(title="T4", description="D", status=TicketStatus.RESOLVED, priority=TicketPriority.LOW, requester_id=requester_user.id, assignee_id=agent_bob.id, created_at=now, updated_at=now)

    # Charlie resolves 1 ticket
    t5 = Ticket(title="T5", description="D", status=TicketStatus.RESOLVED, priority=TicketPriority.LOW, requester_id=requester_user.id, assignee_id=agent_charlie.id, created_at=now, updated_at=now)

    db_session.add_all([t1, t2, t3, t4, t5])
    db_session.commit()

    res = client.get("/api/v1/reports/agent-ranking", headers=agent_auth_headers)
    assert res.status_code == 200
    data = res.json()

    ranking_by_id = {row["agent_id"]: row for row in data}

    # Verify tied agents share rank 1
    assert ranking_by_id[agent_user.id]["rank"] == 1
    assert ranking_by_id[agent_user.id]["resolved_count"] == 2
    assert ranking_by_id[agent_bob.id]["rank"] == 1
    assert ranking_by_id[agent_bob.id]["resolved_count"] == 2

    # Verify Charlie gets rank 3 (RANK skips after ties)
    assert ranking_by_id[agent_charlie.id]["rank"] == 3
    assert ranking_by_id[agent_charlie.id]["resolved_count"] == 1


def test_report_daily_volume(
    client: TestClient,
    agent_auth_headers: dict[str, str],
    db_session: Session,
    requester_user: User,
):
    """
    Test daily-volume report:
    - Returns tickets created per day using a CTE.
    - Excludes tickets outside the lookback window.
    """
    now = datetime.now(timezone.utc)

    # 2 tickets created today
    t1 = Ticket(title="Today 1", description="D", status=TicketStatus.OPEN, priority=TicketPriority.LOW, requester_id=requester_user.id, created_at=now, updated_at=now)
    t2 = Ticket(title="Today 2", description="D", status=TicketStatus.OPEN, priority=TicketPriority.LOW, requester_id=requester_user.id, created_at=now, updated_at=now)

    # 1 ticket created 2 days ago
    t3 = Ticket(title="2 Days Ago", description="D", status=TicketStatus.OPEN, priority=TicketPriority.LOW, requester_id=requester_user.id, created_at=now - timedelta(days=2), updated_at=now)

    # 1 ticket created 100 days ago (outside default 30-day window)
    t4 = Ticket(title="100 Days Ago", description="D", status=TicketStatus.OPEN, priority=TicketPriority.LOW, requester_id=requester_user.id, created_at=now - timedelta(days=100), updated_at=now)

    db_session.add_all([t1, t2, t3, t4])
    db_session.commit()

    res = client.get("/api/v1/reports/daily-volume?days=30", headers=agent_auth_headers)
    assert res.status_code == 200
    data = res.json()

    # Look up by date
    today_str = now.strftime("%Y-%m-%d")
    two_days_ago_str = (now - timedelta(days=2)).strftime("%Y-%m-%d")

    counts = {row["date"]: row["ticket_count"] for row in data}
    assert counts.get(today_str) == 2
    assert counts.get(two_days_ago_str) == 1

    # Verify 100 days ago is NOT present
    old_date_str = (now - timedelta(days=100)).strftime("%Y-%m-%d")
    assert old_date_str not in counts
