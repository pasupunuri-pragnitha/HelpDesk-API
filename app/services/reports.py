from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence
import sqlalchemy as sa
from sqlalchemy.orm import Session


def get_hours_diff_expression(dialect_name: str, start_col: str, end_col: str) -> str:
    """
    Generate the SQL expression for calculating elapsed time in hours between two timestamp columns.
    
    Why this helper is needed:
    - MySQL has a dedicated TIMESTAMPDIFF(unit, start, end) function:
      TIMESTAMPDIFF(SECOND, start, end) / 3600.0 returns fractional hours.
    - SQLite does not have TIMESTAMPDIFF; instead it uses the julianday() function:
      (julianday(end) - julianday(start)) returns the difference in fractional days,
      which multiplied by 24.0 gives elapsed hours.
    """
    if dialect_name == "mysql":
        return f"(TIMESTAMPDIFF(SECOND, {start_col}, {end_col}) / 3600.0)"
    return f"((julianday({end_col}) - julianday({start_col})) * 24.0)"


def get_tickets_by_status(db: Session) -> Sequence[dict[str, Any]]:
    """
    Report 1: Count tickets per status and priority using GROUP BY.
    """
    stmt = sa.text("""
        SELECT 
            status, 
            priority, 
            COUNT(*) AS count
        FROM tickets
        GROUP BY status, priority
        ORDER BY status, priority
    """)
    result = db.execute(stmt)
    return result.mappings().all()


def get_overdue_tickets(
    db: Session,
    current_time: Optional[datetime] = None,
) -> Sequence[dict[str, Any]]:
    """
    Report 2: Overdue tickets (due_at in the past, status open or in_progress)
    with the requester's name and assignee's name (or null).
    Uses INNER JOIN for requester and LEFT JOIN for assignee.
    """
    now = current_time or datetime.now(timezone.utc)
    stmt = sa.text("""
        SELECT 
            t.id,
            t.title,
            t.status,
            t.priority,
            t.due_at,
            t.requester_id,
            r.full_name AS requester_name,
            t.assignee_id,
            a.full_name AS assignee_name
        FROM tickets t
        JOIN users r ON t.requester_id = r.id
        LEFT JOIN users a ON t.assignee_id = a.id
        WHERE t.due_at < :now
          AND t.status IN ('open', 'in_progress')
        ORDER BY t.due_at ASC, t.id ASC
    """)
    result = db.execute(stmt, {"now": now})
    return result.mappings().all()


def get_resolution_time(db: Session) -> Sequence[dict[str, Any]]:
    """
    Report 3: Average hours from ticket creation to the first 'resolved' entry
    in ticket_status_history, per assignee, using a CTE.
    Only counts tickets that have a resolved entry.
    """
    dialect_name = db.get_bind().dialect.name
    diff_expr = get_hours_diff_expression(dialect_name, "t.created_at", "fr.resolved_at")

    stmt = sa.text(f"""
        WITH first_resolved AS (
            SELECT 
                ticket_id, 
                MIN(created_at) AS resolved_at
            FROM ticket_status_history
            WHERE to_status = 'resolved'
            GROUP BY ticket_id
        ),
        ticket_resolution AS (
            SELECT 
                t.id AS ticket_id,
                t.assignee_id,
                u.full_name AS assignee_name,
                {diff_expr} AS resolution_hours
            FROM tickets t
            JOIN first_resolved fr ON t.id = fr.ticket_id
            JOIN users u ON t.assignee_id = u.id
        )
        SELECT 
            assignee_id,
            assignee_name,
            ROUND(AVG(resolution_hours), 2) AS avg_resolution_hours,
            COUNT(*) AS ticket_count
        FROM ticket_resolution
        GROUP BY assignee_id, assignee_name
        ORDER BY avg_resolution_hours ASC, assignee_id ASC
    """)
    result = db.execute(stmt)
    return result.mappings().all()


def get_agent_ranking(db: Session) -> Sequence[dict[str, Any]]:
    """
    Report 4: Agents ranked by number of tickets resolved using RANK() OVER (ORDER BY ... DESC).
    Ties share a rank.
    """
    stmt = sa.text("""
        WITH agent_counts AS (
            SELECT 
                u.id AS agent_id,
                u.full_name AS agent_name,
                COUNT(t.id) AS resolved_count
            FROM users u
            JOIN tickets t ON t.assignee_id = u.id AND t.status IN ('resolved', 'closed')
            WHERE u.role = 'agent'
            GROUP BY u.id, u.full_name
        )
        SELECT 
            agent_id,
            agent_name,
            resolved_count,
            RANK() OVER (ORDER BY resolved_count DESC) AS `rank`
        FROM agent_counts
        ORDER BY `rank` ASC, agent_id ASC
    """)
    result = db.execute(stmt)
    return result.mappings().all()


def get_daily_volume(
    db: Session,
    days: int = 30,
    current_time: Optional[datetime] = None,
) -> Sequence[dict[str, Any]]:
    """
    Report 5: Tickets created per day over the last N days using a CTE.
    Days with zero tickets may be left out.
    """
    now = current_time or datetime.now(timezone.utc)
    since_date = now - timedelta(days=days)

    stmt = sa.text("""
        WITH daily_tickets AS (
            SELECT 
                DATE(created_at) AS ticket_date,
                id
            FROM tickets
            WHERE created_at >= :since_date
        )
        SELECT 
            ticket_date AS `date`,
            COUNT(id) AS ticket_count
        FROM daily_tickets
        GROUP BY ticket_date
        ORDER BY ticket_date ASC
    """)
    result = db.execute(stmt, {"since_date": since_date})
    return result.mappings().all()
