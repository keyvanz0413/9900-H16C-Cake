from __future__ import annotations

import json
import base64

from tools.unsubscribe_tool import (
    post_one_click_unsubscribe,
    build_get_unsubscribe_info_tool,
    get_unsubscribe_info_from_email_tool,
)
import tools.unsubscribe_tool as unsubscribe_tool_module


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

    monkeypatch.setattr(unsubscribe_tool_module, "urlopen", fake_urlopen)

    payload = json.loads(post_one_click_unsubscribe("https://example.com/unsub?id=123", timeout_seconds=3))

    assert payload["status"] == "confirmed"
    assert payload["http_status"] == 204
    assert calls[0][1] == 3
    request = calls[0][0]
    assert request.get_method() == "POST"
    assert request.data == b"List-Unsubscribe=One-Click"


def test_post_one_click_unsubscribe_treats_202_as_request_accepted(monkeypatch):
    class _Response:
        status = 202

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def getcode(self):
            return 202

        def read(self, size):
            return b"Unsubscribe Request Accepted"

    def fake_urlopen(request, timeout):
        return _Response()

    monkeypatch.setattr(unsubscribe_tool_module, "urlopen", fake_urlopen)

    payload = json.loads(post_one_click_unsubscribe("https://example.com/unsub?id=123"))

    assert payload["status"] == "request_accepted"
    assert payload["sender_unsubscribe_status"] == "request_accepted"
    assert payload["gmail_subscription_ui_status"] == "not_updated_by_agent"


def _encode_text(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("utf-8").rstrip("=")


def test_build_get_unsubscribe_info_tool_exposes_expected_name_and_error_shape():
    tool = build_get_unsubscribe_info_tool(lambda: None)

    payload = json.loads(tool(["msg-001"]))

    assert tool.__name__ == "get_unsubscribe_info"
    assert payload["summary"]["requested_count"] == 1
    assert payload["summary"]["analyzed_count"] == 0
    assert payload["summary"]["error_count"] == 1
    assert payload["items"] == [
        {
            "email_id": "msg-001",
            "error": "Unsubscribe inspection is only available when Gmail is connected.",
        }
    ]


def test_get_unsubscribe_info_from_email_tool_batches_and_omits_missing_options():
    calls = []
    message_payloads = {
        "msg-one": {
            "id": "msg-one",
            "payload": {
                "headers": [
                    {
                        "name": "List-Unsubscribe",
                        "value": "<https://example.com/unsub?id=123>, <mailto:unsubscribe@example.com?subject=unsubscribe>",
                    },
                    {"name": "List-Unsubscribe-Post", "value": "List-Unsubscribe=One-Click"},
                ]
            },
        },
        "msg-mail": {
            "id": "msg-mail",
            "payload": {
                "headers": [
                    {
                        "name": "List-Unsubscribe",
                        "value": "<mailto:leave@example.com?subject=unsubscribe&body=please%20remove%20me>",
                    }
                ]
            },
        },
    }
    service = _FakeService(message_payloads, calls)
    email_tool = _FakeEmailTool(service)

    payload = json.loads(
        get_unsubscribe_info_from_email_tool(
            email_tool=email_tool,
            email_ids=["msg-one", "msg-mail"],
        )
    )

    assert payload["summary"] == {
        "requested_count": 2,
        "analyzed_count": 2,
        "error_count": 0,
    }

    first_item = payload["items"][0]
    assert first_item["email_id"] == "msg-one"
    assert first_item["unsubscribe"]["method"] == "one_click"
    assert set(first_item["unsubscribe"]["options"].keys()) == {"one_click", "mailto"}
    assert first_item["unsubscribe"]["options"]["one_click"]["request_payload"] == {
        "url": "https://example.com/unsub?id=123"
    }
    assert first_item["unsubscribe"]["options"]["mailto"]["send_payload"] == {
        "to": "unsubscribe@example.com",
        "subject": "unsubscribe",
        "body": "",
    }
    assert "website" not in first_item["unsubscribe"]["options"]

    second_item = payload["items"][1]
    assert second_item["email_id"] == "msg-mail"
    assert second_item["unsubscribe"]["method"] == "mailto"
    assert set(second_item["unsubscribe"]["options"].keys()) == {"mailto"}
    assert second_item["unsubscribe"]["options"]["mailto"]["send_payload"] == {
        "to": "leave@example.com",
        "subject": "unsubscribe",
        "body": "please remove me",
    }


def test_get_unsubscribe_info_from_email_tool_promotes_manual_body_link_to_website():
    calls = []
    message_payloads = {
        "msg-site": {
            "id": "msg-site",
            "payload": {
                "headers": [],
                "mimeType": "multipart/alternative",
                "parts": [
                    {
                        "mimeType": "text/html",
                        "body": {
                            "data": _encode_text(
                                '<html><body><a href="https://example.com/manual-unsub?token=abc">Unsubscribe</a></body></html>'
                            )
                        },
                    }
                ],
            },
        }
    }
    service = _FakeService(message_payloads, calls)
    email_tool = _FakeEmailTool(service)

    payload = json.loads(
        get_unsubscribe_info_from_email_tool(
            email_tool=email_tool,
            email_ids=["msg-site"],
        )
    )

    item = payload["items"][0]
    assert item["email_id"] == "msg-site"
    assert item["unsubscribe"]["method"] == "website"
    assert item["unsubscribe"]["options"] == {
        "website": {
            "manual_links": [
                {
                    "label": "Unsubscribe",
                    "source": "text/html",
                    "url": "https://example.com/manual-unsub?token=abc",
                }
            ]
        }
    }
