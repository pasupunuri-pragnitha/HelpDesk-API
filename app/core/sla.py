from datetime import datetime, timedelta

from app.models.enums import TicketPriority

# SLA resolution windows in hours by priority
SLA_HOURS_BY_PRIORITY: dict[TicketPriority, int] = {
    TicketPriority.URGENT: 2,   # 2 hours: Critical outage
    TicketPriority.HIGH: 8,     # 8 hours: High-impact issue (same business day)
    TicketPriority.MEDIUM: 24,  # 24 hours: Normal issue (1 calendar day)
    TicketPriority.LOW: 72,     # 72 hours: Minor request (3 calendar days)
}


def calculate_due_at(priority: TicketPriority, start_time: datetime) -> datetime:
    """
    Calculate SLA due_at timestamp by adding the priority's SLA hours to start_time.
    """
    hours = SLA_HOURS_BY_PRIORITY.get(priority, 24)
    return start_time + timedelta(hours=hours)
