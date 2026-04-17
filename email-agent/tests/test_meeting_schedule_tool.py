"""Tests for the meeting schedule context helper."""

import json

from tools.meeting_schedule import (
    configure_meeting_schedule,
    create_confirmed_meeting,
    get_meeting_schedule_context,
)


class FakeEmailTool:
    def __init__(self, body: str):
        self.body = body

    def search_emails(self, query: str, max_results: int) -> str:
        assert max_results == 10
        return self.body


class FakeCalendarTool:
    def __init__(self):
        self.created_events = []

    def find_free_slots(self, date: str, duration_minutes: int) -> str:
        assert date == "2026-04-20"
        assert duration_minutes == 30
        return "Available: 15:00"

    def list_events(self, days_ahead: int) -> str:
        assert days_ahead == 7
        return "No upcoming events found."

    def create_event(
        self,
        title: str,
        start_time: str,
        end_time: str,
        description: str = None,
        attendees: str = None,
        location: str = None,
    ) -> str:
        self.created_events.append(
            {
                "title": title,
                "start_time": start_time,
                "end_time": end_time,
                "description": description,
                "attendees": attendees,
                "location": location,
            }
        )
        return f"Event created: {title}\nStart: {start_time}\nEvent ID: evt-123"


class FakeMemoryTool:
    def read_memory(self, key: str) -> str:
        return "not found"


CONFIRMED_THREAD = """Found 2 email(s):

1.  From: Wenyu Ding <wenyu.ding1@student.unsw.edu.au>
   Subject: Meeting on 20 Apr
   Date: Fri, 17 Apr 2026 10:00:00 GMT
   Preview: Yes, 20 Apr at 3 PM works for me. See you then.
   ID: email-1

2.  From: KT Y <kty41693@gmail.com>
   Subject: Meeting on 20 Apr
   Date: Fri, 17 Apr 2026 09:00:00 GMT
   Preview: Would you be available to meet on 20 Apr at 3 PM?
   ID: email-2
"""


PROPOSED_THREAD = """Found 1 email(s):

1.  From: Wenyu Ding <wenyu.ding1@student.unsw.edu.au>
   Subject: Meeting next week
   Date: Fri, 17 Apr 2026 10:00:00 GMT
   Preview: Would you be available next week for a meeting?
   ID: email-1
"""


RESCHEDULE_THREAD = """Found 2 email(s):

1.  From: Wenyu Ding <wenyu.ding1@student.unsw.edu.au>
   Subject: Re: Meeting on 20 Apr
   Date: Fri, 17 Apr 2026 11:00:00 GMT
   Preview: Actually, can we reschedule? That time no longer works.
   ID: email-1

2.  From: Wenyu Ding <wenyu.ding1@student.unsw.edu.au>
   Subject: Meeting on 20 Apr
   Date: Fri, 17 Apr 2026 10:00:00 GMT
   Preview: Yes, 20 Apr at 3 PM works for me.
   ID: email-2
"""


def _configure(body: str) -> FakeCalendarTool:
    calendar = FakeCalendarTool()
    configure_meeting_schedule(
        email_tool=FakeEmailTool(body),
        calendar_tool=calendar,
        memory_tool=FakeMemoryTool(),
    )
    return calendar


def test_confirmed_email_thread_is_ready_to_create_calendar_event():
    _configure(CONFIRMED_THREAD)

    result = json.loads(
        get_meeting_schedule_context(
            contact_query="Wenyu Ding",
            requested_date="2026-04-20",
            requested_time="3 PM",
        )
    )

    assert result["status"] == "email_confirmed"
    assert result["calendar_action"] == "ready_to_create"
    assert result["agreement"]["ready_to_create_calendar_event"] is True
    assert result["agreement"]["acceptance_found"] is True
    assert result["agreement"]["exact_date_found"] is True
    assert result["agreement"]["exact_time_found"] is True
    assert result["missing_requirements"] == []
    assert "No calendar event has been created." in result["safety_notes"]


def test_missing_time_and_acceptance_are_not_ready_to_create():
    _configure(PROPOSED_THREAD)

    result = json.loads(get_meeting_schedule_context(contact_query="Wenyu Ding"))

    assert result["status"] == "proposed"
    assert result["calendar_action"] == "do_not_create_yet"
    assert result["agreement"]["ready_to_create_calendar_event"] is False
    assert "exact_time" in result["missing_requirements"]
    assert "acceptance" in result["missing_requirements"]


def test_later_reschedule_blocks_calendar_creation():
    _configure(RESCHEDULE_THREAD)

    result = json.loads(
        get_meeting_schedule_context(
            contact_query="Wenyu Ding",
            requested_date="2026-04-20",
            requested_time="3 PM",
        )
    )

    assert result["status"] == "reschedule_requested"
    assert result["calendar_action"] == "do_not_create_yet"
    assert result["agreement"]["later_cancellation_or_reschedule_found"] is True
    assert result["agreement"]["ready_to_create_calendar_event"] is False


def test_create_confirmed_meeting_creates_calendar_event_after_ready_context():
    calendar = _configure(CONFIRMED_THREAD)
    context_json = get_meeting_schedule_context(
        contact_query="Wenyu Ding",
        requested_date="2026-04-20",
        requested_time="3 PM",
    )

    result = json.loads(create_confirmed_meeting(context_json, title="Meeting with Wenyu"))

    assert result["status"] == "write_action_succeeded"
    assert result["calendar_action"] == "created"
    assert result["title"] == "Meeting with Wenyu"
    assert result["start_time"] == "2026-04-20 15:00"
    assert result["end_time"] == "2026-04-20 15:30"
    assert result["attendees"] == "wenyu.ding1@student.unsw.edu.au"
    assert len(calendar.created_events) == 1


def test_create_confirmed_meeting_rejects_not_ready_context():
    calendar = _configure(PROPOSED_THREAD)
    context_json = get_meeting_schedule_context(contact_query="Wenyu Ding")

    result = json.loads(create_confirmed_meeting(context_json))

    assert result["status"] == "proposed"
    assert result["calendar_action"] == "do_not_create_yet"
    assert "not 'ready_to_create'" in result["error"]
    assert calendar.created_events == []
