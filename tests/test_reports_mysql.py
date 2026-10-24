from datetime import datetime, timedelta, timezone
import os
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from app.models.enums import TicketPriority, TicketStatus, UserRole
from app.models.history import TicketStatusHistory
from app.models.ticket import Ticket
from app.models.user import User
from app.services.reports import (
    get_agent_ranking,
    get_daily_volume,
    get_overdue_tickets,
    get_resolution_time,
    get_tickets_by_status,
)

TEST_MYSQL_URL = os.getenv("TEST_MYSQL_URL")

pytestmark = [
    pytest.mark.mysql,
    pytest.mark.skipif(
        not TEST_MYSQL_URL,
        reason="TEST_MYSQL_URL environment variable is not set; skipping MySQL integration tests",
    ),
]


@pytest.fixture
def mysql_session():
    """Provide a transactional database session against the real MySQL instance."""
    engine = sa.create_engine(TEST_MYSQL_URL)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()
    engine.dispose()


def test_mysql_all_reports(mysql_session: Session):
    """
    Integration test running all 5 reports against real MySQL 8.
    Verifies MySQL TIMESTAMPDIFF, RANK() OVER, CTEs, and JOINs execute flawlessly.
    """
    now = datetime.now(timezone.utc)

    # 1. Seed users
    agent1 = User(
        email="mysql_agent1@example.com",
        full_name="MySQL Agent 1",
        hashed_password="hash",
        role=UserRole.AGENT,
        is_active=True,
    )
    agent2 = User(
        email="mysql_agent2@example.com",
        full_name="MySQL Agent 2",
        hashed_password="hash",
        role=UserRole.AGENT,
        is_active=True,
    )
    requester = User(
        email="mysql_req@example.com",
        full_name="MySQL Requester",
        hashed_password="hash",
        role=UserRole.REQUESTER,
        is_active=True,
    )
    mysql_session.add_all([agent1, agent2, requester])
    mysql_session.flush()

    # 2. Seed tickets
    # Overdue assigned
    t1 = Ticket(
        title="MySQL Overdue Assigned",
        description="Desc",
        status=TicketStatus.OPEN,
        priority=TicketPriority.HIGH,
        requester_id=requester.id,
        assignee_id=agent1.id,
        due_at=now - timedelta(days=2),
        created_at=now - timedelta(days=5),
        updated_at=now,
    )
    # Overdue unassigned
    t2 = Ticket(
        title="MySQL Overdue Unassigned",
        description="Desc",
        status=TicketStatus.IN_PROGRESS,
        priority=TicketPriority.MEDIUM,
        requester_id=requester.id,
        assignee_id=None,
        due_at=now - timedelta(days=1),
        created_at=now - timedelta(days=3),
        updated_at=now,
    )
    # Resolved ticket for agent 1 (created 6h ago, resolved 2h ago -> 4h duration)
    t3 = Ticket(
        title="MySQL Resolved T3",
        description="Desc",
        status=TicketStatus.RESOLVED,
        priority=TicketPriority.LOW,
        requester_id=requester.id,
        assignee_id=agent1.id,
        due_at=now + timedelta(days=1),
        created_at=now - timedelta(hours=6),
        updated_at=now,
    )
    # Resolved ticket for agent 2 (created 3h ago, resolved 1h ago -> 2h duration)
    t4 = Ticket(
        title="MySQL Resolved T4",
        description="Desc",
        status=TicketStatus.RESOLVED,
        priority=TicketPriority.URGENT,
        requester_id=requester.id,
        assignee_id=agent2.id,
        due_at=now + timedelta(days=1),
        created_at=now - timedelta(hours=3),
        updated_at=now,
    )
    mysql_session.add_all([t1, t2, t3, t4])
    mysql_session.flush()

    # Seed history for resolved tickets
    h1 = TicketStatusHistory(
        ticket_id=t3.id,
        changed_by_id=agent1.id,
        from_status=TicketStatus.IN_PROGRESS,
        to_status=TicketStatus.RESOLVED,
        created_at=now - timedelta(hours=2),
    )
    h2 = TicketStatusHistory(
        ticket_id=t4.id,
        changed_by_id=agent2.id,
        from_status=TicketStatus.IN_PROGRESS,
        to_status=TicketStatus.RESOLVED,
        created_at=now - timedelta(hours=1),
    )
    mysql_session.add_all([h1, h2])
    mysql_session.flush()

    # 1. Report: tickets by status
    status_report = get_tickets_by_status(mysql_session)
    assert len(status_report) >= 2

    # 2. Report: overdue tickets
    overdue_report = get_overdue_tickets(mysql_session, current_time=now)
    overdue_ids = {r["id"] for r in overdue_report}
    assert t1.id in overdue_ids
    assert t2.id in overdue_ids

    # Check assigned vs unassigned in MySQL
    assigned_row = next(r for r in overdue_report if r["id"] == t1.id)
    assert assigned_row["assignee_name"] == agent1.full_name
    unassigned_row = next(r for r in overdue_report if r["id"] == t2.id)
    assert unassigned_row["assignee_name"] is None

    # 3. Report: resolution time (verifying MySQL TIMESTAMPDIFF)
    res_time_report = get_resolution_time(mysql_session)
    agent_res_map = {r["assignee_id"]: r for r in res_time_report}
    assert agent1.id in agent_res_map
    assert round(float(agent_res_map[agent1.id]["avg_resolution_hours"]), 1) == 4.0
    assert agent2.id in agent_res_map
    assert round(float(agent_res_map[agent2.id]["avg_resolution_hours"]), 1) == 2.0

    # 4. Report: agent ranking (verifying MySQL RANK() OVER window function)
    ranking_report = get_agent_ranking(mysql_session)
    assert len(ranking_report) >= 2
    # Both agents resolved 1 ticket, so they share rank 1 in MySQL!
    r_map = {r["agent_id"]: r for r in ranking_report}
    assert r_map[agent1.id]["rank"] == 1
    assert r_map[agent2.id]["rank"] == 1

    # 5. Report: daily volume
    volume_report = get_daily_volume(mysql_session, days=30, current_time=now)
    assert len(volume_report) >= 1
