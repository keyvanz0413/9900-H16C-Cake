"""Tests for local approval plugins."""

import pytest

from plugins.calendar_approval_plugin import check_calendar_approval
from plugins.gmail_approval_plugin import check_email_approval, sync_crm_after_send


class FakeIO:
    def __init__(self, responses):
        self.responses = list(responses)
        self.sent = []

    def send(self, event):
        self.sent.append(event)

    def receive(self):
        if not self.responses:
            raise AssertionError("No more fake IO responses available")
        return self.responses.pop(0)


class FakeStorage:
    def __init__(self):
        self.checkpoints = []

    def checkpoint(self, session):
        self.checkpoints.append(dict(session))


class FakeAgent:
    def __init__(self, pending_tool=None, io=None, storage=None):
        self.current_session = {}
        if pending_tool:
            self.current_session["pending_tool"] = pending_tool
        self.io = io
        self.storage = storage
        self.tools = type("Tools", (), {})()

    def _record_trace(self, entry):
        self.current_session.setdefault("trace", []).append(entry)


def test_gmail_plugin_requests_frontend_approval_and_saves_session_scope():
    io = FakeIO([{"type": "APPROVAL_RESPONSE", "approved": True, "scope": "session"}])
    storage = FakeStorage()
    agent = FakeAgent(
        pending_tool={
            "name": "send",
            "arguments": {
                "to": "xhy413604@gmail.com",
                "subject": "关于下周四的汇报",
                "body": "你好",
            },
        },
        io=io,
        storage=storage,
    )

    check_email_approval(agent)

    assert io.sent[0]["type"] == "approval_needed"
    assert io.sent[0]["tool"] == "send"
    assert "xhy413604@gmail.com" in io.sent[0]["description"]
    assert "send" in agent.current_session["gmail_approved_tools"]
    assert agent.current_session["gmail_force_send"]["tool_name"] == "send"
    assert storage.checkpoints


def test_gmail_plugin_reject_hard_sets_stop_signal():
    io = FakeIO([{"type": "APPROVAL_RESPONSE", "approved": False, "scope": "once", "mode": "reject_hard"}])
    agent = FakeAgent(
        pending_tool={"name": "reply", "arguments": {"email_id": "thread-123", "body": "follow up"}},
        io=io,
    )

    with pytest.raises(ValueError, match="rejected Gmail tool"):
        check_email_approval(agent)

    assert agent.current_session["stop_signal"] == "User rejected Gmail tool 'reply'."


def test_gmail_plugin_allows_conversational_mode_without_io_or_tty():
    agent = FakeAgent(
        pending_tool={
            "name": "send",
            "arguments": {
                "to": "xhy413604@gmail.com",
                "subject": "关于下周四的汇报",
                "body": "你好",
            },
        },
    )

    check_email_approval(agent)

    assert "gmail_force_send" not in agent.current_session


def test_calendar_plugin_requests_frontend_approval_and_saves_session_scope():
    io = FakeIO([{"type": "APPROVAL_RESPONSE", "approved": True, "scope": "session"}])
    storage = FakeStorage()
    agent = FakeAgent(
        pending_tool={
            "name": "create_event",
            "arguments": {
                "title": "Weekly sync",
                "start_time": "2026-04-20T09:00:00",
                "end_time": "2026-04-20T09:30:00",
            },
        },
        io=io,
        storage=storage,
    )

    check_calendar_approval(agent)

    assert io.sent[0]["type"] == "approval_needed"
    assert io.sent[0]["tool"] == "create_event"
    assert "Weekly sync" in io.sent[0]["description"]
    assert "create_event" in agent.current_session["calendar_approved_tools"]
    assert storage.checkpoints


def test_gmail_plugin_syncs_crm_after_successful_send():
    class FakeGmail:
        def __init__(self):
            self.calls = []

        def update_contact(self, email, **kwargs):
            self.calls.append((email, kwargs))
            return "Updated contact"

    agent = FakeAgent()
    agent.tools.gmail = FakeGmail()
    agent.current_session["trace"] = [
        {
            "type": "tool_result",
            "name": "send",
            "status": "success",
            "args": {"to": "xhy413604@gmail.com"},
        }
    ]

    sync_crm_after_send(agent)

    assert agent.tools.gmail.calls[0][0] == "xhy413604@gmail.com"
