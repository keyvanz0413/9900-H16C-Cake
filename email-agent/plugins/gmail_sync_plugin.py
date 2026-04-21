"""Local Gmail-related plugins for post-send CRM synchronization."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

try:
    from connectonion.core.events import after_each_tool
except ImportError:
    from connectonion.events import after_tool as after_each_tool


def build_gmail_sync_plugin(email_tool_getter: Callable[[], Any]) -> list[Callable[[Any], None]]:
    """Create an after-send plugin that updates CRM metadata for sent emails."""

    @after_each_tool
    def sync_crm_after_send_compat(agent_instance) -> None:
        current_session = getattr(agent_instance, "current_session", None)
        if not isinstance(current_session, dict):
            return

        trace_items = current_session.get("trace") or []
        if not trace_items:
            return

        latest_trace = trace_items[-1]
        if not isinstance(latest_trace, dict):
            return
        if latest_trace.get("type") != "tool_result":
            return
        if latest_trace.get("name") not in {"send", "reply"}:
            return
        if latest_trace.get("status") != "success":
            return

        args = latest_trace.get("args") or {}
        if not isinstance(args, dict):
            return

        to = str(args.get("to") or "").strip()
        if not to:
            return

        email_tool = email_tool_getter()
        if email_tool is None or not hasattr(email_tool, "update_contact"):
            return

        try:
            today = datetime.now().strftime("%Y-%m-%d")
            result = email_tool.update_contact(to, last_contact=today, next_contact_date="")
        except Exception as exc:
            print(f"[crm-sync] failed to update contact after send for {to}: {exc}", flush=True)
            return

        if "Updated" in str(result or ""):
            print(f"[crm-sync] updated contact after send: {to}", flush=True)

    return [sync_crm_after_send_compat]
