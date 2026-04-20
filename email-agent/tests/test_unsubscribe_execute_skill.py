from __future__ import annotations

import json
import threading
from pathlib import Path

from intent_layer import PythonSkillExecutor, SkillInputFieldSpec, SkillSpec, build_tool_function_map
from unsubscribe_workflow import candidate_id_for_sender, extract_section_text


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
        normalized_query = str(query)
        if "Qudos Bank Arena" in normalized_query:
            return (
                "Found 1 email(s):\n\n"
                "1. From: Qudos Bank Arena <news@qudosbankarena.com.au>\n"
                "   Subject: Qudos Bank Arena events\n"
                "   ID: unsub-004\n"
            )
        if "Mismatch Brand" in normalized_query:
            return (
                "Found 1 email(s):\n\n"
                "1. From: Deals <deals@example.com>\n"
                "   Subject: Weekly deals\n"
                "   ID: unsub-001\n"
            )
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
                        }
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
            "unsub-004": {
                "email_id": "unsub-004",
                "unsubscribe": {
                    "method": "one_click",
                    "options": {
                        "one_click": {
                            "url": "https://qudos.example.com/unsubscribe?id=456",
                            "request_payload": {"url": "https://qudos.example.com/unsubscribe?id=456"},
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


def _spec() -> SkillSpec:
    return SkillSpec(
        name="unsubscribe_execute",
        description="Execute unsubscribe.",
        scope="Multi-target unsubscribe.",
        used_tools=(
            "search_emails",
            "get_unsubscribe_info",
            "post_one_click_unsubscribe",
            "send",
        ),
        output="execution result",
        input_schema=(
            SkillInputFieldSpec(
                name="target_queries",
                field_type="list",
                required=True,
                description="Targets to unsubscribe.",
            ),
            SkillInputFieldSpec(
                name="candidate_ids",
                field_type="list",
                required=False,
                description="Optional candidate ids.",
                has_default=True,
                default=[],
            ),
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
        ),
    )


def _executor_for(toolbox: UnsubscribeExecuteToolBox, state_path: Path) -> PythonSkillExecutor:
    return PythonSkillExecutor(
        skills_directory=Path(__file__).resolve().parent.parent / "skills",
        tool_function_map=build_tool_function_map([toolbox]),
        skill_runtime={"unsubscribe_state_path": str(state_path)},
    )


def _write_state(path: Path, items: list[dict[str, object]]) -> None:
    path.write_text(json.dumps({"version": 1, "items": items}, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_section_list(response: str, section_name: str) -> list[dict[str, object]]:
    text = extract_section_text(response, section_name)
    return json.loads(text) if text else []


def test_unsubscribe_execute_marks_new_successful_target_hidden(tmp_path):
    toolbox = UnsubscribeExecuteToolBox()
    state_path = tmp_path / "UNSUBSCRIBE_STATE.json"
    _write_state(
        state_path,
        [
            {
                "candidate_id": candidate_id_for_sender(sender_email="product@vendor.test", sender_domain="vendor.test"),
                "sender": "Product <product@vendor.test>",
                "sender_email": "product@vendor.test",
                "sender_domain": "vendor.test",
                "representative_email_id": "unsub-002",
                "status": "active",
                "updated_at": "2026-04-20T00:00:00+00:00",
                "method": "mailto",
            }
        ],
    )

    result = _executor_for(toolbox, state_path).run(
        _spec(),
        skill_arguments={"target_queries": ["Product"], "candidate_ids": [], "days": 30, "max_results": 20},
        current_message="Unsubscribe from Product.",
        intent_decision=type("Intent", (), {"intent": "Unsubscribe from Product."})(),
        recent_context=[],
        read_results=[],
    )

    assert result.completed is True
    assert result.response is not None
    assert ("send", {"to": "unsubscribe@example.com", "subject": "unsubscribe", "body": "unsubscribe"}) in toolbox.calls
    search_calls = [call for call in toolbox.calls if call[0] == "search_emails"]
    assert len(search_calls) == 1
    assert "Product" in str(search_calls[0][1]["query"])

    newly_unsubscribed = _read_section_list(result.response, "NEWLY_UNSUBSCRIBED_JSON")
    assert len(newly_unsubscribed) == 1
    assert newly_unsubscribed[0]["sender_email"] == "product@vendor.test"

    stored_payload = json.loads(state_path.read_text(encoding="utf-8"))
    statuses = {item["sender_email"]: item["status"] for item in stored_payload["items"]}
    assert statuses["product@vendor.test"] == "hidden_locally_after_unsubscribe"


def test_unsubscribe_execute_reports_already_hidden_without_reexecution(tmp_path):
    toolbox = UnsubscribeExecuteToolBox()
    state_path = tmp_path / "UNSUBSCRIBE_STATE.json"
    _write_state(
        state_path,
        [
            {
                "candidate_id": candidate_id_for_sender(sender_email="news@qudosbankarena.com.au", sender_domain="qudosbankarena.com.au"),
                "sender": "Qudos Bank Arena <news@qudosbankarena.com.au>",
                "sender_email": "news@qudosbankarena.com.au",
                "sender_domain": "qudosbankarena.com.au",
                "representative_email_id": "unsub-004",
                "status": "hidden_locally_after_unsubscribe",
                "updated_at": "2026-04-20T00:00:00+00:00",
                "method": "one_click",
            }
        ],
    )

    result = _executor_for(toolbox, state_path).run(
        _spec(),
        skill_arguments={"target_queries": ["Qudos Bank Arena"], "candidate_ids": [], "days": 30, "max_results": 20},
        current_message="Unsubscribe from Qudos Bank Arena.",
        intent_decision=type("Intent", (), {"intent": "Unsubscribe from Qudos Bank Arena."})(),
        recent_context=[],
        read_results=[],
    )

    assert result.completed is True
    called_tool_names = [name for name, _ in toolbox.calls]
    assert "post_one_click_unsubscribe" not in called_tool_names
    assert "send" not in called_tool_names

    already_unsubscribed = _read_section_list(result.response, "ALREADY_UNSUBSCRIBED_JSON")
    assert len(already_unsubscribed) == 1
    assert already_unsubscribed[0]["sender_email"] == "news@qudosbankarena.com.au"


def test_unsubscribe_execute_falls_back_to_targeted_search_for_multiple_targets(tmp_path):
    toolbox = UnsubscribeExecuteToolBox()
    state_path = tmp_path / "UNSUBSCRIBE_STATE.json"
    _write_state(state_path, [])

    result = _executor_for(toolbox, state_path).run(
        _spec(),
        skill_arguments={
            "target_queries": ["Qudos Bank Arena", "Product"],
            "candidate_ids": [],
            "days": 30,
            "max_results": 20,
        },
        current_message="Unsubscribe from Qudos Bank Arena and Product.",
        intent_decision=type("Intent", (), {"intent": "Unsubscribe from Qudos Bank Arena and Product."})(),
        recent_context=[],
        read_results=[],
    )

    assert result.completed is True
    assert result.response is not None

    assert ("post_one_click_unsubscribe", {"url": "https://qudos.example.com/unsubscribe?id=456"}) in toolbox.calls
    assert ("send", {"to": "unsubscribe@example.com", "subject": "unsubscribe", "body": "unsubscribe"}) in toolbox.calls

    fallback_discovery = _read_section_list(result.response, "FALLBACK_DISCOVERY_JSON")
    assert len(fallback_discovery) == 2

    stored_payload = json.loads(state_path.read_text(encoding="utf-8"))
    statuses = {item["sender_email"]: item["status"] for item in stored_payload["items"]}
    assert statuses["news@qudosbankarena.com.au"] == "hidden_locally_after_unsubscribe"
    assert statuses["product@vendor.test"] == "hidden_locally_after_unsubscribe"


def test_unsubscribe_execute_does_not_auto_execute_unmatched_single_fallback_candidate(tmp_path):
    toolbox = UnsubscribeExecuteToolBox()
    state_path = tmp_path / "UNSUBSCRIBE_STATE.json"
    _write_state(state_path, [])

    result = _executor_for(toolbox, state_path).run(
        _spec(),
        skill_arguments={
            "target_queries": ["Mismatch Brand"],
            "candidate_ids": [],
            "days": 30,
            "max_results": 20,
        },
        current_message="Unsubscribe from Mismatch Brand.",
        intent_decision=type("Intent", (), {"intent": "Unsubscribe from Mismatch Brand."})(),
        recent_context=[],
        read_results=[],
    )

    assert result.completed is True
    assert result.response is not None
    assert "post_one_click_unsubscribe" not in [name for name, _ in toolbox.calls]
    assert "send" not in [name for name, _ in toolbox.calls]

    not_found = _read_section_list(result.response, "NOT_FOUND_JSON")
    assert len(not_found) == 1
    assert not_found[0]["target_query"] == "Mismatch Brand"
