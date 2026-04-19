from __future__ import annotations

import base64
import html
import json
import re
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import Request, urlopen


HEADER_NAMES = [
    "List-Unsubscribe",
    "List-Unsubscribe-Post",
]
DEFAULT_MAX_MANUAL_LINKS = 5

_BRACKETED_VALUE_PATTERN = re.compile(r"<([^>]+)>")
_URL_PATTERN = re.compile(r"https?://[^\s<>\")']+", flags=re.IGNORECASE)
_MAILTO_PATTERN = re.compile(r"mailto:[^\s<>\")']+", flags=re.IGNORECASE)
_ANCHOR_PATTERN = re.compile(
    r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
    flags=re.IGNORECASE | re.DOTALL,
)
_TAG_PATTERN = re.compile(r"<[^>]+>")
_UNSUBSCRIBE_TEXT_PATTERN = re.compile(
    r"unsubscribe|un-subscribe|opt\s*out|email\s*preferences|manage\s*preferences|subscription\s*preferences",
    flags=re.IGNORECASE,
)


def _json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _loads_mapping(raw_text: Any) -> dict[str, Any]:
    if isinstance(raw_text, dict):
        return raw_text
    try:
        payload = json.loads(str(raw_text or "").strip())
    except json.JSONDecodeError:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _normalize_email_ids(email_ids: Any) -> list[str]:
    if email_ids is None:
        return []

    raw_items: list[Any]
    if isinstance(email_ids, str):
        text = email_ids.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, list):
                raw_items = payload
            else:
                raw_items = [part.strip() for part in text.replace("\n", ",").split(",")]
        else:
            raw_items = [part.strip() for part in text.replace("\n", ",").split(",")]
    elif isinstance(email_ids, (list, tuple, set)):
        raw_items = list(email_ids)
    else:
        raw_items = [email_ids]

    normalized: list[str] = []
    seen: set[str] = set()
    for raw_item in raw_items:
        email_id = str(raw_item or "").strip()
        if not email_id or email_id in seen:
            continue
        seen.add(email_id)
        normalized.append(email_id)
    return normalized


def _normalize_header_names(header_names: Any) -> list[str]:
    if header_names is None:
        return list(HEADER_NAMES)
    if isinstance(header_names, str):
        names = [item.strip() for item in header_names.split(",")]
    elif isinstance(header_names, (list, tuple, set)):
        names = [str(item or "").strip() for item in header_names]
    else:
        names = []

    normalized: list[str] = []
    seen: set[str] = set()
    for name in names:
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(name)
    return normalized or list(HEADER_NAMES)


def _header_lookup(message: dict[str, Any]) -> dict[str, str]:
    payload = message.get("payload", {}) or {}
    headers = payload.get("headers", []) if isinstance(payload, dict) else []
    lookup: dict[str, str] = {}
    for header in headers:
        if not isinstance(header, dict):
            continue
        name = str(header.get("name") or "").strip()
        value = str(header.get("value") or "").strip()
        if not name:
            continue
        lookup[name.lower()] = value
    return lookup


def _get_email_headers(
    *,
    email_tool: Any,
    email_id: str,
    header_names: Any = None,
) -> dict[str, Any]:
    normalized_email_id = str(email_id or "").strip()
    if not normalized_email_id:
        return {
            "ok": False,
            "email_id": "",
            "headers": {},
            "error": "get_unsubscribe_info requires a non-empty email_id.",
        }

    selected_header_names = _normalize_header_names(header_names)
    try:
        service = email_tool._get_service()
        message = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=normalized_email_id,
                format="metadata",
                metadataHeaders=selected_header_names,
            )
            .execute()
        )
    except TypeError:
        try:
            service = email_tool._get_service()
            message = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=normalized_email_id,
                    format="metadata",
                )
                .execute()
            )
        except Exception as exc:
            return {
                "ok": False,
                "email_id": normalized_email_id,
                "headers": {},
                "error": str(exc),
            }
    except Exception as exc:
        return {
            "ok": False,
            "email_id": normalized_email_id,
            "headers": {},
            "error": str(exc),
        }

    if not isinstance(message, dict):
        message = {}
    lookup = _header_lookup(message)
    headers = {
        header_name: lookup.get(header_name.lower(), "")
        for header_name in selected_header_names
    }
    return {
        "ok": True,
        "email_id": normalized_email_id,
        "thread_id": str(message.get("threadId") or "").strip(),
        "headers": headers,
        "error": "",
    }


def _parse_list_unsubscribe_header(header_value: str) -> dict[str, Any]:
    raw = str(header_value or "").strip()
    bracketed_values = [value.strip() for value in _BRACKETED_VALUE_PATTERN.findall(raw) if value.strip()]
    scan_values = bracketed_values or [part.strip() for part in raw.split(",") if part.strip()]

    https_urls: list[str] = []
    mailto_urls: list[str] = []
    other_values: list[str] = []

    def _append_unique(target: list[str], value: str) -> None:
        if value and value not in target:
            target.append(value)

    for value in scan_values:
        lowered = value.lower()
        if lowered.startswith(("http://", "https://")):
            _append_unique(https_urls, value)
        elif lowered.startswith("mailto:"):
            _append_unique(mailto_urls, value)
        elif value:
            other_values.append(value)

    for url in _URL_PATTERN.findall(raw):
        _append_unique(https_urls, url.rstrip(">,."))
    for mailto in _MAILTO_PATTERN.findall(raw):
        _append_unique(mailto_urls, mailto.rstrip(">,."))

    return {
        "raw": raw,
        "https_urls": https_urls,
        "mailto_urls": mailto_urls,
        "other_values": other_values,
    }


def _supports_one_click(list_unsubscribe_post: str) -> bool:
    normalized = str(list_unsubscribe_post or "").strip().lower().replace(" ", "")
    return "list-unsubscribe=one-click" in normalized


def _parse_mailto_url(mailto_url: str) -> dict[str, Any]:
    raw = str(mailto_url or "").strip()
    if not raw.lower().startswith("mailto:"):
        return {
            "ok": False,
            "raw": raw,
            "to": "",
            "subject": "",
            "body": "",
            "error": "parse_mailto_url requires a mailto: URL.",
        }

    parsed = urlparse(raw)
    to_address = unquote(parsed.path or "").strip()
    query = parse_qs(parsed.query or "", keep_blank_values=True)
    subject = unquote((query.get("subject") or ["unsubscribe"])[0]).strip() or "unsubscribe"
    body = unquote((query.get("body") or [""])[0]).strip()

    return {
        "ok": bool(to_address),
        "raw": raw,
        "to": to_address,
        "subject": subject,
        "body": body,
        "error": "" if to_address else "mailto URL did not contain a recipient.",
    }


def _decode_base64url(raw_data: Any) -> str:
    data = str(raw_data or "").strip()
    if not data:
        return ""
    padding = "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(data + padding).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _strip_tags(value: str) -> str:
    text = _TAG_PATTERN.sub(" ", str(value or ""))
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _append_link(links: list[dict[str, str]], *, url: str, label: str, source: str) -> None:
    normalized_url = html.unescape(str(url or "").strip())
    if not normalized_url.lower().startswith(("http://", "https://")):
        return
    normalized_label = _strip_tags(label) or "(link)"
    if not _UNSUBSCRIBE_TEXT_PATTERN.search(normalized_label) and not _UNSUBSCRIBE_TEXT_PATTERN.search(normalized_url):
        return
    if any(item.get("url") == normalized_url for item in links):
        return
    links.append(
        {
            "url": normalized_url,
            "label": normalized_label,
            "source": source,
        }
    )


def _extract_unsubscribe_links_from_content(*, content: str, source: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    text = str(content or "")
    if not text:
        return links

    for href, anchor_html in _ANCHOR_PATTERN.findall(text):
        _append_link(links, url=href, label=anchor_html, source=source)

    for match in _URL_PATTERN.finditer(text):
        url = match.group(0)
        window_start = max(match.start() - 80, 0)
        window_end = min(match.end() + 80, len(text))
        surrounding_text = text[window_start:window_end]
        _append_link(links, url=url.rstrip(">,."), label=surrounding_text, source=source)

    return links


def _collect_message_text_parts(part: dict[str, Any], *, collected: list[dict[str, str]]) -> None:
    mime_type = str(part.get("mimeType") or "").lower()
    body = part.get("body", {}) or {}
    data = body.get("data") if isinstance(body, dict) else ""

    if data and mime_type in {"text/html", "text/plain"}:
        collected.append(
            {
                "mime_type": mime_type,
                "content": _decode_base64url(data),
            }
        )

    for child in part.get("parts", []) or []:
        if isinstance(child, dict):
            _collect_message_text_parts(child, collected=collected)


def _extract_unsubscribe_links_from_email(
    *,
    email_tool: Any,
    email_id: str,
    max_links: int = DEFAULT_MAX_MANUAL_LINKS,
) -> dict[str, Any]:
    normalized_email_id = str(email_id or "").strip()
    if not normalized_email_id:
        return {
            "ok": False,
            "email_id": "",
            "links": [],
            "error": "get_unsubscribe_info requires a non-empty email_id.",
        }

    try:
        safe_max_links = min(max(int(max_links or DEFAULT_MAX_MANUAL_LINKS), 1), 20)
    except (TypeError, ValueError):
        safe_max_links = DEFAULT_MAX_MANUAL_LINKS

    try:
        service = email_tool._get_service()
        message = (
            service.users()
            .messages()
            .get(userId="me", id=normalized_email_id, format="full")
            .execute()
        )
    except Exception as exc:
        return {
            "ok": False,
            "email_id": normalized_email_id,
            "links": [],
            "error": str(exc),
        }

    payload = message.get("payload", {}) if isinstance(message, dict) else {}
    text_parts: list[dict[str, str]] = []
    if isinstance(payload, dict):
        _collect_message_text_parts(payload, collected=text_parts)

    links: list[dict[str, str]] = []
    for part in text_parts:
        part_links = _extract_unsubscribe_links_from_content(
            content=part.get("content", ""),
            source=part.get("mime_type", "message_body"),
        )
        for link in part_links:
            if len(links) >= safe_max_links:
                break
            if not any(item.get("url") == link.get("url") for item in links):
                links.append(link)

    return {
        "ok": True,
        "email_id": normalized_email_id,
        "links": links,
        "link_count": len(links),
        "error": "",
    }


def _build_manual_link(*, url: str, label: str, source: str) -> dict[str, str] | None:
    normalized_url = str(url or "").strip()
    if not normalized_url.lower().startswith(("http://", "https://")):
        return None
    return {
        "url": normalized_url,
        "label": str(label or "Open unsubscribe page").strip() or "Open unsubscribe page",
        "source": str(source or "unknown").strip() or "unknown",
    }


def _dedupe_manual_links(links: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for link in links:
        if not isinstance(link, dict):
            continue
        url = str(link.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(
            {
                "url": url,
                "label": str(link.get("label") or "Open unsubscribe page").strip() or "Open unsubscribe page",
                "source": str(link.get("source") or "unknown").strip() or "unknown",
            }
        )
    return deduped


def _build_mailto_option(mailto_url: str) -> tuple[dict[str, Any] | None, str]:
    normalized_mailto_url = str(mailto_url or "").strip()
    if not normalized_mailto_url:
        return None, ""

    parsed_payload = _parse_mailto_url(normalized_mailto_url)
    option: dict[str, Any] = {"url": normalized_mailto_url}

    if parsed_payload.get("ok"):
        option["send_payload"] = {
            "to": str(parsed_payload.get("to") or "").strip(),
            "subject": str(parsed_payload.get("subject") or "").strip(),
            "body": str(parsed_payload.get("body") or ""),
        }
        return option, ""

    error = str(parsed_payload.get("error") or "").strip()
    return option, error


def _build_unsubscribe_payload(
    *,
    list_unsubscribe: str,
    list_unsubscribe_post: str,
    manual_link_payload: dict[str, Any] | None,
) -> tuple[dict[str, Any], str]:
    parsed_payload = _parse_list_unsubscribe_header(list_unsubscribe)

    https_urls = [
        str(url or "").strip()
        for url in parsed_payload.get("https_urls", [])
        if str(url or "").strip()
    ]
    mailto_urls = [
        str(url or "").strip()
        for url in parsed_payload.get("mailto_urls", [])
        if str(url or "").strip()
    ]

    supports_one_click = _supports_one_click(list_unsubscribe_post)
    one_click_url = https_urls[0] if supports_one_click and https_urls else ""
    website_url = ""
    if https_urls and not one_click_url:
        website_url = https_urls[0]

    options: dict[str, Any] = {}
    errors: list[str] = []

    if one_click_url:
        options["one_click"] = {
            "url": one_click_url,
            "request_payload": {"url": one_click_url},
        }

    if mailto_urls:
        mailto_option, mailto_error = _build_mailto_option(mailto_urls[0])
        if mailto_option is not None:
            options["mailto"] = mailto_option
        if mailto_error:
            errors.append(mailto_error)

    manual_links: list[dict[str, str]] = []
    if website_url:
        header_link = _build_manual_link(
            url=website_url,
            label="Open unsubscribe page",
            source="list_unsubscribe_header",
        )
        if header_link is not None:
            manual_links.append(header_link)

    if isinstance(manual_link_payload, dict):
        raw_links = manual_link_payload.get("links")
        if isinstance(raw_links, list):
            for raw_link in raw_links:
                if not isinstance(raw_link, dict):
                    continue
                manual_link = _build_manual_link(
                    url=str(raw_link.get("url") or "").strip(),
                    label=str(raw_link.get("label") or "Open unsubscribe page").strip() or "Open unsubscribe page",
                    source=str(raw_link.get("source") or "email_body").strip() or "email_body",
                )
                if manual_link is not None:
                    manual_links.append(manual_link)

    deduped_manual_links = _dedupe_manual_links(manual_links)
    if website_url or deduped_manual_links:
        website_option: dict[str, Any] = {}
        if website_url:
            website_option["url"] = website_url
        if deduped_manual_links:
            website_option["manual_links"] = deduped_manual_links
        options["website"] = website_option

    if one_click_url:
        method = "one_click"
    elif mailto_urls:
        method = "mailto"
    elif "website" in options:
        method = "website"
    else:
        method = "unknown"

    unsubscribe = {
        "method": method,
        "options": options,
    }
    return unsubscribe, "; ".join(error for error in errors if error)


def get_unsubscribe_info_from_email_tool(
    *,
    email_tool: Any,
    email_ids: Any,
    max_manual_links: int = DEFAULT_MAX_MANUAL_LINKS,
) -> str:
    normalized_email_ids = _normalize_email_ids(email_ids)
    if not normalized_email_ids:
        return _json_dumps(
            {
                "items": [],
                "summary": {
                    "requested_count": 0,
                    "analyzed_count": 0,
                    "error_count": 1,
                },
                "error": "get_unsubscribe_info requires at least one email_id.",
            }
        )

    items: list[dict[str, Any]] = []
    error_count = 0

    for email_id in normalized_email_ids:
        item: dict[str, Any] = {"email_id": email_id, "error": ""}
        header_payload = _get_email_headers(
            email_tool=email_tool,
            email_id=email_id,
            header_names=HEADER_NAMES,
        )

        if not header_payload.get("ok"):
            item["error"] = str(header_payload.get("error") or "Could not fetch unsubscribe metadata.").strip()
            items.append(item)
            error_count += 1
            continue

        headers = header_payload.get("headers") if isinstance(header_payload.get("headers"), dict) else {}
        list_unsubscribe = str(headers.get("List-Unsubscribe") or "").strip()
        list_unsubscribe_post = str(headers.get("List-Unsubscribe-Post") or "").strip()
        parsed_preview = _parse_list_unsubscribe_header(list_unsubscribe)

        should_extract_manual_links = (
            not _supports_one_click(list_unsubscribe_post)
            and not parsed_preview.get("mailto_urls")
        )
        manual_link_payload: dict[str, Any] | None = None
        if should_extract_manual_links:
            manual_link_payload = _extract_unsubscribe_links_from_email(
                email_tool=email_tool,
                email_id=email_id,
                max_links=max_manual_links,
            )

        unsubscribe_payload, item_error = _build_unsubscribe_payload(
            list_unsubscribe=list_unsubscribe,
            list_unsubscribe_post=list_unsubscribe_post,
            manual_link_payload=manual_link_payload,
        )

        item["unsubscribe"] = unsubscribe_payload
        if item_error:
            item["error"] = item_error
            error_count += 1
        items.append(item)

    analyzed_count = max(len(items) - error_count, 0)
    return _json_dumps(
        {
            "items": items,
            "summary": {
                "requested_count": len(normalized_email_ids),
                "analyzed_count": analyzed_count,
                "error_count": error_count,
            },
            "error": "",
        }
    )


def post_one_click_unsubscribe(url: str, timeout_seconds: int = 10) -> str:
    """Execute an RFC 8058-style one-click unsubscribe POST."""
    raw_url = str(url or "").strip()
    parsed = urlparse(raw_url)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        return _json_dumps(
            {
                "status": "failed",
                "http_status": None,
                "url": raw_url,
                "evidence": "One-click unsubscribe requires a valid HTTPS URL.",
                "error": "invalid_url",
            }
        )

    try:
        safe_timeout = min(max(int(timeout_seconds or 10), 1), 30)
    except (TypeError, ValueError):
        safe_timeout = 10

    data = urlencode({"List-Unsubscribe": "One-Click"}).encode("utf-8")
    request = Request(
        raw_url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "email-agent unsubscribe client",
        },
    )

    try:
        with urlopen(request, timeout=safe_timeout) as response:
            status_code = int(getattr(response, "status", 0) or response.getcode() or 0)
            response_text = response.read(500).decode("utf-8", errors="replace").strip()
    except Exception as exc:
        return _json_dumps(
            {
                "status": "failed",
                "http_status": None,
                "url": raw_url,
                "evidence": f"POST failed: {exc}",
                "error": str(exc),
            }
        )

    if status_code in {200, 204}:
        status = "confirmed"
    elif status_code == 202:
        status = "request_accepted"
    elif 200 <= status_code < 300:
        status = "request_submitted"
    else:
        status = "uncertain"

    evidence = f"HTTP {status_code} response received."
    if response_text:
        evidence = f"{evidence} Response preview: {response_text[:160]}"
    return _json_dumps(
        {
            "status": status,
            "http_status": status_code,
            "url": raw_url,
            "evidence": evidence,
            "sender_unsubscribe_status": status,
            "gmail_subscription_ui_status": "not_updated_by_agent",
            "error": "",
        }
    )


def build_get_unsubscribe_info_tool(
    email_tool_getter: Callable[[], Any],
) -> Callable[[list[str]], str]:
    """Build a Gmail-aware tool that returns unsubscribe classification plus execution-ready details."""

    def get_unsubscribe_info(email_ids: list[str], max_manual_links: int = DEFAULT_MAX_MANUAL_LINKS) -> str:
        """Inspect one or more Gmail messages and return unsubscribe method plus execution-ready details.

        Args:
            email_ids: Gmail message ids to inspect.
            max_manual_links: Maximum number of manual unsubscribe links to keep per email.

        Returns:
            JSON containing per-message unsubscribe method and any execution-ready details.
        """
        email_tool = email_tool_getter()
        normalized_email_ids = _normalize_email_ids(email_ids)
        if email_tool is None:
            return _json_dumps(
                {
                    "items": [
                        {
                            "email_id": email_id,
                            "error": "Unsubscribe inspection is only available when Gmail is connected.",
                        }
                        for email_id in normalized_email_ids
                    ],
                    "summary": {
                        "requested_count": len(normalized_email_ids),
                        "analyzed_count": 0,
                        "error_count": len(normalized_email_ids) or 1,
                    },
                    "error": "Unsubscribe inspection is only available when Gmail is connected.",
                }
            )
        return get_unsubscribe_info_from_email_tool(
            email_tool=email_tool,
            email_ids=normalized_email_ids,
            max_manual_links=max_manual_links,
        )

    get_unsubscribe_info.__name__ = "get_unsubscribe_info"
    return get_unsubscribe_info
