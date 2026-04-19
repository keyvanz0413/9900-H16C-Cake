from __future__ import annotations

import json
from typing import Any, Callable


ALLOWED_METHODS = {"auto", "one_click", "mailto", "website"}
MANUAL_LINK_FALLBACK_STATUSES = {"failed", "uncertain", "manual_required"}


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


def _normalize_requested_method(raw_method: Any) -> str:
    method = str(raw_method or "auto").strip().lower()
    if method in {"one-click", "one click", "oneclick"}:
        method = "one_click"
    if method not in ALLOWED_METHODS:
        return "auto"
    return method


def _normalize_classified_method(raw_method: Any) -> str:
    method = str(raw_method or "unknown").strip().lower()
    if method in {"one-click", "one click", "oneclick"}:
        return "one_click"
    if method in {"one_click", "mailto", "website"}:
        return method
    return "unknown"


def _available_methods(options: dict[str, Any]) -> list[str]:
    return [method for method in ("one_click", "mailto", "website") if isinstance(options.get(method), dict)]


def _resolve_effective_method(requested_method: str, classified_method: str, options: dict[str, Any]) -> str:
    available_methods = _available_methods(options)
    if requested_method != "auto":
        return requested_method
    if classified_method in available_methods:
        return classified_method
    if available_methods:
        return available_methods[0]
    return classified_method or "unknown"


def _confirmation_result(*, email_id: str, classified_method: str, available_methods: list[str]) -> dict[str, Any]:
    return {
        "completed": True,
        "response": "\n".join(
            [
                "[UNSUBSCRIBE_EXECUTE_BUNDLE]",
                f"email_id: {email_id}",
                "status: needs_confirmation",
                f"classified_method: {classified_method}",
                f"available_methods: {', '.join(available_methods) if available_methods else '(none)'}",
                "notes:",
                "- No unsubscribe action was executed because confirmed=false.",
                "- Reply with explicit confirmation before execution.",
            ]
        ).strip(),
        "reason": "Execution requires explicit user confirmation; no unsubscribe action was performed.",
    }


def _first_manual_link(link_payload: dict[str, Any]) -> dict[str, Any]:
    links = link_payload.get("manual_links")
    if not isinstance(links, list):
        return {}
    for link in links:
        if not isinstance(link, dict):
            continue
        url = str(link.get("url") or "").strip()
        if url.lower().startswith(("http://", "https://")):
            return {
                "url": url,
                "label": str(link.get("label") or link.get("anchor_text") or "Open unsubscribe page").strip() or "Open unsubscribe page",
                "source": str(link.get("source") or "email_body").strip() or "email_body",
                "kind": str(link.get("kind") or "unsubscribe_link").strip() or "unsubscribe_link",
            }
    return {}


def _extract_unsubscribe_item(info_payload: dict[str, Any], email_id: str) -> dict[str, Any]:
    items = info_payload.get("items")
    if not isinstance(items, list):
        return {}
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("email_id") or "").strip() == email_id:
            return item
    return {}


def execute_skill(*, arguments, used_tools, skill_spec):
    email_id = str(arguments.get("email_id") or "").strip()
    requested_method = _normalize_requested_method(arguments.get("method", "auto"))
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

    _, unsubscribe_kwargs, unsubscribe_text = _call_tool(
        "get_unsubscribe_info",
        used_tools["get_unsubscribe_info"],
        {"email_ids": [email_id]},
    )
    unsubscribe_info = _loads_mapping(unsubscribe_text)
    unsubscribe_item = _extract_unsubscribe_item(unsubscribe_info, email_id)
    item_error = str(unsubscribe_item.get("error") or "").strip()
    unsubscribe = unsubscribe_item.get("unsubscribe") if isinstance(unsubscribe_item.get("unsubscribe"), dict) else {}
    options = unsubscribe.get("options") if isinstance(unsubscribe.get("options"), dict) else {}
    classified_method = _normalize_classified_method(unsubscribe.get("method", "unknown"))
    available_methods = _available_methods(options)

    if item_error or not unsubscribe:
        return {
            "completed": True,
            "response": "\n".join(
                [
                    "[UNSUBSCRIBE_EXECUTE_BUNDLE]",
                    f"email_id: {email_id}",
                    "status: failed",
                    f"reason: Could not fetch unsubscribe metadata: {item_error or 'unknown error'}",
                    "No unsubscribe action was executed.",
                ]
            ),
            "reason": "Could not fetch unsubscribe metadata.",
        }

    effective_method = _resolve_effective_method(requested_method, classified_method, options)

    if requested_method != "auto" and requested_method not in available_methods:
        return {
            "completed": True,
            "response": "\n".join(
                [
                    "[UNSUBSCRIBE_EXECUTE_BUNDLE]",
                    f"email_id: {email_id}",
                    "status: failed",
                    f"requested_method: {requested_method}",
                    f"classified_method: {classified_method}",
                    f"available_methods: {', '.join(available_methods) if available_methods else '(none)'}",
                    "reason: Requested method is not available for this message.",
                    "No unsubscribe action was executed.",
                ]
            ),
            "reason": "Requested method did not match the current unsubscribe options.",
        }

    if not confirmed:
        return _confirmation_result(
            email_id=email_id,
            classified_method=classified_method,
            available_methods=available_methods,
        )

    execution_status = "failed"
    sender_unsubscribe_status = "failed"
    gmail_subscription_ui_status = "not_updated_by_agent"
    execution_evidence = ""
    execution_payload: dict[str, Any] = {}
    execution_tool = "(none)"
    execution_kwargs: dict[str, Any] = {}
    manual_unsubscribe: dict[str, Any] = {}

    if effective_method == "one_click":
        one_click_option = options.get("one_click") if isinstance(options.get("one_click"), dict) else {}
        request_payload = one_click_option.get("request_payload") if isinstance(one_click_option.get("request_payload"), dict) else {}
        one_click_url = str(request_payload.get("url") or one_click_option.get("url") or "").strip()
        if not one_click_url:
            execution_status = "failed"
            execution_evidence = "No one-click URL was available after re-reading unsubscribe metadata."
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
        mailto_option = options.get("mailto") if isinstance(options.get("mailto"), dict) else {}
        send_payload = mailto_option.get("send_payload") if isinstance(mailto_option.get("send_payload"), dict) else {}
        if not send_payload:
            execution_status = "failed"
            execution_evidence = "No mailto send payload was available after re-reading unsubscribe metadata."
        else:
            body = str(send_payload.get("body") or "").strip() or "unsubscribe"
            execution_tool, execution_kwargs, send_text = _call_tool(
                "send",
                used_tools["send"],
                {
                    "to": str(send_payload.get("to") or "").strip(),
                    "subject": str(send_payload.get("subject") or "unsubscribe").strip() or "unsubscribe",
                    "body": body,
                },
            )
            execution_status = "request_sent"
            sender_unsubscribe_status = "request_sent"
            execution_evidence = str(send_text or "Unsubscribe request email sent.").strip()
            execution_payload = {
                "send_payload": {
                    "to": str(send_payload.get("to") or "").strip(),
                    "subject": str(send_payload.get("subject") or "unsubscribe").strip() or "unsubscribe",
                    "body": body,
                },
                "send_result": send_text,
            }

    elif effective_method == "website":
        website_option = options.get("website") if isinstance(options.get("website"), dict) else {}
        manual_unsubscribe = _first_manual_link(website_option)
        if not manual_unsubscribe:
            website_url = str(website_option.get("url") or "").strip()
            if website_url:
                manual_unsubscribe = {
                    "url": website_url,
                    "label": "Open unsubscribe page",
                    "source": "list_unsubscribe_header",
                    "kind": "unsubscribe_link",
                }
        execution_status = "manual_link_available" if manual_unsubscribe else "manual_required"
        sender_unsubscribe_status = "manual_required"
        execution_evidence = (
            "This message only exposes a website unsubscribe flow. "
            "Website unsubscribe automation is not implemented in this version."
        )
        execution_payload = {"website": website_option}

    else:
        execution_status = "failed"
        sender_unsubscribe_status = "failed"
        execution_evidence = f"Unsupported or unknown unsubscribe method: {effective_method}."

    should_use_manual_link_fallback = (
        confirmed
        and not manual_unsubscribe
        and execution_status in MANUAL_LINK_FALLBACK_STATUSES
    )
    if should_use_manual_link_fallback:
        website_option = options.get("website") if isinstance(options.get("website"), dict) else {}
        manual_unsubscribe = _first_manual_link(website_option)
        if manual_unsubscribe:
            execution_status = "manual_link_available"
            if sender_unsubscribe_status in {"failed", "manual_required", "uncertain"}:
                sender_unsubscribe_status = "manual_required"
            execution_evidence = (
                f"{execution_evidence} Manual unsubscribe link is available for the user to open."
                if execution_evidence
                else "Manual unsubscribe link is available for the user to open."
            )

    response_payload = {
        "email_id": email_id,
        "requested_method": requested_method,
        "classified_method": classified_method,
        "available_methods": available_methods,
        "effective_method": effective_method,
        "status": execution_status,
        "sender_unsubscribe_status": sender_unsubscribe_status,
        "gmail_subscription_ui_status": gmail_subscription_ui_status,
        "evidence": execution_evidence,
        "manual_unsubscribe": manual_unsubscribe,
        "unsubscribe_info": unsubscribe,
        "execution": execution_payload,
        "tool_calls": {
            "get_unsubscribe_info": unsubscribe_kwargs,
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
                "- If status is manual_link_available, the user must open the extracted link manually; the agent did not visit the page.",
                "",
                "[RESULT_JSON]",
                json.dumps(response_payload, ensure_ascii=False, indent=2, sort_keys=True),
            ]
        ).strip(),
        "reason": f"Unsubscribe execution completed with status={execution_status}.",
    }
