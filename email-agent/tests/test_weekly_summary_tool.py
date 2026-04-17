"""Tests for the weekly summary aggregation helper."""

import json

from tools.weekly_summary import configure_weekly_summary, get_weekly_email_activity


class FakeEmailTool:
    def search_emails(self, query: str, max_results: int) -> str:
        assert query == "newer_than:7d"
        assert max_results == 50
        return """Found 4 email(s):

1. [UNREAD] From: Google <no-reply@accounts.google.com>
   Subject: Security alert
   Date: Fri, 17 Apr 2026 10:58:48 GMT
   Preview: New login activity on your account
   ID: email-1

2.  From: Alice <alice@example.com>
   Subject: Meeting next week
   Date: Thu, 16 Apr 2026 10:00:00 GMT
   Preview: Would you be available for a meeting next Monday?
   ID: email-2

3.  From: Bob <bob@example.com>
   Subject: Re: meeting urgent
   Date: Wed, 15 Apr 2026 10:00:00 GMT
   Preview: Yes, it works for me.
   ID: email-3

4.  From: World360 Rewards <hello@example.com>
   Subject: Don't miss this points boost
   Date: Tue, 14 Apr 2026 10:00:00 GMT
   Preview: View in your browser Unsubscribe
   ID: email-4
"""

    def get_unanswered_emails(self, within_days: int, max_results: int) -> str:
        assert within_days == 7
        assert max_results == 20
        return "No unanswered emails found."


class FakeCalendarTool:
    def list_events(self, days_ahead: int) -> str:
        assert days_ahead == 7
        return "No upcoming events found."


def test_weekly_activity_returns_structured_json():
    configure_weekly_summary(email_tool=FakeEmailTool(), calendar_tool=FakeCalendarTool())

    result = json.loads(get_weekly_email_activity())

    assert result["period"]["days"] == 7
    assert result["query"] == "newer_than:7d"
    assert result["counts"]["total_emails"] == 4
    assert result["counts"]["unread_emails"] == 1
    assert result["counts"]["senders"] == 4

    theme_names = {theme["name"] for theme in result["themes"]}
    assert "Security alerts" in theme_names
    assert "Meeting scheduling" in theme_names
    assert "Newsletters / promotions" in theme_names


def test_meeting_email_confirmation_is_not_calendar_confirmation():
    configure_weekly_summary(email_tool=FakeEmailTool(), calendar_tool=FakeCalendarTool())

    result = json.loads(get_weekly_email_activity())
    meeting_theme = next(theme for theme in result["themes"] if theme["name"] == "Meeting scheduling")
    statuses = {item["status"] for item in meeting_theme["items"]}

    assert "email_confirmed" in statuses
    assert result["calendar"]["upcoming_events_found"] is False
    assert any("calendar" in limitation.lower() for limitation in result["limitations"])
