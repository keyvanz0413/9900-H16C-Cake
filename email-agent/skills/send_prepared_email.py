from __future__ import annotations

from typing import Any, Callable


def _call_tool(name: str, tool_callable: Callable[..., Any], kwargs: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    print(f"[skill:send_prepared_email] calling {name} with {kwargs}", flush=True)
    try:
        result = tool_callable(**kwargs)
    except Exception as exc:
        result = f"Error: {exc}"
    text = str(result or "").strip() or "(empty)"
    print(f"[skill:send_prepared_email] finished {name}", flush=True)
    return name, kwargs, text


def execute_skill(*, arguments, used_tools, skill_spec):
    to = str(arguments.get("to") or "").strip()
    subject = str(arguments.get("subject") or "").strip()
    body = str(arguments.get("body") or "").strip()
    cc = str(arguments.get("cc") or "").strip()
    bcc = str(arguments.get("bcc") or "").strip()

    send_kwargs = {
        "to": to,
        "subject": subject,
        "body": body,
    }
    if cc:
        send_kwargs["cc"] = cc
    if bcc:
        send_kwargs["bcc"] = bcc

    print(
        f"[skill:send_prepared_email] start to={to or '(empty)'} subject={subject or '(empty)'} "
        f"cc={'yes' if cc else 'no'} bcc={'yes' if bcc else 'no'}",
        flush=True,
    )

    _, resolved_send_kwargs, send_result_text = _call_tool(
        "send",
        used_tools["send"],
        send_kwargs,
    )

    lines = [
        "[SEND_PREPARED_EMAIL_RESULT]",
        f"skill_name: {skill_spec.get('name', 'send_prepared_email')}",
        "notes:",
        "- This skill sends an already-finalized email using the provider's native send tool.",
        "- The email content must already be explicit in the current request or recent conversation context before this skill is selected.",
        "- Finalizer instruction: clearly state that the email was sent only if the send result below indicates success.",
        "- Finalizer instruction: if the send result below contains an error, report that failure clearly and do not claim the email was sent.",
        "",
        "[SEND_EMAIL_RESULT]",
        "tool: send",
        f"arguments: {resolved_send_kwargs}",
        send_result_text,
        "",
        "[SENT_EMAIL_FIELDS]",
        f"to: {to}",
        f"cc: {cc or '(none)'}",
        f"bcc: {bcc or '(none)'}",
        f"subject: {subject}",
        "body:",
        body,
    ]

    send_succeeded = "email sent successfully" in send_result_text.lower()
    if send_succeeded:
        reason = f"Sent the finalized email to {to}."
    else:
        reason = f"The send tool did not confirm success for the prepared email to {to}."

    return {
        "completed": True,
        "response": "\n".join(lines).strip(),
        "reason": reason,
    }
