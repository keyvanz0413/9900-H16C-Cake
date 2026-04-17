"""Tests for the draft reply strategy helper."""

import json
from datetime import datetime, timedelta

from tools.draft_reply import configure_draft_reply, get_draft_reply_strategy
from tools.writing_style import configure_writing_style, get_writing_style_profile


class FakeEmailTool:
    def __init__(self, search_result: str):
        self.search_result = search_result
        self.send_called = False
        self.reply_called = False

    def search_emails(self, query: str, max_results: int) -> str:
        assert max_results == 10
        return self.search_result

    def get_sent_emails(self, max_results: int) -> str:
        assert max_results == 20
        return """Found 4 email(s):

1.  To: Sarah <sarah@example.com>
   Subject: Re: Project update
   Date: Fri, 17 Apr 2026 10:00:00 GMT
   Preview: Hi Sarah, thanks for the update. Sounds good to me. I can review tomorrow. Best, Aiden
   ID: sent-1

2.  To: Bob <bob@example.com>
   Subject: Re: Meeting
   Date: Thu, 16 Apr 2026 10:00:00 GMT
   Preview: Hey Bob, happy to meet next week. Let me know what time works. Thanks, Aiden
   ID: sent-2

3.  To: Priya <priya@example.com>
   Subject: Re: Draft
   Date: Wed, 15 Apr 2026 10:00:00 GMT
   Preview: Hi Priya, thanks. I will take a look and send comments by tomorrow. Best, Aiden
   ID: sent-3

4.  To: Alex <alex@example.com>
   Subject: Re: Follow up
   Date: Tue, 14 Apr 2026 10:00:00 GMT
   Preview: Hi Alex, sounds good. Let me know if anything changes. Thanks, Aiden
   ID: sent-4
"""

    def send(self, *args, **kwargs):
        self.send_called = True
        raise AssertionError("send should not be called")

    def reply(self, *args, **kwargs):
        self.reply_called = True
        raise AssertionError("reply should not be called")


class FakeMemoryTool:
    def read_memory(self, key: str) -> str:
        return "not found"


MEETING_SEARCH_RESULT = """Found 1 email(s):

1.  From: Aiden_Yang <945430408@qq.com>
   Subject: confirm a meeting
   Date: Thu, 9 Apr 2026 01:26:49 +1000
   Preview: I want to remind you that we have a meeting at this Sunday 6:00 pm
   ID: 19d6db41597d2640
"""


EMPTY_SEARCH_RESULT = "Found 0 email(s):"


def _configure(tmp_path, search_result: str) -> tuple[FakeEmailTool, object]:
    profile_path = tmp_path / "writing_style_profile.json"
    email = FakeEmailTool(search_result)
    configure_writing_style(email_tool=email, profile_path=str(profile_path))
    configure_draft_reply(email_tool=email, memory_tool=FakeMemoryTool())
    return email, profile_path


def _load_strategy_result(raw: str) -> dict:
    if raw.startswith("FINAL_RESPONSE_REQUIRED"):
        raw = raw.split("Structured status:", 1)[1].strip()
    return json.loads(raw)


def test_missing_writing_style_blocks_drafting(tmp_path):
    email, _ = _configure(tmp_path, MEETING_SEARCH_RESULT)

    result = _load_strategy_result(
        get_draft_reply_strategy(
            user_request="draft a reply to him, let him know I will join the meeting on time",
            contact_query="Aiden_Yang",
            thread_query="confirm a meeting",
        )
    )

    assert result["draft_readiness"]["ready_to_draft"] is False
    assert result["draft_readiness"]["blocked_by"] == "missing_writing_style"
    assert "learn your style" in result["draft_readiness"]["user_question"]
    assert result["must_not_draft"] is True
    assert result["reply_strategy"]["key_points"] == []
    assert "learn your style" in result["final_response"]
    assert email.send_called is False
    assert email.reply_called is False


def test_fresh_writing_style_allows_confirm_strategy(tmp_path):
    email, _ = _configure(tmp_path, MEETING_SEARCH_RESULT)
    get_writing_style_profile(refresh_profile=True)

    result = _load_strategy_result(
        get_draft_reply_strategy(
            user_request="draft a reply to him, let him know I will join the meeting on time",
            contact_query="Aiden_Yang",
            thread_query="confirm a meeting",
        )
    )

    assert result["draft_readiness"]["ready_to_draft"] is True
    assert result["draft_readiness"]["state"] == "ready"
    assert result["reply_strategy"]["goal"] == "confirm"
    assert result["writing_style"]["profile_state"] == "fresh"
    assert "confirm that the user will join the meeting on time" in result["reply_strategy"]["key_points"]
    assert "time: 6:00 pm" in result["thread_context"]["important_details"]
    assert email.send_called is False
    assert email.reply_called is False


def test_stale_writing_style_blocks_without_allow_stale(tmp_path):
    _email, profile_path = _configure(tmp_path, MEETING_SEARCH_RESULT)
    get_writing_style_profile(refresh_profile=True)
    saved = json.loads(profile_path.read_text(encoding="utf-8"))
    saved["last_updated"] = (datetime.now() - timedelta(days=8)).strftime("%Y-%m-%d")
    profile_path.write_text(json.dumps(saved), encoding="utf-8")

    result = _load_strategy_result(
        get_draft_reply_strategy(
            user_request="draft a reply to him",
            contact_query="Aiden_Yang",
            thread_query="confirm a meeting",
        )
    )

    assert result["draft_readiness"]["ready_to_draft"] is False
    assert result["draft_readiness"]["blocked_by"] == "stale_writing_style"


def test_missing_thread_context_blocks_drafting(tmp_path):
    _configure(tmp_path, EMPTY_SEARCH_RESULT)
    get_writing_style_profile(refresh_profile=True)

    result = _load_strategy_result(
        get_draft_reply_strategy(
            user_request="draft a reply to him",
            contact_query="Unknown",
        )
    )

    assert result["draft_readiness"]["ready_to_draft"] is False
    assert result["draft_readiness"]["blocked_by"] == "missing_thread_context"
