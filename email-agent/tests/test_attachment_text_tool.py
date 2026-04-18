from __future__ import annotations

import base64

from tools.attachment_text_tool import extract_recent_attachment_texts_from_email_tool


def _encode_text(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("utf-8").rstrip("=")


class _Execute:
    def __init__(self, payload):
        self._payload = payload

    def execute(self):
        return self._payload


class _AttachmentsAPI:
    def __init__(self, payloads, calls):
        self._payloads = payloads
        self._calls = calls

    def get(self, *, userId, messageId, id):
        self._calls.append(("attachment_get", {"userId": userId, "messageId": messageId, "id": id}))
        return _Execute(self._payloads[id])


class _MessagesAPI:
    def __init__(self, list_payload, message_payloads, attachment_payloads, calls):
        self._list_payload = list_payload
        self._message_payloads = message_payloads
        self._attachment_payloads = attachment_payloads
        self._calls = calls

    def list(self, *, userId, q, maxResults):
        self._calls.append(("list", {"userId": userId, "q": q, "maxResults": maxResults}))
        return _Execute(self._list_payload)

    def get(self, *, userId, id, format):
        self._calls.append(("message_get", {"userId": userId, "id": id, "format": format}))
        return _Execute(self._message_payloads[id])

    def attachments(self):
        return _AttachmentsAPI(self._attachment_payloads, self._calls)


class _UsersAPI:
    def __init__(self, list_payload, message_payloads, attachment_payloads, calls):
        self._messages = _MessagesAPI(list_payload, message_payloads, attachment_payloads, calls)

    def messages(self):
        return self._messages


class _FakeService:
    def __init__(self, list_payload, message_payloads, attachment_payloads, calls):
        self._users = _UsersAPI(list_payload, message_payloads, attachment_payloads, calls)

    def users(self):
        return self._users


class _FakeEmailTool:
    def __init__(self, service):
        self._service_instance = service

    def _get_service(self):
        return self._service_instance


def test_extract_recent_attachment_texts_uses_days_and_max_results():
    calls = []
    list_payload = {"messages": [{"id": "msg-001"}]}
    message_payloads = {
        "msg-001": {
            "id": "msg-001",
            "threadId": "thread-001",
            "payload": {
                "headers": [
                    {"name": "From", "value": "Alice <alice@example.com>"},
                    {"name": "Subject", "value": "Resume attached"},
                    {"name": "Date", "value": "Fri, 18 Apr 2026 10:00:00 +0000"},
                ],
                "parts": [
                    {
                        "filename": "resume.txt",
                        "mimeType": "text/plain",
                        "body": {"data": _encode_text("Backend engineer with Python and LLM experience.")},
                    }
                ],
            },
        }
    }
    attachment_payloads = {}
    service = _FakeService(list_payload, message_payloads, attachment_payloads, calls)
    email_tool = _FakeEmailTool(service)

    result = extract_recent_attachment_texts_from_email_tool(
        email_tool=email_tool,
        days=7,
        max_results=5,
    )

    assert "Query: in:inbox newer_than:7d has:attachment" in result
    assert "Matched message count: 1" in result
    assert "Filename: resume.txt" in result
    assert "Extracted Text:" in result
    assert "Backend engineer with Python and LLM experience." in result
    assert calls[0] == (
        "list",
        {
            "userId": "me",
            "q": "in:inbox newer_than:7d has:attachment",
            "maxResults": 5,
        },
    )


def test_extract_recent_attachment_texts_fetches_attachment_bytes_and_marks_unsupported():
    calls = []
    list_payload = {"messages": [{"id": "msg-002"}]}
    message_payloads = {
        "msg-002": {
            "id": "msg-002",
            "threadId": "thread-002",
            "payload": {
                "headers": [
                    {"name": "From", "value": "Recruiter <recruiter@example.com>"},
                    {"name": "Subject", "value": "Candidate package"},
                ],
                "parts": [
                    {
                        "filename": "candidate_cv.txt",
                        "mimeType": "text/plain",
                        "body": {"attachmentId": "att-001"},
                    },
                    {
                        "filename": "photo.png",
                        "mimeType": "image/png",
                        "body": {"attachmentId": "att-002"},
                    },
                ],
            },
        }
    }
    attachment_payloads = {
        "att-001": {"data": _encode_text("Candidate profile summary from attachment.")},
        "att-002": {"data": _encode_text("not used")},
    }
    service = _FakeService(list_payload, message_payloads, attachment_payloads, calls)
    email_tool = _FakeEmailTool(service)

    result = extract_recent_attachment_texts_from_email_tool(
        email_tool=email_tool,
        days=3,
        max_results=1,
    )

    assert "Filename: candidate_cv.txt" in result
    assert "Candidate profile summary from attachment." in result
    assert "Filename: photo.png" in result
    assert "Status: skipped (unsupported attachment type)" in result
    assert ("attachment_get", {"userId": "me", "messageId": "msg-002", "id": "att-001"}) in calls

