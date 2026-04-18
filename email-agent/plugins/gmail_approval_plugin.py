"""Local Gmail approval plugin with frontend and CLI approval paths."""

from __future__ import annotations

import sys
from datetime import datetime
from typing import TYPE_CHECKING, Any

from connectonion.core.events import after_each_tool, before_each_tool
from connectonion.tui import pick
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

if TYPE_CHECKING:
    from connectonion.core.agent import Agent

_console = Console()
SEND_METHODS = ("send", "reply")


def _has_interactive_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _is_auto_approved(agent: "Agent", tool_name: str, args: dict[str, Any]) -> bool:
    session = agent.current_session
    if session.get("gmail_approve_all", False):
        return True

    approved_tools = session.get("gmail_approved_tools", set())
    if tool_name in approved_tools:
        return True

    if tool_name == "send":
        approved_recipients = session.get("gmail_approved_recipients", set())
        return args.get("to", "") in approved_recipients

    return tool_name == "reply" and session.get("gmail_approve_replies", False)


def _build_preview(tool_name: str, args: dict[str, Any]) -> tuple[Text, str, str, str | None]:
    preview = Text()

    if tool_name == "send":
        to = args.get("to", "")
        subject = args.get("subject", "")
        body = args.get("body", "")
        cc = args.get("cc", "")
        bcc = args.get("bcc", "")

        preview.append("To: ", style="bold cyan")
        preview.append(f"{to}\n")
        if cc:
            preview.append("CC: ", style="bold cyan")
            preview.append(f"{cc}\n")
        if bcc:
            preview.append("BCC: ", style="bold cyan")
            preview.append(f"{bcc}\n")
        preview.append("Subject: ", style="bold cyan")
        preview.append(f"{subject}\n\n")
        preview.append(body[:500] + ("..." if len(body) > 500 else ""))

        description = f"Send email to {to}" if to else "Send email"
        if subject:
            description += f" with subject '{subject}'"
        return preview, "Email to Send", description, to or None

    email_id = args.get("email_id", "")
    body = args.get("body", "")
    preview.append("Reply to thread: ", style="bold cyan")
    preview.append(f"{email_id}\n\n")
    preview.append(body[:500] + ("..." if len(body) > 500 else ""))

    description = f"Reply to thread {email_id}" if email_id else "Reply to email thread"
    return preview, "Reply to Send", description, None


def _checkpoint(agent: "Agent") -> None:
    storage = getattr(agent, "storage", None)
    if storage:
        storage.checkpoint(agent.current_session)


def _grant_current_tool_execution(agent: "Agent", tool_name: str, args: dict[str, Any]) -> None:
    agent.current_session["gmail_force_send"] = {
        "tool_name": tool_name,
        "args": dict(args),
    }


def _wait_for_approval_response(agent: "Agent") -> dict[str, Any]:
    while True:
        response = agent.io.receive()
        response_type = response.get("type")

        if response_type == "io_closed":
            raise ValueError("Connection closed while waiting for Gmail approval.")

        if response_type in (None, "APPROVAL_RESPONSE") and "approved" in response:
            return response


def _handle_frontend_response(agent: "Agent", tool_name: str, response: dict[str, Any]) -> None:
    if response.get("approved", False):
        _grant_current_tool_execution(
            agent,
            tool_name,
            agent.current_session.get("pending_tool", {}).get("arguments", {}),
        )
        if response.get("scope") == "session":
            agent.current_session.setdefault("gmail_approved_tools", set()).add(tool_name)
        return

    feedback = response.get("feedback", "")
    mode = response.get("mode", "reject_hard")

    if mode == "reject_hard":
        agent.current_session["stop_signal"] = feedback or f"User rejected Gmail tool '{tool_name}'."
        raise ValueError(
            f"User rejected Gmail tool '{tool_name}'."
            + (f" Feedback: {feedback}" if feedback else "")
        )

    if mode == "reject_explain":
        raise ValueError(
            f"User wants explanation before Gmail tool '{tool_name}'."
            + (f" Context: {feedback}" if feedback else "")
            + "\n\n<system-reminder>"
            "Explain this email action in simple language, why it is needed, and what will happen next. "
            "Do not retry the send/reply until the user explicitly approves."
            "</system-reminder>"
        )

    raise ValueError(
        f"User rejected Gmail tool '{tool_name}'."
        + (f" Feedback: {feedback}" if feedback else "")
        + "\n\n<system-reminder>"
        "Do not retry this send/reply automatically. Revise the draft or ask the user what they want changed."
        "</system-reminder>"
    )


def _request_frontend_approval(agent: "Agent", tool_name: str, args: dict[str, Any], description: str) -> None:
    _checkpoint(agent)
    agent.io.send(
        {
            "type": "approval_needed",
            "tool": tool_name,
            "arguments": args,
            "description": description,
        }
    )
    response = _wait_for_approval_response(agent)
    _handle_frontend_response(agent, tool_name, response)


def _request_cli_approval(agent: "Agent", tool_name: str, args: dict[str, Any], title: str, preview: Text, recipient_key: str | None) -> None:
    _console.print()
    _console.print(Panel(preview, title=f"[yellow]{title}[/yellow]", border_style="yellow"))

    options = ["Yes, send it"]
    if tool_name == "send" and recipient_key:
        options.append(f"Auto approve emails to '{recipient_key}'")
    if tool_name == "reply":
        options.append("Auto approve all replies this session")
    options.append("Auto approve all emails this session")

    choice = pick("Send this email?", options, other=True, console=_console)

    if choice == "Yes, send it":
        _grant_current_tool_execution(agent, tool_name, args)
        return
    if choice.startswith("Auto approve emails to"):
        agent.current_session.setdefault("gmail_approved_recipients", set()).add(recipient_key)
        _grant_current_tool_execution(agent, tool_name, args)
        return
    if choice == "Auto approve all replies this session":
        agent.current_session["gmail_approve_replies"] = True
        _grant_current_tool_execution(agent, tool_name, args)
        return
    if choice == "Auto approve all emails this session":
        agent.current_session["gmail_approve_all"] = True
        _grant_current_tool_execution(agent, tool_name, args)
        return
    raise ValueError(f"User feedback: {choice}")


@before_each_tool
def check_email_approval(agent: "Agent") -> None:
    pending = agent.current_session.get("pending_tool")
    if not pending:
        return

    tool_name = pending["name"]
    if tool_name not in SEND_METHODS:
        return

    args = pending["arguments"]
    if _is_auto_approved(agent, tool_name, args):
        return

    preview, title, description, recipient_key = _build_preview(tool_name, args)

    if getattr(agent, "io", None):
        _request_frontend_approval(agent, tool_name, args, description)
        return

    if _has_interactive_terminal():
        _request_cli_approval(agent, tool_name, args, title, preview, recipient_key)
        return

    # In plain HTTP/background mode there is no approval transport. Let the tool
    # itself handle conversational draft confirmation instead of failing here.
    return


@after_each_tool
def sync_crm_after_send(agent: "Agent") -> None:
    trace = agent.current_session["trace"][-1]
    if trace["type"] != "tool_result":
        return
    if trace["name"] not in SEND_METHODS:
        return
    if trace["status"] != "success":
        return

    to = trace["args"].get("to", "")
    if not to:
        return

    gmail = getattr(agent.tools, "gmail", None)
    if gmail is None:
        return

    today = datetime.now().strftime("%Y-%m-%d")
    result = gmail.update_contact(to, last_contact=today, next_contact_date="")

    if "Updated" in result:
        _console.print(f"[dim]CRM updated: {to}[/dim]")


gmail_approval_plugin = [
    check_email_approval,
    sync_crm_after_send,
]
