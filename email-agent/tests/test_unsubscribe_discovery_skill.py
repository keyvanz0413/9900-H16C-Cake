from __future__ import annotations

import json
import threading
from pathlib import Path

from intent_layer import PythonSkillExecutor, SkillInputFieldSpec, SkillSpec, build_tool_function_map
from tools.unsubscribe_tools import classify_unsubscribe_method, parse_list_unsubscribe_header


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

    def get_email_headers(self, email_id: str, header_names=None) -> str:
        self._record("get_email_headers", email_id=email_id, header_names=header_names)
        payloads = {
            "unsub-001": {
                "ok": True,
                "email_id": "unsub-001",
                "thread_id": "thread-001",
                "headers": {
                    "From": "Deals <deals@example.com>",
                    "Subject": "Weekly deals",
                    "Date": "Fri, 18 Apr 2026 09:00:00 +0000",
                    "List-Unsubscribe": "<https://example.com/one-click?id=123>",
                    "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                    "List-Id": "<deals.example.com>",
                    "Precedence": "bulk",
                },
            },
            "unsub-002": {
                "ok": True,
                "email_id": "unsub-002",
                "thread_id": "thread-002",
                "headers": {
                    "From": "Product <product@vendor.test>",
                    "Subject": "Product update",
                    "Date": "Fri, 18 Apr 2026 08:00:00 +0000",
                    "List-Unsubscribe": "<mailto:unsubscribe@vendor.test?subject=unsubscribe>, <https://vendor.test/preferences>",
                    "List-Unsubscribe-Post": "",
                    "List-Id": "<product.vendor.test>",
                    "Precedence": "bulk",
                },
            },
            "unsub-003": {
                "ok": True,
                "email_id": "unsub-003",
                "thread_id": "thread-003",
                "headers": {
                    "From": "Alerts <alerts@service.test>",
                    "Subject": "Account notice",
                    "Date": "Fri, 18 Apr 2026 07:00:00 +0000",
                    "List-Unsubscribe": "<https://service.test/email-settings>",
                    "List-Unsubscribe-Post": "",
                    "List-Id": "<alerts.service.test>",
                    "Precedence": "",
                },
            },
        }
        return json.dumps(payloads[email_id], ensure_ascii=False)


def test_unsubscribe_discovery_skill_classifies_candidates_without_side_effect_tools():
    toolbox = UnsubscribeDiscoveryToolBox()
    executor = PythonSkillExecutor(
        skills_directory=Path(__file__).resolve().parent.parent / "skills",
        tool_function_map=build_tool_function_map(
            [toolbox, parse_list_unsubscribe_header, classify_unsubscribe_method]
        ),
    )
    spec = SkillSpec(
        name="unsubscribe_discovery",
        description="Discover unsubscribe candidates.",
        scope="Read-only.",
        used_tools=(
            "search_emails",
            "get_email_headers",
            "parse_list_unsubscribe_header",
            "classify_unsubscribe_method",
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
        "get_email_headers",
        "get_email_headers",
        "get_email_headers",
    ]
