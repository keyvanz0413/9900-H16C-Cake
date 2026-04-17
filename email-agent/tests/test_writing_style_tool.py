"""Tests for the writing style profile helper."""

import json
from datetime import datetime, timedelta

from tools.writing_style import configure_writing_style, get_writing_style_profile


class FakeEmailTool:
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


def test_missing_profile_requires_user_confirmation(tmp_path):
    profile_path = tmp_path / "writing_style_profile.json"
    configure_writing_style(email_tool=FakeEmailTool(), profile_path=str(profile_path))

    result = json.loads(get_writing_style_profile())

    assert result["profile_state"] == "missing"
    assert result["requires_user_confirmation"] is True
    assert result["source"]["saved_profile_used"] is False
    assert not profile_path.exists()


def test_refresh_profile_saves_summarized_style(tmp_path):
    profile_path = tmp_path / "writing_style_profile.json"
    configure_writing_style(email_tool=FakeEmailTool(), profile_path=str(profile_path))

    result = json.loads(get_writing_style_profile(refresh_profile=True))
    saved = json.loads(profile_path.read_text(encoding="utf-8"))

    assert result["profile_state"] == "refreshed"
    assert result["requires_user_confirmation"] is False
    assert result["confidence"] == "medium"
    assert saved["profile"]["tone"] == "polite, concise, and collaborative"
    assert "Hi {name}" in saved["profile"]["greeting_patterns"]
    assert "Best" in saved["profile"]["sign_off_patterns"]
    assert "Project update" not in profile_path.read_text(encoding="utf-8")


def test_fresh_saved_profile_is_reused(tmp_path):
    profile_path = tmp_path / "writing_style_profile.json"
    configure_writing_style(email_tool=FakeEmailTool(), profile_path=str(profile_path))
    get_writing_style_profile(refresh_profile=True)

    result = json.loads(get_writing_style_profile())

    assert result["profile_state"] == "fresh"
    assert result["requires_user_confirmation"] is False
    assert result["source"]["saved_profile_used"] is True
    assert result["source"]["is_stale"] is False


def test_stale_saved_profile_requests_refresh(tmp_path):
    profile_path = tmp_path / "writing_style_profile.json"
    configure_writing_style(email_tool=FakeEmailTool(), profile_path=str(profile_path))
    get_writing_style_profile(refresh_profile=True)
    saved = json.loads(profile_path.read_text(encoding="utf-8"))
    saved["last_updated"] = (datetime.now() - timedelta(days=8)).strftime("%Y-%m-%d")
    profile_path.write_text(json.dumps(saved), encoding="utf-8")

    result = json.loads(get_writing_style_profile(stale_after_days=7))

    assert result["profile_state"] == "stale"
    assert result["requires_user_confirmation"] is True
    assert result["source"]["is_stale"] is True
    assert result["source"]["profile_age_days"] >= 8
