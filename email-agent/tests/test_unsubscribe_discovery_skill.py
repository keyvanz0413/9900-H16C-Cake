from __future__ import annotations

import json
import threading
from pathlib import Path

from intent_layer import PythonSkillExecutor, SkillInputFieldSpec, SkillSpec, build_tool_function_map


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
                        },
                        "website": {
                            "url": "https://vendor.test/preferences",
                            "manual_links": [
                                {
                                    "url": "https://vendor.test/preferences",
                                    "label": "Manage preferences",
                                    "source": "list_unsubscribe_header",
                                }
                            ],
                        },
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


def test_unsubscribe_discovery_skill_classifies_candidates_without_side_effect_tools():
    toolbox = UnsubscribeDiscoveryToolBox()
    executor = PythonSkillExecutor(
        skills_directory=Path(__file__).resolve().parent.parent / "skills",
        tool_function_map=build_tool_function_map([toolbox]),
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
    assert "No POST request, mailto message, website visit, browser automation, archive, or label action was performed." in result.response
    assert '"method": "one_click"' in result.response
    assert '"method": "mailto"' in result.response
    assert '"method": "website"' in result.response

    called_tool_names = [name for name, _ in toolbox.calls]
    assert called_tool_names == [
        "search_emails",
        "get_unsubscribe_info",
    ]
