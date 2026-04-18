"""Tests for conversational email confirmation flow."""

import importlib
import os

from connectonion import Gmail


class FakeAgent:
    def __init__(self, turn: int, user_prompt: str):
        self.current_session = {
            "turn": turn,
            "user_prompt": user_prompt,
            "trace": [],
        }

    def _record_trace(self, entry):
        self.current_session.setdefault("trace", []).append(entry)


def _load_agent_module():
    os.environ["LINKED_GMAIL"] = "true"
    import agent as agent_module
    importlib.reload(agent_module)
    return agent_module


def _keep_draft_as_is(agent_module, monkeypatch):
    monkeypatch.setattr(
        agent_module,
        "_clean_email_args_with_llm",
        lambda agent, tool_name, args: agent_module._normalize_email_args(tool_name, args),
    )


def test_cleanup_uses_current_sender_name(monkeypatch):
    agent_module = _load_agent_module()
    monkeypatch.setattr(agent_module, "_current_sender_name", lambda: "Keyvan Zhuo")
    monkeypatch.setattr(
        agent_module,
        "llm_do",
        lambda *args, **kwargs: agent_module.CleanSendDraft(
            subject="关于下周末去歌剧院的计划",
            body="亲爱的 Keyvan，\n\n期待你的回复。\n\n祝好，\n[你的名字]",
        ),
    )

    result = agent_module._clean_email_args_with_llm(
        None,
        "send",
        {
            "to": "keyvan.z.0413@gmail.com",
            "subject": "关于下周末去歌剧院的计划",
            "body": "亲爱的 Keyvan，\n\n期待你的回复。\n\n祝好，\n[你的名字]",
            "cc": "",
            "bcc": "",
        },
    )

    assert result["body"].endswith("祝好，\nKeyvan Zhuo")
    assert "[你的名字]" not in result["body"]


def test_agent_refreshes_system_prompt_before_each_input(monkeypatch):
    agent_module = _load_agent_module()
    prompts = iter([
        "The sender's name is: First Sender",
        "The sender's name is: Second Sender",
    ])

    monkeypatch.setattr(agent_module, "_build_system_prompt", lambda: next(prompts))
    seen_prompts = []

    def fake_agent_input(self, prompt, max_iterations=None, session=None, images=None, files=None):
        seen_prompts.append(self.system_prompt)
        return "ok"

    monkeypatch.setattr(agent_module.Agent, "input", fake_agent_input)

    assert agent_module.main_agent.input("first") == "ok"
    assert agent_module.main_agent.input("second") == "ok"
    assert seen_prompts == [
        "The sender's name is: First Sender",
        "The sender's name is: Second Sender",
    ]


def test_send_stages_draft_before_sending(monkeypatch):
    agent_module = _load_agent_module()
    calls = []

    def fake_send(self, to, subject, body, cc=None, bcc=None):
        calls.append((to, subject, body, cc, bcc))
        return "sent"

    monkeypatch.setattr(Gmail, "send", fake_send)
    monkeypatch.setattr(
        agent_module,
        "_clean_email_args_with_llm",
        lambda agent, tool_name, args: {
            "to": args["to"],
            "subject": args["subject"],
            "body": "你好，想确认一下下周四的汇报安排。\n\n祝好，",
            "cc": "",
            "bcc": "",
        },
    )

    gmail = agent_module.GmailCompat()
    agent = FakeAgent(turn=1, user_prompt="发一封邮件给小黑，确认下周四的汇报")

    result = gmail.send(
        to="xhy413604@gmail.com",
        subject="关于下周四的汇报",
        body="你好，想确认一下下周四的汇报安排。",
        agent=agent,
    )

    assert calls == []
    assert "NO EMAIL HAS BEEN SENT YET." in result
    assert "[你的名字]" not in result
    assert "Next step:" not in result
    assert agent.current_session["gmail_pending_draft"]["tool_name"] == "send"
    assert agent.current_session["outbound_email_state"]["phase"] == "draft_ready"
    assert agent.current_session["outbound_email_state"]["recipient"] == "xhy413604@gmail.com"
    assert agent.current_session["outbound_email_state"]["topic"] == "关于下周四的汇报"
    assert agent.current_session["halt_turn"] is True
    assert agent.current_session["result_override"] == result


def test_send_requires_later_turn_confirmation(monkeypatch):
    agent_module = _load_agent_module()
    calls = []

    def fake_send(self, to, subject, body, cc=None, bcc=None):
        calls.append((to, subject, body, cc, bcc))
        return "Reply sent successfully. Message ID: 123"

    monkeypatch.setattr(Gmail, "send", fake_send)
    _keep_draft_as_is(agent_module, monkeypatch)
    monkeypatch.setattr(
        agent_module,
        "llm_do",
        lambda *args, **kwargs: agent_module.PendingEmailIntent(intent="confirm_send"),
    )

    gmail = agent_module.GmailCompat()
    agent = FakeAgent(turn=1, user_prompt="发一封邮件给小黑，确认下周四的汇报")

    gmail.send(
        to="xhy413604@gmail.com",
        subject="关于下周四的汇报",
        body="你好，想确认一下下周四的汇报安排。",
        agent=agent,
    )

    agent.current_session["turn"] = 2
    agent.current_session["user_prompt"] = "没啥问题，发吧"

    result = gmail.send(
        to="xhy413604@gmail.com",
        subject="关于下周四的汇报",
        body="你好，想确认一下下周四的汇报安排。",
        agent=agent,
    )

    assert calls == [("xhy413604@gmail.com", "关于下周四的汇报", "你好，想确认一下下周四的汇报安排。", None, None)]
    assert result == "Reply sent successfully. Message ID: 123"
    assert "gmail_pending_draft" not in agent.current_session
    assert "outbound_email_state" not in agent.current_session
    assert agent.current_session["stop_signal"] is True
    assert "Reply sent successfully. Message ID: 123" in agent.current_session["result_override"]
    assert "继续处理别的事情" in agent.current_session["result_override"]


def test_send_can_be_cancelled_by_llm_intent(monkeypatch):
    agent_module = _load_agent_module()
    calls = []

    def fake_send(self, to, subject, body, cc=None, bcc=None):
        calls.append((to, subject, body, cc, bcc))
        return "sent"

    monkeypatch.setattr(Gmail, "send", fake_send)
    _keep_draft_as_is(agent_module, monkeypatch)
    monkeypatch.setattr(
        agent_module,
        "llm_do",
        lambda *args, **kwargs: agent_module.PendingEmailIntent(intent="cancel_send"),
    )

    gmail = agent_module.GmailCompat()
    agent = FakeAgent(turn=1, user_prompt="先起草一封邮件")

    gmail.send(
        to="xhy413604@gmail.com",
        subject="关于下周四的汇报",
        body="你好，想确认一下下周四的汇报安排。",
        agent=agent,
    )

    agent.current_session["turn"] = 2
    agent.current_session["user_prompt"] = "算了先别发"

    result = gmail.send(
        to="xhy413604@gmail.com",
        subject="关于下周四的汇报",
        body="你好，想确认一下下周四的汇报安排。",
        agent=agent,
    )

    assert calls == []
    assert result == "Canceled the pending email draft. No email was sent."
    assert "gmail_pending_draft" not in agent.current_session
    assert "outbound_email_state" not in agent.current_session


def test_send_bypasses_conversational_confirmation_after_plugin_approval(monkeypatch):
    agent_module = _load_agent_module()
    calls = []

    def fake_send(self, to, subject, body, cc=None, bcc=None):
        calls.append((to, subject, body, cc, bcc))
        return "sent"

    monkeypatch.setattr(Gmail, "send", fake_send)
    _keep_draft_as_is(agent_module, monkeypatch)

    gmail = agent_module.GmailCompat()
    agent = FakeAgent(turn=1, user_prompt="发一封邮件给小黑")
    agent.current_session["gmail_force_send"] = {
        "tool_name": "send",
        "args": {
            "to": "xhy413604@gmail.com",
            "subject": "关于下周四的汇报",
            "body": "你好，想确认一下下周四的汇报安排。",
            "cc": None,
            "bcc": None,
        },
    }

    result = gmail.send(
        to="xhy413604@gmail.com",
        subject="关于下周四的汇报",
        body="你好，想确认一下下周四的汇报安排。",
        agent=agent,
    )

    assert calls == [("xhy413604@gmail.com", "关于下周四的汇报", "你好，想确认一下下周四的汇报安排。", None, None)]
    assert result == "sent"
    assert "gmail_force_send" not in agent.current_session
    assert agent.current_session["stop_signal"] is True
    assert "继续处理别的事情" in agent.current_session["result_override"]


def test_send_uses_trace_to_restore_pending_draft_across_http_turns(monkeypatch):
    agent_module = _load_agent_module()
    calls = []

    def fake_send(self, to, subject, body, cc=None, bcc=None):
        calls.append((to, subject, body, cc, bcc))
        return "Email sent successfully. Message ID: abc123"

    monkeypatch.setattr(Gmail, "send", fake_send)
    _keep_draft_as_is(agent_module, monkeypatch)
    monkeypatch.setattr(
        agent_module,
        "llm_do",
        lambda *args, **kwargs: agent_module.PendingEmailIntent(intent="confirm_send"),
    )

    gmail = agent_module.GmailCompat()
    first_agent = FakeAgent(turn=1, user_prompt="发测试邮件")

    gmail.send(
        to="keyvan.z.0413@gmail.com",
        subject="Quick Check-In",
        body="Hi Keyvan,\n\nTest.\n",
        agent=first_agent,
    )

    restored_agent = FakeAgent(turn=2, user_prompt="可以，就按这个发出去")
    restored_agent.current_session["trace"] = list(first_agent.current_session["trace"])

    result = gmail.send(
        to="keyvan.z.0413@gmail.com",
        subject="Quick Check-In",
        body="Hi Keyvan,\n\nTest.\n",
        agent=restored_agent,
    )

    assert calls == [("keyvan.z.0413@gmail.com", "Quick Check-In", "Hi Keyvan,\n\nTest.\n", None, None)]
    assert result == "Email sent successfully. Message ID: abc123"
    assert "outbound_email_state" not in restored_agent.current_session


def test_send_confirmation_uses_pending_cleaned_draft_even_if_current_args_differ(monkeypatch):
    agent_module = _load_agent_module()
    calls = []

    def fake_send(self, to, subject, body, cc=None, bcc=None):
        calls.append((to, subject, body, cc, bcc))
        return "Email sent successfully. Message ID: cleaned123"

    monkeypatch.setattr(Gmail, "send", fake_send)
    monkeypatch.setattr(
        agent_module,
        "_clean_email_args_with_llm",
        lambda agent, tool_name, args: {
            "to": args["to"],
            "subject": args["subject"],
            "body": "亲爱的 Keyvan，\n\n期待你的回复！\n\n祝好，\nKeyvan Zhuo",
            "cc": "",
            "bcc": "",
        },
    )
    monkeypatch.setattr(agent_module, "_classify_pending_email_intent", lambda *args, **kwargs: "confirm_send")

    gmail = agent_module.GmailCompat()
    agent = FakeAgent(turn=1, user_prompt="起草邮件")

    gmail.send(
        to="keyvan.z.0413@gmail.com",
        subject="约定下个月去歌剧院的计划",
        body="亲爱的 Keyvan，\n\n期待你的回复！\n\n祝好，\n[你的名字]",
        agent=agent,
    )

    agent.current_session["turn"] = 2
    agent.current_session["user_prompt"] = "发送"

    result = gmail.send(
        to="keyvan.z.0413@gmail.com",
        subject="约定下个月去歌剧院的计划",
        body="亲爱的 Keyvan，\n\n期待你的回复！\n\n祝好，\n[你的名字]",
        agent=agent,
    )

    assert result == "Email sent successfully. Message ID: cleaned123"
    assert calls == [
        (
            "keyvan.z.0413@gmail.com",
            "约定下个月去歌剧院的计划",
            "亲爱的 Keyvan，\n\n期待你的回复！\n\n祝好，\nKeyvan Zhuo",
            None,
            None,
        )
    ]
    assert "gmail_pending_draft" not in agent.current_session
    assert "outbound_email_state" not in agent.current_session
    assert agent.current_session["stop_signal"] is True


def test_send_failure_returns_failure_message_and_keeps_pending_draft(monkeypatch):
    agent_module = _load_agent_module()
    _keep_draft_as_is(agent_module, monkeypatch)

    def fake_send(self, to, subject, body, cc=None, bcc=None):
        raise TimeoutError("The read operation timed out")

    monkeypatch.setattr(Gmail, "send", fake_send)
    monkeypatch.setattr(
        agent_module,
        "llm_do",
        lambda *args, **kwargs: agent_module.PendingEmailIntent(intent="confirm_send"),
    )

    gmail = agent_module.GmailCompat()
    agent = FakeAgent(turn=1, user_prompt="发测试邮件")

    gmail.send(
        to="keyvan.z.0413@gmail.com",
        subject="Quick Check-In",
        body="Hi Keyvan,\n\nTest.\n",
        agent=agent,
    )

    agent.current_session["turn"] = 2
    agent.current_session["user_prompt"] = "发送"

    try:
        gmail.send(
            to="keyvan.z.0413@gmail.com",
            subject="Quick Check-In",
            body="Hi Keyvan,\n\nTest.\n",
            agent=agent,
        )
    except TimeoutError:
        pass
    else:
        raise AssertionError("send should raise when Gmail send fails")

    assert agent.current_session["gmail_pending_draft"]["tool_name"] == "send"
    assert agent.current_session["outbound_email_state"]["phase"] == "draft_ready"
    assert agent.current_session["stop_signal"] is True
    assert "邮件发送失败" in agent.current_session["result_override"]
    assert "草稿已保留" in agent.current_session["result_override"]


def test_agent_background_cancellation_clears_pending_draft(monkeypatch):
    agent_module = _load_agent_module()
    monkeypatch.setattr(agent_module, "_has_interactive_confirmation_path", lambda agent: False)
    monkeypatch.setattr(
        agent_module,
        "llm_do",
        lambda *args, **kwargs: agent_module.PendingEmailIntent(intent="cancel_send"),
    )

    agent = agent_module.main_agent
    agent.current_session = {
        "messages": [
            {"role": "system", "content": "prompts/gmail_agent.md"},
            {"role": "user", "content": "算了先别发"},
        ],
        "trace": [
            {
                "type": "email_draft_pending",
                "tool_name": "send",
                "args": {
                    "to": "keyvan.z.0413@gmail.com",
                    "subject": "Quick Check-In",
                    "body": "Hi Keyvan,\n\nTest.\n",
                    "cc": "",
                    "bcc": "",
                },
                "turn": 1,
            }
        ],
        "turn": 2,
        "iteration": 0,
        "user_prompt": "算了先别发",
    }

    result = agent._run_iteration_loop(15)

    assert result == "Canceled the pending email draft. No email was sent."
    assert "gmail_pending_draft" not in agent.current_session
    assert "outbound_email_state" not in agent.current_session


def test_agent_background_confirmation_sends_pending_draft(monkeypatch):
    agent_module = _load_agent_module()
    monkeypatch.setattr(agent_module, "_has_interactive_confirmation_path", lambda agent: False)
    monkeypatch.setattr(
        agent_module,
        "llm_do",
        lambda *args, **kwargs: agent_module.PendingEmailIntent(intent="confirm_send"),
    )
    delivered = []

    monkeypatch.setattr(
        agent_module,
        "_send_pending_email_now",
        lambda agent, pending: delivered.append(pending) or "Email sent successfully. Message ID: host123",
    )

    agent = agent_module.main_agent
    agent.current_session = {
        "messages": [
            {"role": "system", "content": "prompts/gmail_agent.md"},
            {"role": "user", "content": "发送"},
        ],
        "trace": [
            {
                "type": "email_draft_pending",
                "tool_name": "send",
                "args": {
                    "to": "keyvan.z.0413@gmail.com",
                    "subject": "约定下个月去歌剧院的计划",
                    "body": "亲爱的 Keyvan，\n\n期待你的回复！\n\n祝好，\nKeyvan Zhuo",
                    "cc": "",
                    "bcc": "",
                },
                "turn": 1,
            }
        ],
        "turn": 2,
        "iteration": 0,
        "user_prompt": "发送",
    }

    result = agent._run_iteration_loop(15)

    assert result == "Email sent successfully. Message ID: host123"
    assert delivered == [
        {
            "tool_name": "send",
            "args": {
                "to": "keyvan.z.0413@gmail.com",
                "subject": "约定下个月去歌剧院的计划",
                "body": "亲爱的 Keyvan，\n\n期待你的回复！\n\n祝好，\nKeyvan Zhuo",
                "cc": "",
                "bcc": "",
            },
            "turn": 1,
        }
    ]
    assert "gmail_pending_draft" not in agent.current_session
    assert "outbound_email_state" not in agent.current_session
