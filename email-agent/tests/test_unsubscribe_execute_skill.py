from __future__ import annotations

import json
import threading
from pathlib import Path

from intent_layer import PythonSkillExecutor, SkillInputFieldSpec, SkillSpec, build_tool_function_map


class UnsubscribeExecuteToolBox:
    def __init__(self):
        self.one_click_status = "confirmed"
        self.one_click_evidence = ""
        self.calls: list[tuple[str, dict[str, object]]] = []
        self._lock = threading.Lock()

    def _record(self, tool_name: str, **kwargs: object) -> None:
        with self._lock:
            self.calls.append((tool_name, kwargs))

    def search_emails(self, query: str, max_results: int = 10) -> str:
        self._record("search_emails", query=query, max_results=max_results)
        return (
            "Found 3 email(s):\n\n"
            "1. From: Deals <deals@example.com>\n"
            "   Subject: Weekly deals\n"
            "   ID: unsub-001\n\n"
            "2. From: Product <product@vendor.test>\n"
            "   Subject: Product update\n"
            "   ID: unsub-002\n\n"
            "3. From: Alerts <alerts@service.test>\n"
            "   Subject: Account notice\n"
            "   ID: unsub-003\n"
        )

    def get_unsubscribe_info(self, email_ids, max_manual_links: int = 5) -> str:
        self._record("get_unsubscribe_info", email_ids=email_ids, max_manual_links=max_manual_links)
        payloads = {
            "unsub-001": {
                "email_id": "unsub-001",
                "unsubscribe": {
                    "method": "one_click",
                    "options": {
                        "one_click": {
                            "url": "https://example.com/one-click?id=123",
                            "request_payload": {"url": "https://example.com/one-click?id=123"},
                        },
                        "website": {
                            "manual_links": [
                                {
                                    "url": "https://example.com/manual-unsubscribe?token=abc",
                                    "label": "Click here to unsubscribe",
                                    "source": "email_body",
                                }
                            ]
                        },
                    },
                },
                "error": "",
            },
            "unsub-002": {
                "email_id": "unsub-002",
                "unsubscribe": {
                    "method": "mailto",
                    "options": {
                        "mailto": {
                            "url": "mailto:unsubscribe@example.com?subject=unsubscribe",
                            "send_payload": {
                                "to": "unsubscribe@example.com",
                                "subject": "unsubscribe",
                                "body": "",
                            },
                        }
                    },
                },
                "error": "",
            },
            "unsub-003": {
                "email_id": "unsub-003",
                "unsubscribe": {
                    "method": "website",
                    "options": {
                        "website": {
                            "url": "https://service.example.com/preferences",
                            "manual_links": [
                                {
                                    "url": "https://service.example.com/preferences",
                                    "label": "Manage preferences",
                                    "source": "list_unsubscribe_header",
                                }
                            ],
                        }
                    },
                },
                "error": "",
            },
        }
        return json.dumps(
            {
                "items": [payloads[email_id] for email_id in email_ids],
                "summary": {
                    "requested_count": len(email_ids),
                    "analyzed_count": len(email_ids),
                    "error_count": 0,
                },
                "error": "",
            },
            ensure_ascii=False,
        )

    def post_one_click_unsubscribe(self, url: str) -> str:
        self._record("post_one_click_unsubscribe", url=url)
        http_status = 202 if self.one_click_status == "request_accepted" else 204
        if self.one_click_status == "failed":
            http_status = 403
        return json.dumps(
            {
                "status": self.one_click_status,
                "sender_unsubscribe_status": self.one_click_status,
                "gmail_subscription_ui_status": "not_updated_by_agent",
                "http_status": http_status,
                "url": url,
                "evidence": self.one_click_evidence or f"HTTP {http_status} response received.",
                "error": "",
            },
            ensure_ascii=False,
        )

    def send(self, to: str, subject: str, body: str) -> str:
        self._record("send", to=to, subject=subject, body=body)
        return f"sent to {to} subject={subject}"


def _executor_for(toolbox: UnsubscribeExecuteToolBox) -> PythonSkillExecutor:
    return PythonSkillExecutor(
        skills_directory=Path(__file__).resolve().parent.parent / "skills",
        tool_function_map=build_tool_function_map([toolbox]),
    )


def _spec() -> SkillSpec:
    return SkillSpec(
        name="unsubscribe_execute",
        description="Execute unsubscribe.",
        scope="Confirmed unsubscribe only.",
        used_tools=(
            "search_emails",
            "get_unsubscribe_info",
            "post_one_click_unsubscribe",
            "send",
        ),
        output="execution result",
        input_schema=(
            SkillInputFieldSpec(
                name="days",
                field_type="int",
                required=False,
                description="Number of recent days to inspect.",
                has_default=True,
                default=30,
            ),
            SkillInputFieldSpec(
                name="max_results",
                field_type="int",
                required=False,
                description="Maximum number of emails to inspect.",
                has_default=True,
                default=100,
            ),
            SkillInputFieldSpec(
                name="method",
                field_type="string",
                required=False,
                description="Method.",
                has_default=True,
                default="auto",
            ),
            SkillInputFieldSpec(
                name="confirmed",
                field_type="bool",
                required=False,
                description="Explicit confirmation.",
                has_default=True,
                default=False,
            ),
        ),
    )


def test_unsubscribe_execute_requires_confirmation_before_side_effects():
    toolbox = UnsubscribeExecuteToolBox()
    result = _executor_for(toolbox).run(
        _spec(),
        skill_arguments={"days": 30, "max_results": 20, "confirmed": False},
        current_message="Unsubscribe from these newsletters.",
        intent_decision=type("Intent", (), {"intent": "Unsubscribe from recent subscription emails."})(),
        recent_context=[],
    )

    assert result.completed is True
    assert result.response is not None
    assert "[UNSUBSCRIBE_EXECUTE_BUNDLE]" in result.response
    assert '"needs_confirmation": 3' in result.response
    assert [name for name, _ in toolbox.calls] == ["search_emails", "get_unsubscribe_info"]


def test_unsubscribe_execute_runs_batch_execution_after_confirmation():
    toolbox = UnsubscribeExecuteToolBox()
    result = _executor_for(toolbox).run(
        _spec(),
        skill_arguments={"days": 30, "max_results": 20, "confirmed": True},
        current_message="Yes, unsubscribe them.",
        intent_decision=type("Intent", (), {"intent": "Confirm batch unsubscribe."})(),
        recent_context=[],
    )

    assert result.completed is True
    assert result.response is not None
    assert '"status": "confirmed"' in result.response
    assert '"status": "request_sent"' in result.response
    assert '"status": "manual_link_available"' in result.response
    assert ("post_one_click_unsubscribe", {"url": "https://example.com/one-click?id=123"}) in toolbox.calls
    assert ("send", {"to": "unsubscribe@example.com", "subject": "unsubscribe", "body": "unsubscribe"}) in toolbox.calls


def test_unsubscribe_execute_preserves_one_click_request_accepted_status():
    toolbox = UnsubscribeExecuteToolBox()
    toolbox.one_click_status = "request_accepted"
    result = _executor_for(toolbox).run(
        _spec(),
        skill_arguments={"days": 30, "max_results": 20, "confirmed": True},
        current_message="Yes, unsubscribe them.",
        intent_decision=type("Intent", (), {"intent": "Confirm batch unsubscribe."})(),
        recent_context=[],
    )

    assert result.completed is True
    assert result.response is not None
    assert '"request_accepted": 1' in result.response
    assert '"sender_unsubscribe_status": "request_accepted"' in result.response


def test_unsubscribe_execute_returns_manual_link_when_one_click_fails():
    toolbox = UnsubscribeExecuteToolBox()
    toolbox.one_click_status = "failed"
    toolbox.one_click_evidence = "HTTP 403 response received."
    result = _executor_for(toolbox).run(
        _spec(),
        skill_arguments={"days": 30, "max_results": 20, "confirmed": True},
        current_message="Yes, unsubscribe them.",
        intent_decision=type("Intent", (), {"intent": "Confirm batch unsubscribe."})(),
        recent_context=[],
    )

    assert result.completed is True
    assert result.response is not None
    assert '"manual_link_available": 2' in result.response
    assert "https://example.com/manual-unsubscribe?token=abc" in result.response
    assert "https://service.example.com/preferences" in result.response


def test_unsubscribe_execute_requested_method_filters_candidates():
    toolbox = UnsubscribeExecuteToolBox()
    result = _executor_for(toolbox).run(
        _spec(),
        skill_arguments={"days": 30, "max_results": 20, "confirmed": True, "method": "mailto"},
        current_message="Use mailto only.",
        intent_decision=type("Intent", (), {"intent": "Confirm mailto-only unsubscribe."})(),
        recent_context=[],
    )

    assert result.completed is True
    assert result.response is not None
    assert ("send", {"to": "unsubscribe@example.com", "subject": "unsubscribe", "body": "unsubscribe"}) in toolbox.calls
    assert "post_one_click_unsubscribe" not in [name for name, _ in toolbox.calls]
    assert '"failed": 2' in result.response
    assert '"request_sent": 1' in result.response
