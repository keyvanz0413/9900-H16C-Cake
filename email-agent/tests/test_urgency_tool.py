"""Tests for the urgency ranking helper."""

import json

from tools.urgency import configure_urgency, get_urgent_email_context


class FakeEmailTool:
    def __init__(self):
        self.write_called = False

    def search_emails(self, query: str, max_results: int) -> str:
        assert query == "newer_than:14d"
        assert max_results == 30
        return """Found 5 email(s):

1. [UNREAD] From: Google <no-reply@accounts.google.com>
   Subject: Security alert
   Date: Fri, 17 Apr 2026 10:00:00 GMT
   Preview: New login from an unknown device. If this was not you, review your account.
   ID: email-1

2.  From: Aiden_Yang <945430408@qq.com>
   Subject: confirm a meeting
   Date: Thu, 16 Apr 2026 10:00:00 GMT
   Preview: I want to remind you that we have a meeting this Sunday 6:00 pm.
   ID: email-2

3. [UNREAD] From: Nike <nike@official.nike.com>
   Subject: Make your move
   Date: Wed, 15 Apr 2026 10:00:00 GMT
   Preview: Sale offer rewards points promotion.
   ID: email-3

4. [UNREAD] From: Nike <nike@notifications.nike.com>
   Subject: Here's your one-time code
   Date: Wed, 15 Apr 2026 09:00:00 GMT
   Preview: Your verification code is 123456.
   ID: email-4

5.  From: Stripe <notifications@stripe.com>
   Subject: Payment failed
   Date: Tue, 14 Apr 2026 09:00:00 GMT
   Preview: A customer payment failed and needs attention.
   ID: email-5
"""

    def get_unanswered_emails(self, within_days: int, max_results: int) -> str:
        assert within_days == 14
        assert max_results == 30
        return """Found 1 unanswered email(s) from the last 14 days:

1. From: Aiden_Yang <945430408@qq.com>
   Subject: confirm a meeting
   Age: 2 days (1 messages in thread)
   Thread ID: email-2
"""

    def send(self, *args, **kwargs):
        self.write_called = True
        raise AssertionError("send should not be called")

    def reply(self, *args, **kwargs):
        self.write_called = True
        raise AssertionError("reply should not be called")

    def archive_email(self, *args, **kwargs):
        self.write_called = True
        raise AssertionError("archive should not be called")


def _result() -> tuple[dict, FakeEmailTool]:
    email = FakeEmailTool()
    configure_urgency(email_tool=email)
    return json.loads(get_urgent_email_context()), email


def _find(items: list[dict], email_id: str) -> dict:
    return next(item for item in items if item["email_id"] == email_id)


def test_security_alert_is_high_urgency():
    result, _ = _result()

    google = _find(result["urgent_emails"], "email-1")

    assert google["urgency"] == "high"
    assert google["category"] == "security"
    assert google["score"] >= 70
    assert any("security" in evidence.lower() for evidence in google["evidence"])


def test_meeting_confirmation_from_person_is_medium_or_higher():
    result, _ = _result()

    meeting = _find(result["urgent_emails"], "email-2")

    assert meeting["urgency"] in {"medium", "high"}
    assert meeting["category"] == "meeting"
    assert any("meeting" in evidence.lower() for evidence in meeting["evidence"])
    assert any("unanswered" in evidence.lower() for evidence in meeting["evidence"])


def test_promotional_unread_email_is_deprioritized():
    result, _ = _result()

    nike = _find(result["ignored_emails"], "email-3")

    assert nike["urgency"] == "ignore"
    assert nike["category"] == "promotion"
    assert any("promotional" in evidence.lower() for evidence in nike["evidence"])


def test_one_time_code_without_security_language_is_not_urgent():
    result, _ = _result()

    code = _find(result["ignored_emails"], "email-4")

    assert code["urgency"] == "ignore"
    assert code["category"] in {"verification", "automated"}
    assert any("one-time code" in evidence.lower() for evidence in code["evidence"])


def test_billing_failure_from_automated_sender_is_high_urgency():
    result, _ = _result()

    stripe = _find(result["urgent_emails"], "email-5")

    assert stripe["urgency"] == "high"
    assert stripe["category"] == "billing"
    assert stripe["score"] >= 70


def test_tool_is_read_only_and_returns_summary():
    result, email = _result()

    assert result["summary"]["high_count"] >= 2
    assert result["summary"]["has_urgent_items"] is True
    assert "security" in result["summary"]["top_categories"]
    assert email.write_called is False


def test_snapshot_mode_omits_detailed_lists():
    email = FakeEmailTool()
    configure_urgency(email_tool=email)

    result = json.loads(get_urgent_email_context(mode="snapshot"))

    assert result["source"]["mode"] == "snapshot"
    assert result["urgent_emails"] == []
    assert result["low_priority"] == []
    assert result["ignored_emails"] == []
