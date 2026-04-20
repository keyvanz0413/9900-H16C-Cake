from __future__ import annotations

import json
import threading
from pathlib import Path

from intent_layer import PythonSkillExecutor, SkillInputFieldSpec, SkillSpec, build_tool_function_map
from unsubscribe_workflow import candidate_id_for_sender, extract_section_text


class UnsubscribeDiscoveryToolBox:
    def __init__(self):
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
                            "url": "mailto:unsubscribe@vendor.test?subject=unsubscribe",
                            "send_payload": {
                                "to": "unsubscribe@vendor.test",
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
                            "url": "https://service.test/email-settings",
                            "manual_links": [
                                {
                                    "url": "https://service.test/email-settings",
                                    "label": "Email settings",
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


def _state_payload() -> dict[str, object]:
    return {
        "version": 1,
        "items": [
            {
                "candidate_id": candidate_id_for_sender(sender_email="existing@active.test", sender_domain="active.test"),
                "sender": "Existing Active <existing@active.test>",
                "sender_email": "existing@active.test",
                "sender_domain": "active.test",
                "representative_email_id": "existing-001",
                "status": "active",
                "updated_at": "2026-04-20T00:00:00+00:00",
                "method": "mailto",
            },
            {
                "candidate_id": candidate_id_for_sender(sender_email="alerts@service.test", sender_domain="service.test"),
                "sender": "Alerts <alerts@service.test>",
                "sender_email": "alerts@service.test",
                "sender_domain": "service.test",
                "representative_email_id": "unsub-003",
                "status": "hidden_locally_after_unsubscribe",
                "updated_at": "2026-04-20T00:00:00+00:00",
                "method": "website",
            },
        ],
    }


def test_unsubscribe_discovery_merges_live_results_and_filters_hidden_state(tmp_path):
    toolbox = UnsubscribeDiscoveryToolBox()
    state_path = tmp_path / "UNSUBSCRIBE_STATE.json"
    state_path.write_text(json.dumps(_state_payload(), ensure_ascii=False, indent=2), encoding="utf-8")

    executor = PythonSkillExecutor(
        skills_directory=Path(__file__).resolve().parent.parent / "skills",
        tool_function_map=build_tool_function_map([toolbox]),
        skill_runtime={"unsubscribe_state_path": str(state_path)},
    )
    spec = SkillSpec(
        name="unsubscribe_discovery",
        description="Discover unsubscribe candidates.",
        scope="Read-only.",
        used_tools=(
            "search_emails",
            "get_unsubscribe_info",
        ),
        output="candidate list",
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
        ),
    )

    result = executor.run(
        spec,
        skill_arguments={"days": 30, "max_results": 20},
        current_message="Find newsletters I can unsubscribe from.",
        intent_decision=type("Intent", (), {"intent": "Discover unsubscribe candidates."})(),
        recent_context=[],
    )

    assert result.completed is True
    assert result.response is not None
    assert "[UNSUBSCRIBE_DISCOVERY_BUNDLE]" in result.response

    visible_candidates = json.loads(extract_section_text(result.response, "VISIBLE_CANDIDATES_JSON"))
    visible_emails = {item["sender_email"] for item in visible_candidates}
    assert "existing@active.test" in visible_emails
    assert "deals@example.com" in visible_emails
    assert "product@vendor.test" in visible_emails
    assert "alerts@service.test" not in visible_emails

    stored_payload = json.loads(state_path.read_text(encoding="utf-8"))
    stored_items = {item["candidate_id"]: item for item in stored_payload["items"]}
    assert len(stored_items) == 4
    hidden_alerts_id = candidate_id_for_sender(sender_email="alerts@service.test", sender_domain="service.test")
    assert stored_items[hidden_alerts_id]["status"] == "hidden_locally_after_unsubscribe"

    called_tool_names = [name for name, _ in toolbox.calls]
    assert called_tool_names == [
        "search_emails",
        "get_unsubscribe_info",
    ]
