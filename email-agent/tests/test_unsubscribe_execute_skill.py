from __future__ import annotations

import json
import threading
from pathlib import Path

from intent_layer import PythonSkillExecutor, SkillInputFieldSpec, SkillSpec, build_tool_function_map
from tools.unsubscribe_tools import classify_unsubscribe_method, parse_list_unsubscribe_header, parse_mailto_url


class UnsubscribeExecuteToolBox:
    def __init__(self, message_kind: str):
        self.message_kind = message_kind
        self.one_click_status = "confirmed"
        self.calls: list[tuple[str, dict[str, object]]] = []
        self._lock = threading.Lock()

    def _record(self, tool_name: str, **kwargs: object) -> None:
        with self._lock:
            self.calls.append((tool_name, kwargs))

    def get_email_headers(self, email_id: str, header_names=None) -> str:
        self._record("get_email_headers", email_id=email_id, header_names=header_names)
        if self.message_kind == "one_click":
            headers = {
                "From": "Deals <deals@example.com>",
                "Subject": "Weekly deals",
                "List-Unsubscribe": "<https://example.com/one-click?id=123>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                "List-Id": "<deals.example.com>",
                "Precedence": "bulk",
            }
        elif self.message_kind == "mailto":
            headers = {
                "From": "Vendor <vendor@example.com>",
                "Subject": "Product news",
                "List-Unsubscribe": "<mailto:unsubscribe@example.com?subject=unsubscribe>",
                "List-Unsubscribe-Post": "",
                "List-Id": "<vendor.example.com>",
                "Precedence": "bulk",
            }
        else:
            headers = {
                "From": "Service <service@example.com>",
                "Subject": "Account notice",
                "List-Unsubscribe": "<https://service.example.com/preferences>",
                "List-Unsubscribe-Post": "",
                "List-Id": "<service.example.com>",
                "Precedence": "bulk",
            }
        return json.dumps({"ok": True, "email_id": email_id, "headers": headers}, ensure_ascii=False)

    def post_one_click_unsubscribe(self, url: str) -> str:
        self._record("post_one_click_unsubscribe", url=url)
        http_status = 202 if self.one_click_status == "request_accepted" else 204
        return json.dumps(
            {
                "status": self.one_click_status,
                "sender_unsubscribe_status": self.one_click_status,
                "gmail_subscription_ui_status": "not_updated_by_agent",
                "http_status": http_status,
                "url": url,
                "evidence": f"HTTP {http_status} response received.",
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
        tool_function_map=build_tool_function_map(
            [toolbox, parse_list_unsubscribe_header, classify_unsubscribe_method, parse_mailto_url]
        ),
    )


def _spec() -> SkillSpec:
    return SkillSpec(
        name="unsubscribe_execute",
        description="Execute unsubscribe.",
        scope="Confirmed unsubscribe only.",
        used_tools=(
            "get_email_headers",
            "parse_list_unsubscribe_header",
            "classify_unsubscribe_method",
            "post_one_click_unsubscribe",
            "parse_mailto_url",
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
    assert [name for name, _ in toolbox.calls] == ["get_email_headers"]


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


def test_unsubscribe_execute_website_returns_manual_required_without_opening_url():
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
    assert "status: manual_required" in result.response
    assert "post_one_click_unsubscribe" not in [name for name, _ in toolbox.calls]
    assert "send" not in [name for name, _ in toolbox.calls]
