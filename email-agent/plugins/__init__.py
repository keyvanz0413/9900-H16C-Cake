"""Project-local plugins for the email agent."""

from .calendar_approval_plugin import calendar_approval_plugin
from .gmail_approval_plugin import gmail_approval_plugin
from .react_plugin import re_act

__all__ = [
    "calendar_approval_plugin",
    "gmail_approval_plugin",
    "re_act",
]
