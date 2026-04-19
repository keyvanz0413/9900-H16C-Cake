from __future__ import annotations

import json
import threading
from pathlib import Path

from intent_layer import PythonSkillExecutor, SkillInputFieldSpec, SkillSpec, build_tool_function_map


class UnsubscribeExecuteToolBox:
    def __init__(self, message_kind: str):
        self.message_kind = message_kind
        self.one_click_status = "confirmed"
        self.one_click_evidence = ""
        self.calls: list[tuple[str, dict[str, object]]] = []
        self._lock = threading.Lock()

    def _record(self, tool_name: str, **kwargs: object) -> None:
        with self._lock:
            self.calls.append((tool_name, kwargs))

    def get_unsubscribe_info(self, email_ids, max_manual_links: int = 5) -> str:
        self._record("get_unsubscribe_info", email_ids=email_ids, max_manual_links=max_manual_links)
        email_id = email_ids[0]
        if self.message_kind == "one_click":
            unsubscribe = {
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
            }
        elif self.message_kind == "mailto":
            unsubscribe = {
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
            }
        else:
            unsubscribe = {
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
            }
        return json.dumps(
            {
                "items": [
                    {
                        "email_id": email_id,
                        "unsubscribe": unsubscribe,
                        "error": "",
                    }
                ],
                "summary": {
                    "requested_count": 1,
                    "analyzed_count": 1,
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
            "get_unsubscribe_info",
            "post_one_click_unsubscribe",
            "send",
        ),
        output="execution result",
        input_schema=(
            SkillInputFieldSpec(
                name="email_id",
                field_type="string",
                required=True,
                description="Gmail message id.",
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
    toolbox = UnsubscribeExecuteToolBox("one_click")
    result = _executor_for(toolbox).run(
        _spec(),
        skill_arguments={"email_id": "msg-001", "confirmed": False},
        current_message="Unsubscribe from this.",
        intent_decision=type("Intent", (), {"intent": "Unsubscribe from a sender."})(),
        recent_context=[],
    )

    assert result.completed is True
    assert result.response is not None
    assert "status: needs_confirmation" in result.response
    assert [name for name, _ in toolbox.calls] == ["get_unsubscribe_info"]


def test_unsubscribe_execute_one_click_posts_after_confirmation():
    toolbox = UnsubscribeExecuteToolBox("one_click")
    result = _executor_for(toolbox).run(
        _spec(),
        skill_arguments={"email_id": "msg-001", "confirmed": True},
        current_message="Yes, unsubscribe.",
        intent_decision=type("Intent", (), {"intent": "Confirm unsubscribe."})(),
        recent_context=[],
    )

    assert result.completed is True
    assert result.response is not None
    assert "status: confirmed" in result.response
    assert "gmail_subscription_ui_status: not_updated_by_agent" in result.response
    assert ("post_one_click_unsubscribe", {"url": "https://example.com/one-click?id=123"}) in toolbox.calls


def test_unsubscribe_execute_preserves_one_click_request_accepted_status():
    toolbox = UnsubscribeExecuteToolBox("one_click")
    toolbox.one_click_status = "request_accepted"
    result = _executor_for(toolbox).run(
        _spec(),
        skill_arguments={"email_id": "msg-001", "confirmed": True},
        current_message="Yes, unsubscribe.",
        intent_decision=type("Intent", (), {"intent": "Confirm unsubscribe."})(),
        recent_context=[],
    )

    assert result.completed is True
    assert result.response is not None
    assert "status: request_accepted" in result.response
    assert "sender_unsubscribe_status: request_accepted" in result.response
    assert "gmail_subscription_ui_status: not_updated_by_agent" in result.response


def test_unsubscribe_execute_returns_manual_link_when_one_click_fails():
    toolbox = UnsubscribeExecuteToolBox("one_click")
    toolbox.one_click_status = "failed"
    toolbox.one_click_evidence = "HTTP 403 response received."
    result = _executor_for(toolbox).run(
        _spec(),
        skill_arguments={"email_id": "msg-001", "confirmed": True},
        current_message="Yes, unsubscribe.",
        intent_decision=type("Intent", (), {"intent": "Confirm unsubscribe."})(),
        recent_context=[],
    )

    assert result.completed is True
    assert result.response is not None
    assert "status: manual_link_available" in result.response
    assert "https://example.com/manual-unsubscribe?token=abc" in result.response
    assert "get_unsubscribe_info" in [name for name, _ in toolbox.calls]


def test_unsubscribe_execute_mailto_sends_request_but_not_confirmed():
    toolbox = UnsubscribeExecuteToolBox("mailto")
    result = _executor_for(toolbox).run(
        _spec(),
        skill_arguments={"email_id": "msg-002", "confirmed": True},
        current_message="Yes, send the unsubscribe request.",
        intent_decision=type("Intent", (), {"intent": "Confirm unsubscribe."})(),
        recent_context=[],
    )

    assert result.completed is True
    assert result.response is not None
    assert "status: request_sent" in result.response
    assert ("send", {"to": "unsubscribe@example.com", "subject": "unsubscribe", "body": "unsubscribe"}) in toolbox.calls


def test_unsubscribe_execute_website_returns_manual_link_without_opening_url():
    toolbox = UnsubscribeExecuteToolBox("website")
    result = _executor_for(toolbox).run(
        _spec(),
        skill_arguments={"email_id": "msg-003", "confirmed": True},
        current_message="Yes, unsubscribe.",
        intent_decision=type("Intent", (), {"intent": "Confirm unsubscribe."})(),
        recent_context=[],
    )

    assert result.completed is True
    assert result.response is not None
    assert "status: manual_link_available" in result.response
    assert "https://service.example.com/preferences" in result.response
    assert "post_one_click_unsubscribe" not in [name for name, _ in toolbox.calls]
    assert "send" not in [name for name, _ in toolbox.calls]
