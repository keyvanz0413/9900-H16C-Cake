from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import Request, urlopen


_DEFAULT_HEADER_NAMES = (
    "From",
    "Subject",
    "Date",
    "List-Unsubscribe",
    "List-Unsubscribe-Post",
    "List-Id",
    "Precedence",
)
_BRACKETED_VALUE_PATTERN = re.compile(r"<([^>]+)>")
_URL_PATTERN = re.compile(r"https?://[^\s<>\")']+", flags=re.IGNORECASE)
_MAILTO_PATTERN = re.compile(r"mailto:[^\s<>\")']+", flags=re.IGNORECASE)
_ONE_CLICK_BODY = "List-Unsubscribe=One-Click"


def _json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _normalize_header_names(header_names: Any) -> list[str]:
    if header_names is None:
        return list(_DEFAULT_HEADER_NAMES)
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
    return normalized or list(_DEFAULT_HEADER_NAMES)


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


def get_email_headers_from_email_tool(
    *,
    email_tool: Any,
    email_id: str,
    header_names: Any = None,
) -> str:
    """Fetch selected Gmail message headers without fetching the full body."""
    normalized_email_id = str(email_id or "").strip()
    if not normalized_email_id:
        return _json_dumps(
            {
                "ok": False,
                "email_id": "",
                "headers": {},
                "error": "get_email_headers requires a non-empty email_id.",
            }
        )

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
            return _json_dumps(
                {
                    "ok": False,
                    "email_id": normalized_email_id,
                    "headers": {},
                    "error": str(exc),
                }
            )
    except Exception as exc:
        return _json_dumps(
            {
                "ok": False,
                "email_id": normalized_email_id,
                "headers": {},
                "error": str(exc),
            }
        )

    if not isinstance(message, dict):
        message = {}
    lookup = _header_lookup(message)
    headers = {
        header_name: lookup.get(header_name.lower(), "")
        for header_name in selected_header_names
    }
    return _json_dumps(
        {
            "ok": True,
            "email_id": normalized_email_id,
            "thread_id": str(message.get("threadId") or "").strip(),
            "headers": headers,
        }
    )


def parse_list_unsubscribe_header(header_value: str) -> str:
    """Parse a List-Unsubscribe header into HTTP(S), mailto, and other values."""
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

    return _json_dumps(
        {
            "raw": raw,
            "https_urls": https_urls,
            "mailto_urls": mailto_urls,
            "other_values": other_values,
        }
    )


def _coerce_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(payload, dict):
            return payload
    return {}


def _host_for_url(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def classify_unsubscribe_method(
    parsed_list_unsubscribe: str,
    list_unsubscribe_post: str = "",
) -> str:
    """Classify parsed unsubscribe metadata without executing any unsubscribe action."""
    parsed = _coerce_mapping(parsed_list_unsubscribe)
    https_urls = [
        str(url or "").strip()
        for url in parsed.get("https_urls", [])
        if str(url or "").strip().lower().startswith(("http://", "https://"))
    ]
    mailto_urls = [
        str(url or "").strip()
        for url in parsed.get("mailto_urls", [])
        if str(url or "").strip().lower().startswith("mailto:")
    ]
    post_header = str(list_unsubscribe_post or "").strip()
    post_header_normalized = post_header.lower().replace(" ", "")

    supports_one_click = "list-unsubscribe=one-click" in post_header_normalized
    reasons: list[str] = []
    method = "unknown"
    confidence = "low"
    one_click_url = None
    mailto_url = None
    website_url = None

    if supports_one_click and https_urls:
        method = "one_click"
        confidence = "high"
        one_click_url = https_urls[0]
        reasons.append("List-Unsubscribe-Post declares List-Unsubscribe=One-Click.")
        reasons.append("List-Unsubscribe contains an HTTP(S) URL.")
    elif mailto_urls:
        method = "mailto"
        confidence = "medium"
        mailto_url = mailto_urls[0]
        reasons.append("List-Unsubscribe contains a mailto URL.")
        if https_urls:
            website_url = https_urls[0]
            reasons.append("List-Unsubscribe also contains an HTTP(S) URL; mailto is preferred for this read-only classification.")
    elif https_urls:
        method = "website"
        confidence = "medium"
        website_url = https_urls[0]
        reasons.append("List-Unsubscribe contains an HTTP(S) URL but no one-click POST header.")
    else:
        reasons.append("No usable List-Unsubscribe URL or mailto value was found.")

    return _json_dumps(
        {
            "method": method,
            "confidence": confidence,
            "one_click_url": one_click_url,
            "mailto_url": mailto_url,
            "website_url": website_url,
            "reasons": reasons,
            "url_host": _host_for_url(one_click_url or website_url or ""),
        }
    )


def parse_mailto_url(mailto_url: str) -> str:
    """Parse a mailto URL into fields suitable for the existing Gmail send tool."""
    raw = str(mailto_url or "").strip()
    if not raw.lower().startswith("mailto:"):
        return _json_dumps(
            {
                "ok": False,
                "raw": raw,
                "to": "",
                "subject": "",
                "body": "",
                "error": "parse_mailto_url requires a mailto: URL.",
            }
        )

    parsed = urlparse(raw)
    to_address = unquote(parsed.path or "").strip()
    query = parse_qs(parsed.query or "", keep_blank_values=True)
    subject = unquote((query.get("subject") or ["unsubscribe"])[0]).strip() or "unsubscribe"
    body = unquote((query.get("body") or [""])[0]).strip()

    return _json_dumps(
        {
            "ok": bool(to_address),
            "raw": raw,
            "to": to_address,
            "subject": subject,
            "body": body,
            "error": "" if to_address else "mailto URL did not contain a recipient.",
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

    status = "confirmed" if 200 <= status_code < 300 else "uncertain"
    evidence = f"HTTP {status_code} response received."
    if response_text:
        evidence = f"{evidence} Response preview: {response_text[:160]}"
    return _json_dumps(
        {
            "status": status,
            "http_status": status_code,
            "url": raw_url,
            "evidence": evidence,
            "error": "",
        }
    )
