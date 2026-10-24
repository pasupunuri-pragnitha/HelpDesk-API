from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

from app.models.enums import TicketPriority, TicketStatus


class TicketsByStatusItem(BaseModel):
    """Report row: count of tickets grouped by status and priority."""
    status: TicketStatus
    priority: TicketPriority
    count: int

    model_config = ConfigDict(from_attributes=True)


class OverdueTicketItem(BaseModel):
    """Report row: overdue ticket details including requester and assignee."""
    id: int
    title: str
    status: TicketStatus
    priority: TicketPriority
    due_at: datetime
    requester_id: int
    requester_name: str
    assignee_id: Optional[int] = None
    assignee_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ResolutionTimeItem(BaseModel):
    """Report row: average hours from creation to first resolution per assignee."""
    assignee_id: int
    assignee_name: str
    avg_resolution_hours: float
    ticket_count: int

    model_config = ConfigDict(from_attributes=True)


class AgentRankingItem(BaseModel):
    """Report row: agent ranked by number of tickets resolved."""
    rank: int
    agent_id: int
    agent_name: str
    resolved_count: int

    model_config = ConfigDict(from_attributes=True)


class DailyVolumeItem(BaseModel):
    """Report row: number of tickets created on a specific calendar day."""
    date: str
    ticket_count: int

    model_config = ConfigDict(from_attributes=True)
