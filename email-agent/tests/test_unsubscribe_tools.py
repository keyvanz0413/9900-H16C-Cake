from __future__ import annotations

import json

from tools.unsubscribe_tools import (
    classify_unsubscribe_method,
    get_email_headers_from_email_tool,
    parse_mailto_url,
    parse_list_unsubscribe_header,
    post_one_click_unsubscribe,
)
import tools.unsubscribe_tools as unsubscribe_tools


class _Execute:
    def __init__(self, payload):
        self._payload = payload

    def execute(self):
        return self._payload


class _MessagesAPI:
    def __init__(self, message_payloads, calls):
        self._message_payloads = message_payloads
        self._calls = calls

    def get(self, **kwargs):
        self._calls.append(("message_get", kwargs))
        return _Execute(self._message_payloads[kwargs["id"]])


class _UsersAPI:
    def __init__(self, message_payloads, calls):
        self._messages = _MessagesAPI(message_payloads, calls)

    def messages(self):
        return self._messages


class _FakeService:
    def __init__(self, message_payloads, calls):
        self._users = _UsersAPI(message_payloads, calls)

    def users(self):
        return self._users


class _FakeEmailTool:
    def __init__(self, service):
        self._service = service

    def _get_service(self):
        return self._service


def test_parse_list_unsubscribe_header_splits_https_and_mailto_values():
    payload = json.loads(
        parse_list_unsubscribe_header(
            "<https://example.com/unsub?id=123>, <mailto:unsubscribe@example.com?subject=unsubscribe>"
        )
    )

    assert payload["https_urls"] == ["https://example.com/unsub?id=123"]
    assert payload["mailto_urls"] == ["mailto:unsubscribe@example.com?subject=unsubscribe"]
    assert payload["other_values"] == []


def test_classify_unsubscribe_method_detects_one_click_when_post_header_exists():
    parsed = {
        "https_urls": ["https://example.com/unsub?id=123"],
        "mailto_urls": ["mailto:unsubscribe@example.com"],
    }

    payload = json.loads(
        classify_unsubscribe_method(
            parsed_list_unsubscribe=parsed,
            list_unsubscribe_post="List-Unsubscribe=One-Click",
        )
    )

    assert payload["method"] == "one_click"
    assert payload["one_click_url"] == "https://example.com/unsub?id=123"
    assert payload["mailto_url"] is None


def test_classify_unsubscribe_method_prefers_mailto_over_website_without_one_click():
    parsed = {
        "https_urls": ["https://example.com/preferences"],
        "mailto_urls": ["mailto:unsubscribe@example.com?subject=unsubscribe"],
    }

    payload = json.loads(
        classify_unsubscribe_method(
            parsed_list_unsubscribe=parsed,
            list_unsubscribe_post="",
        )
    )

    assert payload["method"] == "mailto"
    assert payload["mailto_url"] == "mailto:unsubscribe@example.com?subject=unsubscribe"
    assert payload["website_url"] == "https://example.com/preferences"


def test_get_email_headers_fetches_metadata_headers_only():
    calls = []
    message_payloads = {
        "msg-001": {
            "id": "msg-001",
            "threadId": "thread-001",
            "payload": {
                "headers": [
                    {"name": "From", "value": "News <news@example.com>"},
                    {"name": "Subject", "value": "Weekly update"},
                    {"name": "List-Unsubscribe", "value": "<https://example.com/unsub>"},
                    {"name": "List-Unsubscribe-Post", "value": "List-Unsubscribe=One-Click"},
                ]
            },
        }
    }
    service = _FakeService(message_payloads, calls)
    email_tool = _FakeEmailTool(service)

    payload = json.loads(
        get_email_headers_from_email_tool(
            email_tool=email_tool,
            email_id="msg-001",
            header_names=["From", "List-Unsubscribe", "List-Unsubscribe-Post"],
        )
    )

    assert payload["ok"] is True
    assert payload["email_id"] == "msg-001"
    assert payload["headers"]["From"] == "News <news@example.com>"
    assert payload["headers"]["List-Unsubscribe"] == "<https://example.com/unsub>"
    assert calls == [
        (
            "message_get",
            {
                "userId": "me",
                "id": "msg-001",
                "format": "metadata",
                "metadataHeaders": ["From", "List-Unsubscribe", "List-Unsubscribe-Post"],
            },
        )
    ]


def test_parse_mailto_url_extracts_send_fields():
    payload = json.loads(
        parse_mailto_url("mailto:unsubscribe@example.com?subject=Remove%20me&body=Please%20unsubscribe")
    )

    assert payload["ok"] is True
    assert payload["to"] == "unsubscribe@example.com"
    assert payload["subject"] == "Remove me"
    assert payload["body"] == "Please unsubscribe"


def test_post_one_click_unsubscribe_posts_expected_form_body(monkeypatch):
    calls = []

    class _Response:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def getcode(self):
            return 204

        def read(self, size):
            return b""

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        return _Response()

    monkeypatch.setattr(unsubscribe_tools, "urlopen", fake_urlopen)

    payload = json.loads(post_one_click_unsubscribe("https://example.com/unsub?id=123", timeout_seconds=3))

    assert payload["status"] == "confirmed"
    assert payload["http_status"] == 204
    assert calls[0][1] == 3
    request = calls[0][0]
    assert request.get_method() == "POST"
    assert request.data == b"List-Unsubscribe=One-Click"
