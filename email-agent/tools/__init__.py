"""Custom tools for the email agent."""

from .meeting_schedule import (
    configure_meeting_schedule,
    create_confirmed_meeting,
    get_meeting_schedule_context,
)
from .weekly_summary import configure_weekly_summary, get_weekly_email_activity
from .writing_style import configure_writing_style, get_writing_style_profile

__all__ = [
    "configure_meeting_schedule",
    "configure_weekly_summary",
    "configure_writing_style",
    "create_confirmed_meeting",
    "get_meeting_schedule_context",
    "get_weekly_email_activity",
    "get_writing_style_profile",
]
