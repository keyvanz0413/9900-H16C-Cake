"""Local Calendar approval plugin with frontend, CLI, and non-interactive fallback."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

try:
    from connectonion.core.events import before_each_tool
except ImportError:
    from connectonion.events import before_tool as before_each_tool
try:
    from connectonion.tui import pick
except ImportError:
    from connectonion import pick
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

if TYPE_CHECKING:
    try:
        from connectonion.core.agent import Agent
    except ImportError:
        from connectonion.agent import Agent

_console = Console()
WRITE_METHODS = ("create_event", "create_meet", "update_event", "delete_event")


def _has_interactive_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _is_auto_approved(agent: "Agent", tool_name: str) -> bool:
    session = agent.current_session
    if session.get("calendar_approve_all", False):
        return True
    return tool_name in session.get("calendar_approved_tools", set())


def _build_preview(tool_name: str, args: dict[str, Any]) -> tuple[Text, str, str]:
    preview = Text()

    if tool_name == "create_event":
        title = args.get("title", "")
        start = args.get("start_time", "")
        end = args.get("end_time", "")
        attendees = args.get("attendees", "")
        location = args.get("location", "")
        description = args.get("description", "")

        preview.append("Title: ", style="bold cyan")
        preview.append(f"{title}\n")
        preview.append("Start: ", style="bold cyan")
        preview.append(f"{start}\n")
        preview.append("End: ", style="bold cyan")
        preview.append(f"{end}\n")
        if attendees:
            preview.append("Attendees: ", style="bold yellow")
            preview.append(f"{attendees} (will receive invite!)\n")
        if location:
            preview.append("Location: ", style="bold cyan")
            preview.append(f"{location}\n")
        if description:
            preview.append("\n")
            preview.append(description[:300])

        return preview, "Create Event", f"Create calendar event '{title}'"

    if tool_name == "create_meet":
        title = args.get("title", "")
        start = args.get("start_time", "")
        end = args.get("end_time", "")
        attendees = args.get("attendees", "")
        description = args.get("description", "")

        preview.append("Title: ", style="bold cyan")
        preview.append(f"{title}\n")
        preview.append("Start: ", style="bold cyan")
        preview.append(f"{start}\n")
        preview.append("End: ", style="bold cyan")
        preview.append(f"{end}\n")
        preview.append("Attendees: ", style="bold yellow")
        preview.append(f"{attendees} (will receive Meet invite!)\n")
        if description:
            preview.append("\n")
            preview.append(description[:300])

        return preview, "Create Meeting", f"Create calendar meeting '{title}'"

    if tool_name == "update_event":
        event_id = args.get("event_id", "")
        title = args.get("title", "")
        start = args.get("start_time", "")
        end = args.get("end_time", "")
        attendees = args.get("attendees", "")

        preview.append("Event ID: ", style="bold cyan")
        preview.append(f"{event_id}\n")
        if title:
            preview.append("New Title: ", style="bold cyan")
            preview.append(f"{title}\n")
        if start:
            preview.append("New Start: ", style="bold cyan")
            preview.append(f"{start}\n")
        if end:
            preview.append("New End: ", style="bold cyan")
            preview.append(f"{end}\n")
        if attendees:
            preview.append("New Attendees: ", style="bold yellow")
            preview.append(f"{attendees} (will be notified!)\n")

        return preview, "Update Event", f"Update calendar event {event_id}"

    event_id = args.get("event_id", "")
    preview.append("Event ID: ", style="bold red")
    preview.append(f"{event_id}\n\n")
    preview.append("This will permanently delete the event!", style="red")

    return preview, "Delete Event", f"Delete calendar event {event_id}"


def _checkpoint(agent: "Agent") -> None:
    storage = getattr(agent, "storage", None)
    if storage:
        storage.checkpoint(agent.current_session)


def _wait_for_approval_response(agent: "Agent") -> dict[str, Any]:
    while True:
        response = agent.io.receive()
        response_type = response.get("type")

        if response_type == "io_closed":
            raise ValueError("Connection closed while waiting for Calendar approval.")

        if response_type in (None, "APPROVAL_RESPONSE") and "approved" in response:
            return response


def _handle_frontend_response(agent: "Agent", tool_name: str, response: dict[str, Any]) -> None:
    if response.get("approved", False):
        if response.get("scope") == "session":
            agent.current_session.setdefault("calendar_approved_tools", set()).add(tool_name)
        return

    feedback = response.get("feedback", "")
    mode = response.get("mode", "reject_hard")

    if mode == "reject_hard":
        agent.current_session["stop_signal"] = feedback or f"User rejected Calendar tool '{tool_name}'."
        raise ValueError(
            f"User rejected Calendar tool '{tool_name}'."
            + (f" Feedback: {feedback}" if feedback else "")
        )

    if mode == "reject_explain":
        raise ValueError(
            f"User wants explanation before Calendar tool '{tool_name}'."
            + (f" Context: {feedback}" if feedback else "")
            + "\n\n<system-reminder>"
            "Explain this calendar action in simple language, why it is needed, and what will happen next. "
            "Do not retry the calendar write until the user explicitly approves."
            "</system-reminder>"
        )

    raise ValueError(
        f"User rejected Calendar tool '{tool_name}'."
        + (f" Feedback: {feedback}" if feedback else "")
        + "\n\n<system-reminder>"
        "Do not retry this calendar change automatically. Ask the user what they want changed first."
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


def _request_cli_approval(agent: "Agent", title: str, preview: Text) -> None:
    _console.print()
    _console.print(Panel(preview, title=f"[yellow]{title}[/yellow]", border_style="yellow"))

    options = [f"Yes, {title.lower()}"]
    options.append("Auto approve all calendar actions this session")
    options.append("No, tell agent what I want")

    choice = pick(f"Proceed with {title.lower()}?", options, console=_console)

    if choice.startswith("Yes"):
        return
    if choice == "Auto approve all calendar actions this session":
        agent.current_session["calendar_approve_all"] = True
        return

    feedback = input("What do you want the agent to do instead? ")
    raise ValueError(f"User feedback: {feedback}")


@before_each_tool
def check_calendar_approval(agent: "Agent") -> None:
    pending = agent.current_session.get("pending_tool")
    if not pending:
        return

    tool_name = pending["name"]
    if tool_name not in WRITE_METHODS:
        return

    if _is_auto_approved(agent, tool_name):
        return

    args = pending["arguments"]
    preview, title, description = _build_preview(tool_name, args)

    if getattr(agent, "io", None):
        _request_frontend_approval(agent, tool_name, args, description)
        return

    if _has_interactive_terminal():
        _request_cli_approval(agent, title, preview)
        return

    # In plain HTTP/background mode there is no approval transport and no TTY.
    # Let the tool proceed instead of failing with a terminal IO error.
    return


calendar_approval_plugin = [
    check_calendar_approval,
]
