from __future__ import annotations

import json
from typing import Any, Callable


HEADER_NAMES = [
    "From",
    "Subject",
    "Date",
    "List-Unsubscribe",
    "List-Unsubscribe-Post",
    "List-Id",
    "Precedence",
]
ALLOWED_METHODS = {"auto", "one_click", "mailto", "website"}


def _call_tool(name: str, tool_callable: Callable[..., Any], kwargs: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    print(f"[skill:unsubscribe_execute] calling {name} with {kwargs}", flush=True)
    try:
        result = tool_callable(**kwargs)
    except Exception as exc:
        result = f"Error: {exc}"
    text = str(result or "").strip() or "(empty)"
    print(f"[skill:unsubscribe_execute] finished {name}", flush=True)
    return name, kwargs, text


def _loads_mapping(raw_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(str(raw_text or "").strip())
    except json.JSONDecodeError:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _normalize_method(raw_method: Any) -> str:
    method = str(raw_method or "auto").strip().lower()
    if method in {"one-click", "one click", "oneclick"}:
        method = "one_click"
    if method not in ALLOWED_METHODS:
        return "auto"
    return method


def _confirmation_result(*, email_id: str, classified_method: str, headers: dict[str, Any], classification: dict[str, Any]) -> dict[str, Any]:
    return {
        "completed": True,
        "response": "\n".join(
            [
                "[UNSUBSCRIBE_EXECUTE_BUNDLE]",
                f"email_id: {email_id}",
                "status: needs_confirmation",
                f"classified_method: {classified_method}",
                f"from: {headers.get('From') or '(unknown)'}",
                f"subject: {headers.get('Subject') or '(no subject)'}",
                "notes:",
                "- No unsubscribe action was executed because confirmed=false.",
                "- Reply with explicit confirmation before execution.",
                "",
                "[CLASSIFICATION_JSON]",
                json.dumps(classification, ensure_ascii=False, indent=2, sort_keys=True),
            ]
        ).strip(),
        "reason": "Execution requires explicit user confirmation; no unsubscribe action was performed.",
    }


def execute_skill(*, arguments, used_tools, skill_spec):
    email_id = str(arguments.get("email_id") or "").strip()
    requested_method = _normalize_method(arguments.get("method", "auto"))
    confirmed = bool(arguments.get("confirmed", False))

    print(
        f"[skill:unsubscribe_execute] start email_id={email_id or '(empty)'} method={requested_method} confirmed={confirmed}",
        flush=True,
    )

    if not email_id:
        return {
            "completed": True,
            "response": "[UNSUBSCRIBE_EXECUTE_BUNDLE]\nstatus: failed\nreason: Missing required email_id.\nNo unsubscribe action was executed.",
            "reason": "Missing required email_id.",
        }

    _, header_kwargs, header_text = _call_tool(
        "get_email_headers",
        used_tools["get_email_headers"],
        {"email_id": email_id, "header_names": HEADER_NAMES},
    )
    header_payload = _loads_mapping(header_text)
    headers = header_payload.get("headers") if isinstance(header_payload.get("headers"), dict) else {}
    if not header_payload.get("ok"):
        return {
            "completed": True,
            "response": "\n".join(
                [
                    "[UNSUBSCRIBE_EXECUTE_BUNDLE]",
                    f"email_id: {email_id}",
                    "status: failed",
                    f"reason: Could not fetch message headers: {header_payload.get('error') or 'unknown error'}",
                    "No unsubscribe action was executed.",
                ]
            ),
            "reason": "Could not fetch message headers.",
        }

    list_unsubscribe = str(headers.get("List-Unsubscribe") or "").strip()
    list_unsubscribe_post = str(headers.get("List-Unsubscribe-Post") or "").strip()

    _, parse_kwargs, parsed_text = _call_tool(
        "parse_list_unsubscribe_header",
        used_tools["parse_list_unsubscribe_header"],
        {"header_value": list_unsubscribe},
    )
    parsed_payload = _loads_mapping(parsed_text)

    _, classify_kwargs, classification_text = _call_tool(
        "classify_unsubscribe_method",
        used_tools["classify_unsubscribe_method"],
        {
            "parsed_list_unsubscribe": parsed_payload,
            "list_unsubscribe_post": list_unsubscribe_post,
        },
    )
    classification = _loads_mapping(classification_text)
    classified_method = str(classification.get("method") or "unknown").strip() or "unknown"
    effective_method = classified_method if requested_method == "auto" else requested_method

    if requested_method != "auto" and requested_method != classified_method:
        return {
            "completed": True,
            "response": "\n".join(
                [
                    "[UNSUBSCRIBE_EXECUTE_BUNDLE]",
                    f"email_id: {email_id}",
                    "status: failed",
                    f"requested_method: {requested_method}",
                    f"classified_method: {classified_method}",
                    "reason: Requested method does not match the message headers.",
                    "No unsubscribe action was executed.",
                    "",
                    "[CLASSIFICATION_JSON]",
                    json.dumps(classification, ensure_ascii=False, indent=2, sort_keys=True),
                ]
            ),
            "reason": "Requested method did not match the current header classification.",
        }

    if not confirmed:
        return _confirmation_result(
            email_id=email_id,
            classified_method=classified_method,
            headers=headers,
            classification=classification,
        )

    execution_status = "failed"
    sender_unsubscribe_status = "failed"
    gmail_subscription_ui_status = "not_updated_by_agent"
    execution_evidence = ""
    execution_payload: dict[str, Any] = {}
    execution_tool = "(none)"
    execution_kwargs: dict[str, Any] = {}

    if effective_method == "one_click":
        one_click_url = str(classification.get("one_click_url") or "").strip()
        if not one_click_url:
            execution_status = "failed"
            execution_evidence = "No one-click URL was available after re-reading headers."
        else:
            execution_tool, execution_kwargs, execution_text = _call_tool(
                "post_one_click_unsubscribe",
                used_tools["post_one_click_unsubscribe"],
                {"url": one_click_url},
            )
            execution_payload = _loads_mapping(execution_text)
            execution_status = str(execution_payload.get("status") or "uncertain")
            sender_unsubscribe_status = str(
                execution_payload.get("sender_unsubscribe_status")
                or execution_payload.get("status")
                or "uncertain"
            )
            gmail_subscription_ui_status = str(
                execution_payload.get("gmail_subscription_ui_status") or "not_updated_by_agent"
            )
            execution_evidence = str(execution_payload.get("evidence") or "").strip()

    elif effective_method == "mailto":
        mailto_url = str(classification.get("mailto_url") or "").strip()
        if not mailto_url:
            execution_status = "failed"
            execution_evidence = "No mailto URL was available after re-reading headers."
        else:
            _, parse_mailto_kwargs, parse_mailto_text = _call_tool(
                "parse_mailto_url",
                used_tools["parse_mailto_url"],
                {"mailto_url": mailto_url},
            )
            mailto_payload = _loads_mapping(parse_mailto_text)
            if not mailto_payload.get("ok"):
                execution_status = "failed"
                sender_unsubscribe_status = "failed"
                execution_evidence = str(mailto_payload.get("error") or "Could not parse mailto URL.")
                execution_payload = {"parse_mailto": mailto_payload}
                execution_tool = "parse_mailto_url"
                execution_kwargs = parse_mailto_kwargs
            else:
                body = str(mailto_payload.get("body") or "").strip()
                if not body:
                    body = "unsubscribe"
                execution_tool, execution_kwargs, send_text = _call_tool(
                    "send",
                    used_tools["send"],
                    {
                        "to": str(mailto_payload.get("to") or "").strip(),
                        "subject": str(mailto_payload.get("subject") or "unsubscribe").strip() or "unsubscribe",
                        "body": body,
                    },
                )
                execution_status = "request_sent"
                sender_unsubscribe_status = "request_sent"
                execution_evidence = str(send_text or "Unsubscribe request email sent.").strip()
                execution_payload = {
                    "parse_mailto": mailto_payload,
                    "send_result": send_text,
                }

    elif effective_method == "website":
        execution_status = "manual_required"
        sender_unsubscribe_status = "manual_required"
        execution_evidence = (
            "This message only exposes a website unsubscribe URL. "
            "Website unsubscribe automation is not implemented in this version."
        )
        execution_payload = {
            "website_url": classification.get("website_url"),
        }

    else:
        execution_status = "failed"
        sender_unsubscribe_status = "failed"
        execution_evidence = f"Unsupported or unknown unsubscribe method: {effective_method}."

    response_payload = {
        "email_id": email_id,
        "from": headers.get("From") or "",
        "subject": headers.get("Subject") or "",
        "requested_method": requested_method,
        "classified_method": classified_method,
        "effective_method": effective_method,
        "status": execution_status,
        "sender_unsubscribe_status": sender_unsubscribe_status,
        "gmail_subscription_ui_status": gmail_subscription_ui_status,
        "evidence": execution_evidence,
        "classification": classification,
        "execution": execution_payload,
        "tool_calls": {
            "get_email_headers": header_kwargs,
            "parse_list_unsubscribe_header": parse_kwargs,
            "classify_unsubscribe_method": classify_kwargs,
            "execution_tool": execution_tool,
            "execution_arguments": execution_kwargs,
        },
    }

    print(
        f"[skill:unsubscribe_execute] completed status={execution_status} method={effective_method}",
        flush=True,
    )

    return {
        "completed": True,
        "response": "\n".join(
            [
                "[UNSUBSCRIBE_EXECUTE_BUNDLE]",
                f"skill_name: {skill_spec.get('name', 'unsubscribe_execute')}",
                f"email_id: {email_id}",
                f"status: {execution_status}",
                f"sender_unsubscribe_status: {sender_unsubscribe_status}",
                f"gmail_subscription_ui_status: {gmail_subscription_ui_status}",
                f"effective_method: {effective_method}",
                "notes:",
                "- Website unsubscribe automation is not implemented.",
                "- mailto execution means request_sent, not confirmed.",
                "- one_click execution reports the HTTP result returned by the sender unsubscribe endpoint.",
                "- Gmail Subscriptions UI is not updated by this agent; it may still show the sender even after a one-click request is accepted.",
                "",
                "[RESULT_JSON]",
                json.dumps(response_payload, ensure_ascii=False, indent=2, sort_keys=True),
            ]
        ).strip(),
        "reason": f"Unsubscribe execution completed with status={execution_status}.",
    }
