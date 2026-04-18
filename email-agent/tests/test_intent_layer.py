from __future__ import annotations

import io
import json
import threading
from contextlib import redirect_stdout
from pathlib import Path

from intent_layer import (
    DialogueItem,
    IntentLayerError,
    IntentLayerOrchestrator,
    MarkdownMemoryStore,
    PythonSkillExecutor,
    SkillInputFieldSpec,
    SkillLayerError,
    SkillExecutionResult,
    SkillSpec,
    build_tool_function_map,
    load_skill_registry,
    split_context,
)


class FakeAgent:
    def __init__(self, responses: list[str], *, name: str = "fake-agent", max_iterations: int = 1):
        self._responses = list(responses)
        self.calls: list[tuple[str, int | None, dict | None, list[str] | None, list[dict] | None]] = []
        self.name = name
        self.max_iterations = max_iterations
        self.tools = []
        self.llm = type("LLM", (), {"model": "fake-model"})()
        self.current_session = None

    def input(
        self,
        prompt: str,
        max_iterations: int | None = None,
        session: dict | None = None,
        images: list[str] | None = None,
        files: list[dict] | None = None,
    ) -> str:
        self.calls.append((prompt, max_iterations, session, images, files))
        if session is not None:
            self.current_session = session
        if not self._responses:
            raise AssertionError("FakeAgent received more calls than expected.")
        return self._responses.pop(0)


class FakeSkillExecutor:
    def __init__(self, result: SkillExecutionResult):
        self.result = result
        self.calls: list[tuple[SkillSpec, dict[str, object], str, str, list[DialogueItem], int | None]] = []

    def run(
        self,
        skill_spec: SkillSpec,
        *,
        skill_arguments: dict[str, object],
        current_message: str,
        intent_decision,
        recent_context: list[DialogueItem],
        max_iterations: int | None = None,
    ) -> SkillExecutionResult:
        self.calls.append((skill_spec, skill_arguments, current_message, intent_decision.intent, recent_context, max_iterations))
        return self.result


class ToolBox:
    def search_emails(self, query: str) -> str:
        """Search emails."""
        return f"search:{query}"

    def send(self, recipient: str, body: str) -> str:
        """Send email."""
        return f"sent:{recipient}:{body}"


class WeeklySummaryToolBox:
    def __init__(self):
        self.calls: list[tuple[str, dict[str, object]]] = []
        self._lock = threading.Lock()

    def _record(self, tool_name: str, **kwargs: object) -> str:
        with self._lock:
            self.calls.append((tool_name, kwargs))
        return f"{tool_name}:{json.dumps(kwargs, ensure_ascii=False, sort_keys=True)}"

    def get_my_identity(self) -> str:
        return self._record("get_my_identity")

    def search_emails(self, query: str, max_results: int = 10) -> str:
        return self._record("search_emails", query=query, max_results=max_results)

    def get_unanswered_emails(self, within_days: int = 120, max_results: int = 20) -> str:
        return self._record("get_unanswered_emails", within_days=within_days, max_results=max_results)

    def list_events(self, days_ahead: int = 7, max_results: int = 20) -> str:
        return self._record("list_events", days_ahead=days_ahead, max_results=max_results)


class WritingStyleToolBox:
    def __init__(self):
        self.calls: list[tuple[str, dict[str, object]]] = []
        self._lock = threading.Lock()

    def get_sent_emails(self, max_results: int = 10) -> str:
        with self._lock:
            self.calls.append(("get_sent_emails", {"max_results": max_results}))
        return (
            "Found sent emails:\n"
            "- Subject: Coffee Chat Tomorrow at 3 PM\n"
            "  Body: Hi Zenglin, Would you be available to meet for a coffee chat tomorrow at 3 PM?\n"
            "- Subject: Next week\n"
            "  Body: Hi Zenglin Zhong, I wanted to reach out about next week.\n"
            "- Subject: 明晚一起吃饭\n"
            "  Body: Zenglin 你好， 你明天晚上有空一起吃晚饭吗？"
        )


class UrgentEmailToolBox:
    def __init__(self):
        self.calls: list[tuple[str, dict[str, object]]] = []
        self._lock = threading.Lock()

    def _record(self, tool_name: str, **kwargs: object) -> None:
        with self._lock:
            self.calls.append((tool_name, kwargs))

    def search_emails(self, query: str, max_results: int = 10) -> str:
        self._record("search_emails", query=query, max_results=max_results)
        if "from:founder@example.com" in query:
            return (
                "Found 1 email(s):\n\n"
                "1. [UNREAD] From: Founder <founder@example.com>\n"
                "   Subject: urgent deadline update\n"
                "   Date: Thu, 17 Apr 2026 17:00:00 +0000\n"
                "   Preview: Need your response before EOD...\n"
                "   ID: unanswered-001\n"
            )
        return (
            "Found 3 email(s):\n\n"
            "1. [UNREAD] From: Ops <ops@example.com>\n"
            "   Subject: ACTION REQUIRED: billing issue\n"
            "   Date: Fri, 18 Apr 2026 09:00:00 +0000\n"
            "   Preview: Please respond today about the billing issue...\n"
            "   ID: urgent-001\n\n"
            "2. [UNREAD] From: Security <security@example.com>\n"
            "   Subject: Security alert\n"
            "   Date: Fri, 18 Apr 2026 08:30:00 +0000\n"
            "   Preview: Immediate review recommended...\n"
            "   ID: urgent-002\n\n"
            "3. [UNREAD] From: Founder <founder@example.com>\n"
            "   Subject: urgent deadline update\n"
            "   Date: Thu, 17 Apr 2026 17:00:00 +0000\n"
            "   Preview: Need your response before EOD...\n"
            "   ID: urgent-003\n"
        )

    def get_unanswered_emails(self, within_days: int = 120, max_results: int = 20) -> str:
        self._record("get_unanswered_emails", within_days=within_days, max_results=max_results)
        return (
            f"Found 1 unanswered email(s) from the last {within_days} days:\n\n"
            "1. From: Founder <founder@example.com>\n"
            "   Subject: urgent deadline update\n"
            "   Age: 1 days (2 messages in thread)\n"
            "   Thread ID: thread-123\n"
        )

    def get_email_body(self, email_id: str) -> str:
        self._record("get_email_body", email_id=email_id)
        return f"Email body for {email_id}"


class BugIssueToolBox:
    def __init__(self):
        self.calls: list[tuple[str, dict[str, object]]] = []
        self._lock = threading.Lock()

    def _record(self, tool_name: str, **kwargs: object) -> None:
        with self._lock:
            self.calls.append((tool_name, kwargs))

    def search_emails(self, query: str, max_results: int = 10) -> str:
        self._record("search_emails", query=query, max_results=max_results)
        return (
            "Found 3 email(s):\n\n"
            "1. [UNREAD] From: CI Bot <ci@example.com>\n"
            "   Subject: build failed on main\n"
            "   Date: Fri, 18 Apr 2026 09:15:00 +0000\n"
            "   Preview: The latest pipeline failed on the test stage...\n"
            "   ID: bug-001\n\n"
            "2. [UNREAD] From: GitHub <noreply@github.com>\n"
            "   Subject: issue opened: checkout regression\n"
            "   Date: Fri, 18 Apr 2026 08:50:00 +0000\n"
            "   Preview: A new issue was opened for a checkout regression...\n"
            "   ID: bug-002\n\n"
            "3. [UNREAD] From: Alerts <alerts@example.com>\n"
            "   Subject: failing tests in payments service\n"
            "   Date: Thu, 17 Apr 2026 23:40:00 +0000\n"
            "   Preview: Multiple tests started failing after the latest deploy...\n"
            "   ID: bug-003\n"
        )

    def get_email_body(self, email_id: str) -> str:
        self._record("get_email_body", email_id=email_id)
        return f"Email body for {email_id}"


class ResumeCandidateToolBox:
    def __init__(self):
        self.calls: list[tuple[str, dict[str, object]]] = []
        self._lock = threading.Lock()

    def _record(self, tool_name: str, **kwargs: object) -> None:
        with self._lock:
            self.calls.append((tool_name, kwargs))

    def search_emails(self, query: str, max_results: int = 10) -> str:
        self._record("search_emails", query=query, max_results=max_results)
        return (
            "Found 2 email(s):\n\n"
            "1. [UNREAD] From: Riley Applicant <riley@example.com>\n"
            "   Subject: Application for Backend Engineer role\n"
            "   Date: Fri, 18 Apr 2026 09:30:00 +0000\n"
            "   Preview: Please find attached my resume and portfolio...\n"
            "   ID: resume-001\n\n"
            "2. [UNREAD] From: Jules Recruiter <jules@agency.com>\n"
            "   Subject: Candidate profile for ML Engineer\n"
            "   Date: Thu, 17 Apr 2026 17:15:00 +0000\n"
            "   Preview: Sharing a candidate profile for your review...\n"
            "   ID: resume-002\n"
        )

    def get_email_attachments(self, email_id: str) -> str:
        self._record("get_email_attachments", email_id=email_id)
        if email_id == "resume-001":
            return (
                "Found 1 attachment(s):\n\n"
                "1. Riley_Resume.pdf (152.4 KB)\n"
                "   ID: att-resume-001\n"
            )
        return "No attachments in this email."

    def extract_recent_attachment_texts(self, query: str, max_results: int = 10) -> str:
        self._record("extract_recent_attachment_texts", query=query, max_results=max_results)
        return (
            "Recent attachment text extraction results.\n"
            'Query: in:inbox newer_than:7d (candidate OR applicant OR application OR resume OR cv OR portfolio OR "job application" OR "application for" OR "applying for" OR "cover letter" OR "candidate profile" OR "candidate submission" OR "resume attached" OR "cv attached") has:attachment\n'
            "Message scan limit: 350\n"
            "Matched message count: 2\n"
            "Attachment count: 2\n"
            "Extracted attachment count: 2\n\n"
            "[EMAIL_1]\n"
            "Message ID: resume-001\n"
            "Thread ID: thread-resume-001\n"
            "From: Riley Applicant <riley@example.com>\n"
            "Subject: Application for Backend Engineer role\n"
            "Date: Fri, 18 Apr 2026 09:30:00 +0000\n"
            "Attachment count: 1\n"
            "[ATTACHMENT_1_1]\n"
            "Filename: Riley_Resume.pdf\n"
            "MIME Type: application/pdf\n"
            "Attachment ID: att-resume-001\n"
            "Status: extracted\n"
            "Extracted Text:\n"
            "Riley Applicant. Backend engineer. Python, FastAPI, Postgres, LLM tooling.\n\n"
            "[EMAIL_2]\n"
            "Message ID: unrelated-999\n"
            "Thread ID: thread-unrelated-999\n"
            "From: Ops <ops@example.com>\n"
            "Subject: Statement attached\n"
            "Date: Thu, 17 Apr 2026 08:00:00 +0000\n"
            "Attachment count: 1\n"
            "[ATTACHMENT_2_1]\n"
            "Filename: statement.pdf\n"
            "MIME Type: application/pdf\n"
            "Attachment ID: att-unrelated-999\n"
            "Status: extracted\n"
            "Extracted Text:\n"
            "Monthly statement.\n"
        )


class DraftReplyToolBox:
    def __init__(self):
        self.calls: list[tuple[str, dict[str, object]]] = []
        self._lock = threading.Lock()

    def _record(self, tool_name: str, **kwargs: object) -> None:
        with self._lock:
            self.calls.append((tool_name, kwargs))

    def search_emails(self, query: str, max_results: int = 10) -> str:
        self._record("search_emails", query=query, max_results=max_results)
        if "from:brenda@example.com" in query:
            return (
                "Found 1 email(s):\n\n"
                "1. [UNREAD] From: Brenda <brenda@example.com>\n"
                "   Subject: Re: Coffee chat next week\n"
                "   Date: Fri, 18 Apr 2026 08:00:00 +0000\n"
                "   Preview: Tuesday afternoon works for me...\n"
                "   ID: reply-unanswered-002\n"
            )
        return (
            "Found 2 email(s):\n\n"
            "1. [UNREAD] From: Zenglin <zenglin0813@gmail.com>\n"
            "   Subject: Re: Coffee Chat Tomorrow at 3 PM\n"
            "   Date: Fri, 18 Apr 2026 09:10:00 +0000\n"
            "   Preview: Tomorrow at 3 pm works well for me...\n"
            "   ID: reply-search-001\n\n"
            "2. [UNREAD] From: Zenglin <zenglin0813@gmail.com>\n"
            "   Subject: Next week\n"
            "   Date: Thu, 17 Apr 2026 09:10:00 +0000\n"
            "   Preview: I am also free next Tuesday...\n"
            "   ID: reply-search-002\n"
        )

    def get_unanswered_emails(self, within_days: int = 120, max_results: int = 20) -> str:
        self._record("get_unanswered_emails", within_days=within_days, max_results=max_results)
        return (
            f"Found 2 unanswered email(s) from the last {within_days} days:\n\n"
            "1. From: Alice <alice@example.com>\n"
            "   Subject: Budget review follow-up\n"
            "   Age: 2 days (2 messages in thread)\n"
            "   Thread ID: thread-001\n\n"
            "2. From: Brenda <brenda@example.com>\n"
            "   Subject: Re: Coffee chat next week\n"
            "   Age: 1 days (3 messages in thread)\n"
            "   Thread ID: thread-002\n"
        )

    def get_email_body(self, email_id: str) -> str:
        self._record("get_email_body", email_id=email_id)
        return (
            f"From: sender@example.com\n"
            f"To: ssswindy2@gmail.com\n"
            f"Subject: Subject for {email_id}\n"
            f"Date: Fri, 18 Apr 2026 09:10:00 +0000\n"
            "\n--- Email Body ---\n\n"
            f"Full body for {email_id}"
        )


def make_noop_skill_finalizer() -> FakeAgent:
    return FakeAgent(['{"final_response":"should not be used","reason":"noop"}'], name="skill-finalizer")


def test_split_context_respects_window_limits():
    dialogue = [DialogueItem(role="user" if index % 2 == 0 else "assistant", content=f"message {index}") for index in range(60)]

    older, recent = split_context(dialogue)

    assert len(older) == 40
    assert len(recent) == 10
    assert older[0].content == "message 10"
    assert older[-1].content == "message 49"
    assert recent[0].content == "message 50"
    assert recent[-1].content == "message 59"


def test_load_skill_registry_parses_yaml_shape(tmp_path: Path):
    registry = tmp_path / "registry.yaml"
    registry.write_text(
        "\n".join(
            [
                "skills:",
                "  - name: compose_email_from_context",
                "    description: Draft an email from mailbox context",
                "    scope: Can only draft, never send",
                "    used_tools:",
                "      - search_emails",
                "      - read_memory",
                "    input_schema:",
                "      days:",
                "        type: int",
                "        required: false",
                "        default: 7",
                "        description: Number of recent days to inspect",
                "    output: email_draft",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    skills = load_skill_registry(registry)

    assert len(skills) == 1
    assert skills[0].name == "compose_email_from_context"
    assert skills[0].used_tools == ("search_emails", "read_memory")
    assert skills[0].input_schema == (
        SkillInputFieldSpec(
            name="days",
            field_type="int",
            required=False,
            description="Number of recent days to inspect",
            has_default=True,
            default=7,
        ),
    )


def test_orchestrator_direct_response_skips_main_agent(tmp_path: Path):
    main_agent = FakeAgent(["should not be used"], name="main-agent", max_iterations=15)
    intent_agent = FakeAgent(
        [
            json.dumps(
                {
                    "intent": "Answer a simple acknowledgement directly.",
                    "no_execution_confidence": 9,
                    "final_response": "Sure, that works.",
                    "reason": "The user only needs a lightweight confirmation.",
                    "user_update_summary": "No meaningful update.",
                }
            )
        ]
    )
    selector_agent = FakeAgent(["should not be used"])
    writer_agent = FakeAgent(
        [
            json.dumps(
                {
                    "should_update": False,
                    "profile_markdown": None,
                    "habits_markdown": None,
                    "reason": "Nothing new to store.",
                }
            )
        ]
    )

    store = MarkdownMemoryStore(
        profile_path=tmp_path / "USER_PROFILE.md",
        habits_path=tmp_path / "USER_HABITS.md",
        writer_agent=writer_agent,
    )
    orchestrator = IntentLayerOrchestrator(
        main_agent=main_agent,
        intent_agent=intent_agent,
        skill_selector_agent=selector_agent,
        skill_finalizer_agent=make_noop_skill_finalizer(),
        skill_executor=None,
        memory_store=store,
        skill_registry_path=tmp_path / "registry.yaml",
    )

    result = orchestrator.input("ok")

    assert result == "Sure, that works."
    assert len(main_agent.calls) == 0
    assert len(selector_agent.calls) == 0


def test_orchestrator_raises_when_intent_layer_llm_output_is_invalid(tmp_path: Path):
    main_agent = FakeAgent(["should not run"], name="main-agent", max_iterations=15)
    intent_agent = FakeAgent(["not json at all"])
    selector_agent = FakeAgent(["should not run"])
    writer_agent = FakeAgent(
        [
            json.dumps(
                {
                    "should_update": False,
                    "profile_markdown": None,
                    "habits_markdown": None,
                    "reason": "Nothing new to store.",
                }
            )
        ]
    )

    store = MarkdownMemoryStore(
        profile_path=tmp_path / "USER_PROFILE.md",
        habits_path=tmp_path / "USER_HABITS.md",
        writer_agent=writer_agent,
    )
    orchestrator = IntentLayerOrchestrator(
        main_agent=main_agent,
        intent_agent=intent_agent,
        skill_selector_agent=selector_agent,
        skill_finalizer_agent=make_noop_skill_finalizer(),
        skill_executor=None,
        memory_store=store,
        skill_registry_path=tmp_path / "registry.yaml",
    )

    try:
        orchestrator.input("Draft a reply.")
        raise AssertionError("Expected IntentLayerError to be raised.")
    except IntentLayerError:
        pass

    assert len(main_agent.calls) == 0


def test_orchestrator_handoff_to_main_agent_and_updates_user_files(tmp_path: Path):
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text("skills: []\n", encoding="utf-8")

    main_agent = FakeAgent(["Drafted response from main agent."], name="main-agent", max_iterations=15)
    intent_agent = FakeAgent(
        [
            json.dumps(
                {
                    "intent": "Draft a reply to the user's email request.",
                    "no_execution_confidence": 4,
                    "final_response": None,
                    "reason": "The request needs downstream execution.",
                    "user_update_summary": "The user prefers concise email drafts.",
                }
            )
        ]
    )
    selector_agent = FakeAgent(["should not be called because registry is empty"])
    writer_agent = FakeAgent(
        [
            json.dumps(
                {
                    "should_update": True,
                    "profile_markdown": "# User Profile\n\n- Works on email-heavy tasks.",
                    "habits_markdown": "# User Habits\n\n- Prefers concise email drafts.",
                    "reason": "Stored the newly observed drafting preference.",
                }
            )
        ]
    )

    store = MarkdownMemoryStore(
        profile_path=tmp_path / "USER_PROFILE.md",
        habits_path=tmp_path / "USER_HABITS.md",
        writer_agent=writer_agent,
    )
    orchestrator = IntentLayerOrchestrator(
        main_agent=main_agent,
        intent_agent=intent_agent,
        skill_selector_agent=selector_agent,
        skill_finalizer_agent=make_noop_skill_finalizer(),
        skill_executor=None,
        memory_store=store,
        skill_registry_path=registry_path,
    )

    result = orchestrator.input("Help me reply to this customer email.", max_iterations=7)

    assert result == "Drafted response from main agent."
    assert len(main_agent.calls) == 1
    handoff_prompt, forwarded_max_iterations, _, _, _ = main_agent.calls[0]
    assert "[INTENT_LAYER_HANDOFF]" in handoff_prompt
    assert "intent: Draft a reply to the user's email request." in handoff_prompt
    assert "skill_selector: route to main agent" in handoff_prompt
    assert forwarded_max_iterations == 7
    assert selector_agent.calls == []
    assert "Prefers concise email drafts" in (tmp_path / "USER_HABITS.md").read_text(encoding="utf-8")


def test_orchestrator_accepts_host_signature_and_forwards_session_payloads(tmp_path: Path):
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text("skills: []\n", encoding="utf-8")

    session = {"session_id": "sess-123"}
    images = ["data:image/png;base64,abc"]
    files = [{"name": "note.txt", "type": "text/plain"}]

    main_agent = FakeAgent(["Main agent handled the request."], name="main-agent", max_iterations=15)
    intent_agent = FakeAgent(
        [
            json.dumps(
                {
                    "intent": "Handle the request with the main agent.",
                    "no_execution_confidence": 2,
                    "final_response": None,
                    "reason": "Needs downstream execution.",
                    "user_update_summary": "No meaningful update.",
                }
            )
        ]
    )
    selector_agent = FakeAgent(["should not be called because registry is empty"])
    writer_agent = FakeAgent(
        [
            json.dumps(
                {
                    "should_update": False,
                    "profile_markdown": None,
                    "habits_markdown": None,
                    "reason": "Nothing new to store.",
                }
            )
        ]
    )

    store = MarkdownMemoryStore(
        profile_path=tmp_path / "USER_PROFILE.md",
        habits_path=tmp_path / "USER_HABITS.md",
        writer_agent=writer_agent,
    )
    orchestrator = IntentLayerOrchestrator(
        main_agent=main_agent,
        intent_agent=intent_agent,
        skill_selector_agent=selector_agent,
        skill_finalizer_agent=make_noop_skill_finalizer(),
        skill_executor=None,
        memory_store=store,
        skill_registry_path=registry_path,
    )

    result = orchestrator.input(
        "Please handle this request.",
        session=session,
        images=images,
        files=files,
    )

    assert result == "Main agent handled the request."
    assert orchestrator.current_session == session
    handoff_prompt, _, forwarded_session, forwarded_images, forwarded_files = main_agent.calls[0]
    assert "[USER_MESSAGE]" in handoff_prompt
    assert forwarded_session == session
    assert forwarded_images == images
    assert forwarded_files == files


def test_orchestrator_persists_dialogue_across_new_session_dicts_with_same_session_id(tmp_path: Path):
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text("skills: []\n", encoding="utf-8")

    session_one = {"session_id": "sess-123"}
    session_two = {"session_id": "sess-123"}

    main_agent = FakeAgent(
        [
            "Main agent handled the first request.",
            "Main agent handled the follow-up request.",
        ],
        name="main-agent",
        max_iterations=15,
    )
    intent_agent = FakeAgent(
        [
            json.dumps(
                {
                    "intent": "Handle the first request with the main agent.",
                    "no_execution_confidence": 2,
                    "final_response": None,
                    "reason": "Needs downstream execution.",
                    "user_update_summary": "No meaningful update.",
                }
            ),
            json.dumps(
                {
                    "intent": "Handle the follow-up request with the main agent.",
                    "no_execution_confidence": 2,
                    "final_response": None,
                    "reason": "Needs downstream execution.",
                    "user_update_summary": "No meaningful update.",
                }
            ),
        ]
    )
    selector_agent = FakeAgent(["should not be called because registry is empty", "should not be called because registry is empty"])
    writer_agent = FakeAgent(
        [
            json.dumps(
                {
                    "should_update": False,
                    "profile_markdown": None,
                    "habits_markdown": None,
                    "reason": "Nothing new to store.",
                }
            ),
            json.dumps(
                {
                    "should_update": False,
                    "profile_markdown": None,
                    "habits_markdown": None,
                    "reason": "Nothing new to store.",
                }
            ),
        ]
    )

    store = MarkdownMemoryStore(
        profile_path=tmp_path / "USER_PROFILE.md",
        habits_path=tmp_path / "USER_HABITS.md",
        writer_agent=writer_agent,
    )
    orchestrator = IntentLayerOrchestrator(
        main_agent=main_agent,
        intent_agent=intent_agent,
        skill_selector_agent=selector_agent,
        skill_finalizer_agent=make_noop_skill_finalizer(),
        skill_executor=None,
        memory_store=store,
        skill_registry_path=registry_path,
    )

    first_result = orchestrator.input("First request.", session=session_one)
    second_result = orchestrator.input("Follow-up request.", session=session_two)

    assert first_result == "Main agent handled the first request."
    assert second_result == "Main agent handled the follow-up request."
    second_intent_prompt, _, _, _, _ = intent_agent.calls[1]
    assert "[RECENT_CONTEXT]" in second_intent_prompt
    assert "User: First request." in second_intent_prompt
    assert "Assistant: Main agent handled the first request." in second_intent_prompt


def test_orchestrator_logs_confidence_for_non_direct_routes(tmp_path: Path):
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text("skills: []\n", encoding="utf-8")

    main_agent = FakeAgent(["Main agent handled the request."], name="main-agent", max_iterations=15)
    intent_agent = FakeAgent(
        [
            json.dumps(
                {
                    "intent": "Handle this request with downstream execution.",
                    "no_execution_confidence": 3,
                    "final_response": None,
                    "reason": "Needs tools.",
                    "user_update_summary": "No meaningful update.",
                }
            )
        ]
    )
    selector_agent = FakeAgent(["should not be called because registry is empty"])
    writer_agent = FakeAgent(
        [
            json.dumps(
                {
                    "should_update": False,
                    "profile_markdown": None,
                    "habits_markdown": None,
                    "reason": "Nothing new to store.",
                }
            )
        ]
    )

    store = MarkdownMemoryStore(
        profile_path=tmp_path / "USER_PROFILE.md",
        habits_path=tmp_path / "USER_HABITS.md",
        writer_agent=writer_agent,
    )
    orchestrator = IntentLayerOrchestrator(
        main_agent=main_agent,
        intent_agent=intent_agent,
        skill_selector_agent=selector_agent,
        skill_finalizer_agent=make_noop_skill_finalizer(),
        skill_executor=None,
        memory_store=store,
        skill_registry_path=registry_path,
    )

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        result = orchestrator.input("Please handle this request.", session={"session_id": "sess-456"})

    log_output = stdout.getvalue()
    assert result == "Main agent handled the request."
    assert '"event": "skill_selection"' in log_output
    assert '"confidence": 3.0' in log_output
    assert '"skill_selected": false' in log_output
    assert '"selected_skill": "(none)"' in log_output
    assert '"event": "main_agent"' in log_output
    assert '"event": "memory_update"' in log_output


def test_orchestrator_returns_selected_skill_response_without_main_agent(tmp_path: Path):
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(
        "\n".join(
            [
                "skills:",
                "  - name: compose_email_from_context",
                "    description: Draft an email from mailbox context",
                "    scope: Can only draft, never send",
                "    used_tools:",
                "      - search_emails",
                "    output: email_draft",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    main_agent = FakeAgent(["should not run"], name="main-agent", max_iterations=15)
    intent_agent = FakeAgent(
        [
            json.dumps(
                {
                    "intent": "Draft an email reply from existing mailbox context.",
                    "no_execution_confidence": 3,
                    "final_response": None,
                    "reason": "This needs a drafting workflow.",
                    "user_update_summary": "No meaningful update.",
                }
            )
        ]
    )
    selector_agent = FakeAgent(
        [
            json.dumps(
                {
                    "should_use_skill": True,
                    "skill_name": "compose_email_from_context",
                    "skill_arguments": {},
                    "reason": "This request fits the drafting fast path.",
                }
            )
        ]
    )
    writer_agent = FakeAgent(
        [
            json.dumps(
                {
                    "should_update": False,
                    "profile_markdown": None,
                    "habits_markdown": None,
                    "reason": "Nothing new to store.",
                }
            )
        ]
    )
    skill_finalizer_agent = FakeAgent(
        [
            json.dumps(
                {
                    "final_response": "我已经整理好一版可以直接发给用户的草稿：\n\nHere is a concise draft you can send.",
                    "reason": "The skill already produced a usable draft, so I only reframed it for the user.",
                }
            )
        ],
        name="skill-finalizer",
    )
    skill_executor = FakeSkillExecutor(
        SkillExecutionResult(
            attempted=True,
            completed=True,
            response="Here is a concise draft you can send.",
            reason="Skill completed the drafting request.",
        )
    )

    store = MarkdownMemoryStore(
        profile_path=tmp_path / "USER_PROFILE.md",
        habits_path=tmp_path / "USER_HABITS.md",
        writer_agent=writer_agent,
    )
    orchestrator = IntentLayerOrchestrator(
        main_agent=main_agent,
        intent_agent=intent_agent,
        skill_selector_agent=selector_agent,
        skill_finalizer_agent=skill_finalizer_agent,
        skill_executor=skill_executor,
        memory_store=store,
        skill_registry_path=registry_path,
    )

    result = orchestrator.input("Draft a reply to the client.", max_iterations=6)

    assert result == "我已经整理好一版可以直接发给用户的草稿：\n\nHere is a concise draft you can send."
    assert len(main_agent.calls) == 0
    assert len(skill_executor.calls) == 1
    assert len(skill_finalizer_agent.calls) == 1
    finalizer_prompt, finalizer_max_iterations, _, _, _ = skill_finalizer_agent.calls[0]
    assert "[INTENT]" in finalizer_prompt
    assert "[RECENT_CONTEXT]" in finalizer_prompt
    assert "[SELECTED_SKILL]" in finalizer_prompt
    assert "[SKILL_RESULT]" in finalizer_prompt
    assert "Draft an email reply from existing mailbox context." in finalizer_prompt
    assert "skill_name: compose_email_from_context" in finalizer_prompt
    assert "Can only draft, never send" in finalizer_prompt
    assert "Here is a concise draft you can send." in finalizer_prompt
    assert "[USER_MESSAGE]" not in finalizer_prompt
    assert finalizer_max_iterations == 1
    executed_skill, skill_arguments, current_message, intent_text, _, forwarded_max_iterations = skill_executor.calls[0]
    assert executed_skill.name == "compose_email_from_context"
    assert skill_arguments == {}
    assert current_message == "Draft a reply to the client."
    assert intent_text == "Draft an email reply from existing mailbox context."
    assert forwarded_max_iterations == 6


def test_orchestrator_raises_when_skill_finalizer_llm_output_is_invalid(tmp_path: Path):
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(
        "\n".join(
            [
                "skills:",
                "  - name: compose_email_from_context",
                "    description: Draft an email from mailbox context",
                "    scope: Can only draft, never send",
                "    used_tools:",
                "      - search_emails",
                "    output: email_draft",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    main_agent = FakeAgent(["should not run"], name="main-agent", max_iterations=15)
    intent_agent = FakeAgent(
        [
            json.dumps(
                {
                    "intent": "Draft an email reply from existing mailbox context.",
                    "no_execution_confidence": 3,
                    "final_response": None,
                    "reason": "This needs a drafting workflow.",
                    "user_update_summary": "No meaningful update.",
                }
            )
        ]
    )
    selector_agent = FakeAgent(
        [
            json.dumps(
                {
                    "should_use_skill": True,
                    "skill_name": "compose_email_from_context",
                    "skill_arguments": {},
                    "reason": "This request fits the drafting fast path.",
                }
            )
        ]
    )
    writer_agent = FakeAgent(
        [
            json.dumps(
                {
                    "should_update": False,
                    "profile_markdown": None,
                    "habits_markdown": None,
                    "reason": "Nothing new to store.",
                }
            )
        ]
    )
    skill_finalizer_agent = FakeAgent(["not valid json"], name="skill-finalizer")
    skill_executor = FakeSkillExecutor(
        SkillExecutionResult(
            attempted=True,
            completed=True,
            response="Here is a concise draft you can send.",
            reason="Skill completed the drafting request.",
        )
    )

    store = MarkdownMemoryStore(
        profile_path=tmp_path / "USER_PROFILE.md",
        habits_path=tmp_path / "USER_HABITS.md",
        writer_agent=writer_agent,
    )
    orchestrator = IntentLayerOrchestrator(
        main_agent=main_agent,
        intent_agent=intent_agent,
        skill_selector_agent=selector_agent,
        skill_finalizer_agent=skill_finalizer_agent,
        skill_executor=skill_executor,
        memory_store=store,
        skill_registry_path=registry_path,
    )

    try:
        orchestrator.input("Draft a reply to the client.")
        raise AssertionError("Expected SkillLayerError to be raised.")
    except SkillLayerError:
        pass

    assert len(main_agent.calls) == 0


def test_orchestrator_falls_back_to_main_agent_when_skill_cannot_complete(tmp_path: Path):
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(
        "\n".join(
            [
                "skills:",
                "  - name: compose_email_from_context",
                "    description: Draft an email from mailbox context",
                "    scope: Can only draft, never send",
                "    used_tools:",
                "      - search_emails",
                "    output: email_draft",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    main_agent = FakeAgent(["main-agent fallback response"], name="main-agent", max_iterations=15)
    intent_agent = FakeAgent(
        [
            json.dumps(
                {
                    "intent": "Draft an email reply from existing mailbox context.",
                    "no_execution_confidence": 2,
                    "final_response": None,
                    "reason": "This needs downstream execution.",
                    "user_update_summary": "No meaningful update.",
                }
            )
        ]
    )
    selector_agent = FakeAgent(
        [
            json.dumps(
                {
                    "should_use_skill": True,
                    "skill_name": "compose_email_from_context",
                    "skill_arguments": {},
                    "reason": "This request fits the drafting fast path.",
                }
            )
        ]
    )
    writer_agent = FakeAgent(
        [
            json.dumps(
                {
                    "should_update": False,
                    "profile_markdown": None,
                    "habits_markdown": None,
                    "reason": "Nothing new to store.",
                }
            )
        ]
    )
    skill_executor = FakeSkillExecutor(
        SkillExecutionResult(
            attempted=True,
            completed=False,
            response=None,
            reason="The restricted skill lacked enough mailbox context to finish.",
        )
    )

    store = MarkdownMemoryStore(
        profile_path=tmp_path / "USER_PROFILE.md",
        habits_path=tmp_path / "USER_HABITS.md",
        writer_agent=writer_agent,
    )
    orchestrator = IntentLayerOrchestrator(
        main_agent=main_agent,
        intent_agent=intent_agent,
        skill_selector_agent=selector_agent,
        skill_finalizer_agent=make_noop_skill_finalizer(),
        skill_executor=skill_executor,
        memory_store=store,
        skill_registry_path=registry_path,
    )

    result = orchestrator.input("Draft a reply to the client.")

    assert result == "main-agent fallback response"
    assert len(main_agent.calls) == 1
    handoff_prompt, _, _, _, _ = main_agent.calls[0]
    assert "skill_selector: use compose_email_from_context" in handoff_prompt
    assert 'skill_selector_arguments: {}' in handoff_prompt
    assert "skill_completed: False" in handoff_prompt
    assert "The restricted skill lacked enough mailbox context to finish." in handoff_prompt


def test_orchestrator_raises_when_skill_selector_llm_output_is_invalid(tmp_path: Path):
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(
        "\n".join(
            [
                "skills:",
                "  - name: compose_email_from_context",
                "    description: Draft an email from mailbox context",
                "    scope: Can only draft, never send",
                "    used_tools:",
                "      - search_emails",
                "    output: email_draft",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    main_agent = FakeAgent(["should not run"], name="main-agent", max_iterations=15)
    intent_agent = FakeAgent(
        [
            json.dumps(
                {
                    "intent": "Draft an email reply from existing mailbox context.",
                    "no_execution_confidence": 2,
                    "final_response": None,
                    "reason": "This needs downstream execution.",
                    "user_update_summary": "No meaningful update.",
                }
            )
        ]
    )
    selector_agent = FakeAgent(["this is not valid json"])
    writer_agent = FakeAgent(
        [
            json.dumps(
                {
                    "should_update": False,
                    "profile_markdown": None,
                    "habits_markdown": None,
                    "reason": "Nothing new to store.",
                }
            )
        ]
    )

    store = MarkdownMemoryStore(
        profile_path=tmp_path / "USER_PROFILE.md",
        habits_path=tmp_path / "USER_HABITS.md",
        writer_agent=writer_agent,
    )
    orchestrator = IntentLayerOrchestrator(
        main_agent=main_agent,
        intent_agent=intent_agent,
        skill_selector_agent=selector_agent,
        skill_finalizer_agent=make_noop_skill_finalizer(),
        skill_executor=None,
        memory_store=store,
        skill_registry_path=registry_path,
    )

    try:
        orchestrator.input("Draft a reply to the client.")
        raise AssertionError("Expected SkillLayerError to be raised.")
    except SkillLayerError:
        pass

    assert len(main_agent.calls) == 0


def test_python_skill_executor_runs_selected_python_skill_file(tmp_path: Path):
    toolbox = ToolBox()
    tool_function_map = build_tool_function_map([toolbox])
    skill_file = tmp_path / "compose_email_from_context.py"
    skill_file.write_text(
        "\n".join(
            [
                "def execute_skill(*, arguments, used_tools, skill_spec):",
                "    result = used_tools['search_emails'](query=arguments['query'])",
                "    return {",
                "        'completed': True,",
                "        'response': f\"Skill response: {result} / days={arguments['days']}\",",
                "        'reason': f\"Used {skill_spec['name']} directly.\",",
                "    }",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    executor = PythonSkillExecutor(
        skills_directory=tmp_path,
        tool_function_map=tool_function_map,
    )

    result = executor.run(
        SkillSpec(
            name="compose_email_from_context",
            description="Draft an email",
            scope="Can only draft, never send",
            used_tools=("search_emails",),
            output="email_draft",
            input_schema=(
                SkillInputFieldSpec(
                    name="query",
                    field_type="string",
                    required=True,
                    description="Mailbox query to pass into search_emails",
                ),
                SkillInputFieldSpec(
                    name="days",
                    field_type="int",
                    required=False,
                    description="Number of days to inspect",
                    has_default=True,
                    default=7,
                ),
            ),
        ),
        skill_arguments={"query": "Draft a reply."},
        current_message="Draft a reply.",
        intent_decision=type(
            "IntentDecisionLike",
            (),
            {"intent": "Draft an email reply from mailbox context."},
        )(),
        recent_context=[],
    )

    assert result.completed is True
    assert result.response == "Skill response: search:Draft a reply. / days=7"


def test_python_skill_executor_fails_when_used_tool_is_missing(tmp_path: Path):
    executor = PythonSkillExecutor(
        skills_directory=tmp_path,
        tool_function_map={},
    )

    result = executor.run(
        SkillSpec(
            name="compose_email_from_context",
            description="Draft an email",
            scope="Can only draft, never send",
            used_tools=("search_emails",),
            output="email_draft",
        ),
        skill_arguments={},
        current_message="Draft a reply.",
        intent_decision=type(
            "IntentDecisionLike",
            (),
            {"intent": "Draft an email reply from mailbox context."},
        )(),
        recent_context=[],
    )

    assert result.completed is False
    assert "search_emails" in result.reason


def test_python_skill_executor_raises_when_skill_output_is_invalid(tmp_path: Path):
    skill_file = tmp_path / "compose_email_from_context.py"
    skill_file.write_text(
        "\n".join(
            [
                "def execute_skill(*, arguments, used_tools, skill_spec):",
                "    return 'not a dict'",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    executor = PythonSkillExecutor(
        skills_directory=tmp_path,
        tool_function_map={"search_emails": lambda query: f"search:{query}"},
    )

    try:
        executor.run(
            SkillSpec(
                name="compose_email_from_context",
                description="Draft an email",
                scope="Can only draft, never send",
                used_tools=("search_emails",),
                output="email_draft",
            ),
            skill_arguments={},
            current_message="Draft a reply.",
            intent_decision=type(
                "IntentDecisionLike",
                (),
                {"intent": "Draft an email reply from mailbox context."},
            )(),
            recent_context=[],
        )
        raise AssertionError("Expected SkillLayerError to be raised.")
    except SkillLayerError:
        pass


def test_weekly_email_summary_skill_uses_fixed_workflow(repo_root: Path | None = None):
    del repo_root
    toolbox = WeeklySummaryToolBox()
    tool_function_map = build_tool_function_map([toolbox])
    skills_directory = Path(__file__).resolve().parent.parent / "skills"

    executor = PythonSkillExecutor(
        skills_directory=skills_directory,
        tool_function_map=tool_function_map,
    )

    result = executor.run(
        SkillSpec(
            name="weekly_email_summary",
            description="Summarize recent email activity for a recent time window using mailbox identity, inbox, unanswered, and calendar context.",
            scope="Read-only weekly summary workflow. Never send email and never modify mailbox state.",
            used_tools=("get_my_identity", "search_emails", "get_unanswered_emails", "list_events"),
            output="A user-facing weekly email summary grounded only in the collected identity, inbox, unanswered, and calendar tool results.",
            input_schema=(
                SkillInputFieldSpec(
                    name="days",
                    field_type="int",
                    required=False,
                    description="Number of recent days to summarize.",
                    has_default=True,
                    default=7,
                ),
            ),
        ),
        skill_arguments={"days": 3},
        current_message="总结最近3天邮件",
        intent_decision=type(
            "IntentDecisionLike",
            (),
            {"intent": "用户想让我按最近3天的邮件范围进行总结。"},
        )(),
        recent_context=[],
    )

    assert result.completed is True
    assert "[WEEKLY_EMAIL_SUMMARY_BUNDLE]" in result.response
    assert "search_query: newer_than:3d" in result.response
    assert "[GET_MY_IDENTITY]" in result.response
    assert "[SEARCH_EMAILS]" in result.response
    assert "[GET_UNANSWERED_EMAILS]" in result.response
    assert "[LIST_EVENTS]" in result.response

    calls_by_name = {name: kwargs for name, kwargs in toolbox.calls}
    assert calls_by_name["get_my_identity"] == {}
    assert calls_by_name["search_emails"] == {"query": "newer_than:3d", "max_results": 350}
    assert calls_by_name["get_unanswered_emails"] == {"within_days": 3, "max_results": 50}
    assert calls_by_name["list_events"] == {"days_ahead": 3, "max_results": 20}


def test_writing_style_profile_skill_creates_and_updates_markdown(tmp_path: Path):
    toolbox = WritingStyleToolBox()
    writer_agent = FakeAgent(
        [
            json.dumps(
                {
                    "writing_style_markdown": (
                        "# Writing Style\n\n"
                        "## Snapshot\n\n"
                        "- Friendly and concise.\n\n"
                        "## Subject Lines\n\n"
                        "- Often short and direct.\n"
                    ),
                    "user_summary": "I extracted a concise, friendly writing style profile from your most recent sent emails.",
                    "reason": "Created an initial writing style profile from recent sent emails.",
                }
            ),
            json.dumps(
                {
                    "writing_style_markdown": (
                        "# Writing Style\n\n"
                        "## Snapshot\n\n"
                        "- Friendly, concise, and comfortable mixing Chinese and English.\n\n"
                        "## Subject Lines\n\n"
                        "- Often short and direct.\n\n"
                        "## Language Usage\n\n"
                        "- Mixes English scheduling phrases with Chinese outreach naturally.\n"
                    ),
                    "user_summary": "I added your mixed-language habits and meeting-outreach patterns on top of the existing profile.",
                    "reason": "Updated the profile using the existing markdown plus the latest sent email evidence.",
                }
            ),
        ],
        name="writing-style-writer",
    )
    skills_directory = Path(__file__).resolve().parent.parent / "skills"
    writing_style_path = tmp_path / "WRITING_STYLE.md"

    executor = PythonSkillExecutor(
        skills_directory=skills_directory,
        tool_function_map=build_tool_function_map([toolbox]),
        skill_runtime={
            "agents": {
                "writing_style_writer": writer_agent,
            },
            "paths": {
                "writing_style_markdown": writing_style_path,
            },
        },
    )

    skill_spec = SkillSpec(
        name="writing_style_profile",
        description="Build or update a persistent writing style profile from the user's recent sent emails.",
        scope="Read recent sent emails and update the local writing style markdown only. Never send email and never modify mailbox state beyond WRITING_STYLE.md.",
        used_tools=("get_sent_emails",),
        output="A user-facing confirmation plus the updated WRITING_STYLE markdown derived from recent sent emails.",
    )

    first_result = executor.run(
        skill_spec,
        skill_arguments={},
        current_message="总结我的写作风格",
        intent_decision=type(
            "IntentDecisionLike",
            (),
            {"intent": "用户想根据最近发送的邮件建立写作风格档案。"},
        )(),
        recent_context=[],
    )

    assert first_result.completed is True
    assert writing_style_path.exists()
    assert "[WRITING_STYLE_PROFILE_UPDATED]" in first_result.response
    assert "action: created" in first_result.response
    assert "[WRITING_STYLE_MARKDOWN]" in first_result.response
    first_markdown = writing_style_path.read_text(encoding="utf-8")
    assert "Friendly and concise." in first_markdown

    first_prompt, _, _, _, _ = writer_agent.calls[0]
    assert "[CURRENT_WRITING_STYLE]" in first_prompt
    assert "No writing style profile yet." in first_prompt
    assert "[RECENT_SENT_EMAILS]" in first_prompt
    assert "Coffee Chat Tomorrow at 3 PM" in first_prompt

    second_result = executor.run(
        skill_spec,
        skill_arguments={},
        current_message="再更新一下我的写作风格",
        intent_decision=type(
            "IntentDecisionLike",
            (),
            {"intent": "用户想在已有写作风格档案基础上继续更新。"},
        )(),
        recent_context=[],
    )

    assert second_result.completed is True
    assert "action: updated" in second_result.response
    second_markdown = writing_style_path.read_text(encoding="utf-8")
    assert "comfortable mixing Chinese and English" in second_markdown

    second_prompt, _, _, _, _ = writer_agent.calls[1]
    assert "Friendly and concise." in second_prompt
    assert "Coffee Chat Tomorrow at 3 PM" in second_prompt
    assert "Everything you write must be in English." not in second_prompt

    calls_by_name = {name: kwargs for name, kwargs in toolbox.calls}
    assert calls_by_name["get_sent_emails"] == {"max_results": 30}


def test_urgent_email_triage_skill_uses_fixed_workflow(repo_root: Path | None = None):
    del repo_root
    toolbox = UrgentEmailToolBox()
    tool_function_map = build_tool_function_map([toolbox])
    skills_directory = Path(__file__).resolve().parent.parent / "skills"

    executor = PythonSkillExecutor(
        skills_directory=skills_directory,
        tool_function_map=tool_function_map,
    )

    result = executor.run(
        SkillSpec(
            name="urgent_email_triage",
            description="Find recent inbox emails that look urgent, need attention, or appear high-priority, add unanswered-thread context, and fetch full bodies for both matched urgent emails and unresolved unanswered emails.",
            scope="Read-only urgent-email triage workflow. Never send email and never modify mailbox state.",
            used_tools=("search_emails", "get_unanswered_emails", "get_email_body"),
            output="A user-facing triage of recent inbox emails that look urgent, need attention, or appear high-priority, grounded only in keyword search hits, unanswered-thread context, and the fetched full bodies of matched urgent and unresolved unanswered emails.",
            input_schema=(
                SkillInputFieldSpec(
                    name="days",
                    field_type="int",
                    required=False,
                    description="Number of recent days to inspect for urgent, attention-needed, or high-priority emails.",
                    has_default=True,
                    default=7,
                ),
            ),
        ),
        skill_arguments={"days": 10},
        current_message="看看最近10天有没有紧急邮件",
        intent_decision=type(
            "IntentDecisionLike",
            (),
            {"intent": "用户想让我查找最近10天的紧急或高优先级邮件。"},
        )(),
        recent_context=[],
    )

    assert result.completed is True
    assert "[URGENT_EMAIL_TRIAGE_BUNDLE]" in result.response
    assert "search_query: in:inbox newer_than:7d" in result.response
    assert "max_lookback_days: 7" in result.response
    assert "[SEARCH_EMAILS]" in result.response
    assert "[GET_UNANSWERED_EMAILS]" in result.response
    assert "[MATCHED_URGENT_EMAIL_IDS]" in result.response
    assert "[EMAIL_BODY_RESULTS]" in result.response
    assert "[EMAIL_BODY_1]" in result.response
    assert "[EMAIL_BODY_3]" in result.response
    assert "[UNANSWERED_EMAIL_ID_LOOKUPS]" in result.response
    assert "[UNANSWERED_LOOKUP_1]" in result.response
    assert "[UNANSWERED_EMAIL_BODY_RESULTS]" in result.response
    assert "[UNANSWERED_EMAIL_BODY_1]" in result.response
    assert "urgent-001, urgent-002, urgent-003" in result.response
    assert "matched_email_id: unanswered-001" in result.response

    expected_query = (
        'in:inbox newer_than:7d (urgent OR asap OR immediately OR important OR critical OR priority OR attention OR '
        '"high priority" OR "needs attention" OR "for your attention" OR "attention required" OR "requires attention" OR '
        '"action required" OR "immediate action" OR "response needed" OR "please respond" OR "for your review" OR '
        '"review needed" OR "time sensitive" OR "urgent response" OR deadline OR overdue OR reminder OR '
        '"final notice" OR alert OR "security alert")'
    )
    assert toolbox.calls[0] == ("search_emails", {"query": expected_query, "max_results": 350})
    assert toolbox.calls[1] == ("get_unanswered_emails", {"within_days": 7, "max_results": 30})
    assert toolbox.calls[2] == (
        "get_email_body",
        {"email_id": "urgent-001"},
    )
    assert toolbox.calls[3] == (
        "get_email_body",
        {"email_id": "urgent-002"},
    )
    assert toolbox.calls[4] == (
        "get_email_body",
        {"email_id": "urgent-003"},
    )
    assert toolbox.calls[5] == (
        "search_emails",
        {
            "query": 'in:inbox newer_than:7d from:founder@example.com subject:"urgent deadline update"',
            "max_results": 1,
        },
    )
    assert toolbox.calls[6:] == [
        ("get_email_body", {"email_id": "unanswered-001"}),
    ]


def test_bug_issue_triage_skill_uses_fixed_workflow(repo_root: Path | None = None):
    del repo_root
    toolbox = BugIssueToolBox()
    tool_function_map = build_tool_function_map([toolbox])
    skills_directory = Path(__file__).resolve().parent.parent / "skills"

    executor = PythonSkillExecutor(
        skills_directory=skills_directory,
        tool_function_map=tool_function_map,
    )

    result = executor.run(
        SkillSpec(
            name="bug_issue_triage",
            description="Find recent inbox emails, notifications, or task-record messages that look bug-related, such as build failures, issue openings, failing tests, regressions, incidents, or broken workflows, and fetch the full body of every matched email.",
            scope="Read-only bug triage workflow. Never send email and never modify mailbox state.",
            used_tools=("search_emails", "get_email_body"),
            output="A user-facing prioritized bug triage grounded only in keyword search hits and the fetched full bodies of every matched email.",
            input_schema=(
                SkillInputFieldSpec(
                    name="days",
                    field_type="int",
                    required=False,
                    description="Number of recent days to inspect for bug-related or engineering-problem emails.",
                    has_default=True,
                    default=7,
                ),
            ),
        ),
        skill_arguments={"days": 10},
        current_message="帮我整理最近10天要处理的 bug 事项",
        intent_decision=type(
            "IntentDecisionLike",
            (),
            {"intent": "用户想让我从最近邮件中整理出需要优先处理的 bug 相关事项。"},
        )(),
        recent_context=[],
    )

    assert result.completed is True
    assert "[BUG_ISSUE_TRIAGE_BUNDLE]" in result.response
    assert "search_query: in:inbox newer_than:7d" in result.response
    assert "max_lookback_days: 7" in result.response
    assert "[SEARCH_EMAILS]" in result.response
    assert "[MATCHED_BUG_EMAIL_IDS]" in result.response
    assert "[EMAIL_BODY_RESULTS]" in result.response
    assert "[EMAIL_BODY_1]" in result.response
    assert "[EMAIL_BODY_3]" in result.response
    assert "Finalizer instruction: rank the resulting bug items from highest priority to lowest priority before presenting them to the user." in result.response
    assert "bug-001, bug-002, bug-003" in result.response

    expected_query = (
        'in:inbox newer_than:7d (bug OR bugs OR defect OR regression OR "build failed" OR "build failure" OR '
        '"failing tests" OR "tests failed" OR "test failed" OR "ci failed" OR "pipeline failed" OR "issue opened" OR '
        '"incident opened" OR "production issue" OR "prod issue" OR incident OR outage OR broken OR failure OR blocker OR '
        '"error report")'
    )
    assert toolbox.calls == [
        ("search_emails", {"query": expected_query, "max_results": 350}),
        ("get_email_body", {"email_id": "bug-001"}),
        ("get_email_body", {"email_id": "bug-002"}),
        ("get_email_body", {"email_id": "bug-003"}),
    ]


def test_resume_candidate_review_skill_uses_fixed_workflow(repo_root: Path | None = None):
    del repo_root
    toolbox = ResumeCandidateToolBox()
    tool_function_map = build_tool_function_map([toolbox])
    skills_directory = Path(__file__).resolve().parent.parent / "skills"

    executor = PythonSkillExecutor(
        skills_directory=skills_directory,
        tool_function_map=tool_function_map,
    )

    result = executor.run(
        SkillSpec(
            name="resume_candidate_review",
            description="Find recent candidate, application, or resume-related inbox emails, inspect whether they include attachments, and pass relevant extracted attachment text through to the external finalizer for structured candidate summaries.",
            scope="Read-only resume and candidate review workflow. Never send email and never modify mailbox state.",
            used_tools=("search_emails", "get_email_attachments", "extract_recent_attachment_texts"),
            output="A user-facing structured candidate review grounded only in the search hits, attachment listings, and any extracted attachment text from matched candidate emails.",
            input_schema=(
                SkillInputFieldSpec(
                    name="days",
                    field_type="int",
                    required=False,
                    description="Number of recent days to inspect for candidate, application, or resume-related emails.",
                    has_default=True,
                    default=7,
                ),
            ),
        ),
        skill_arguments={"days": 10},
        current_message="帮我获取最近简历的主要信息并结构化总结",
        intent_decision=type(
            "IntentDecisionLike",
            (),
            {"intent": "用户想让我总结最近候选人或简历邮件里的主要信息，并优先使用附件内容做结构化总结。"},
        )(),
        recent_context=[],
    )

    assert result.completed is True
    assert "[RESUME_CANDIDATE_REVIEW_BUNDLE]" in result.response
    assert "search_query: in:inbox newer_than:7d" in result.response
    assert "[SEARCH_EMAILS]" in result.response
    assert "[ATTACHMENT_CHECK_RESULTS]" in result.response
    assert "[MATCHED_CANDIDATE_EMAIL_IDS_WITH_ATTACHMENTS]" in result.response
    assert "[RELEVANT_ATTACHMENT_TEXT_EXTRACTIONS]" in result.response
    assert "Finalizer instruction: produce a structured candidate summary for each relevant candidate email, grounded first in extracted attachment text when available." in result.response
    assert "resume-001, resume-002" in result.response
    assert "resume-001" in result.response
    assert "Riley Applicant. Backend engineer. Python, FastAPI, Postgres, LLM tooling." in result.response
    assert "unrelated-999" not in result.response

    expected_query = (
        'in:inbox newer_than:7d (candidate OR applicant OR application OR resume OR cv OR portfolio OR '
        '"job application" OR "application for" OR "applying for" OR "cover letter" OR "candidate profile" OR '
        '"candidate submission" OR "resume attached" OR "cv attached")'
    )
    assert toolbox.calls == [
        ("search_emails", {"query": expected_query, "max_results": 350}),
        ("get_email_attachments", {"email_id": "resume-001"}),
        ("get_email_attachments", {"email_id": "resume-002"}),
        (
            "extract_recent_attachment_texts",
            {
                "query": 'in:inbox newer_than:7d (candidate OR applicant OR application OR resume OR cv OR portfolio OR "job application" OR "application for" OR "applying for" OR "cover letter" OR "candidate profile" OR "candidate submission" OR "resume attached" OR "cv attached") has:attachment',
                "max_results": 350,
            },
        ),
    ]


def test_draft_reply_from_email_context_uses_unanswered_rank_workflow(repo_root: Path | None = None):
    del repo_root
    toolbox = DraftReplyToolBox()
    tool_function_map = build_tool_function_map([toolbox])
    skills_directory = Path(__file__).resolve().parent.parent / "skills"
    writing_style_path = skills_directory.parent / "test_tmp_writing_style_unanswered.md"
    writing_style_path.write_text(
        "# Writing Style\n\n- Keep replies concise, warm, and direct.\n- Prefer short confirmations and friendly closings.\n",
        encoding="utf-8",
    )

    try:
        executor = PythonSkillExecutor(
            skills_directory=skills_directory,
            tool_function_map=tool_function_map,
            skill_runtime={
                "paths": {
                    "writing_style_markdown": writing_style_path,
                },
            },
        )

        result = executor.run(
            SkillSpec(
                name="draft_reply_from_email_context",
                description="Locate a target email either by unanswered-message rank or by a mailbox search query, then fetch the target email body so the outer layer can draft a reply.",
                scope="Draft-only reply workflow. Never send email and never modify mailbox state.",
                used_tools=("search_emails", "get_unanswered_emails", "get_email_body"),
                output="A user-facing reply draft grounded only in the located target email, the associated mailbox search results, and the fetched full email body.",
                input_schema=(
                    SkillInputFieldSpec(
                        name="selection_mode",
                        field_type="string",
                        required=True,
                        description="Use unanswered_rank or search_query.",
                    ),
                    SkillInputFieldSpec(
                        name="target_rank",
                        field_type="int",
                        required=False,
                        description="1-based unanswered-email rank.",
                        has_default=True,
                        default=1,
                    ),
                    SkillInputFieldSpec(
                        name="query",
                        field_type="string",
                        required=False,
                        description="Mailbox search fragment used only when selection_mode is search_query.",
                    ),
                    SkillInputFieldSpec(
                        name="days",
                        field_type="int",
                        required=False,
                        description="Search lookback window for search_query mode.",
                        has_default=True,
                        default=30,
                    ),
                ),
            ),
            skill_arguments={"selection_mode": "unanswered_rank", "target_rank": 2},
            current_message="帮我对倒数第二条没回复的消息起草",
            intent_decision=type(
                "IntentDecisionLike",
                (),
                {"intent": "用户想让我对第二条最近未回复的邮件起草回复。"},
            )(),
            recent_context=[],
        )
    finally:
        if writing_style_path.exists():
            writing_style_path.unlink()

    assert result.completed is True
    assert "[DRAFT_REPLY_FROM_EMAIL_CONTEXT_BUNDLE]" in result.response
    assert "[WRITING_STYLE]" in result.response
    assert "Keep replies concise, warm, and direct." in result.response
    assert "selection_mode: unanswered_rank" in result.response
    assert "target_email_id: reply-unanswered-002" in result.response
    assert "[UNANSWERED_RESULTS]" in result.response
    assert "[SELECTED_UNANSWERED_ENTRY]" in result.response
    assert "from: Brenda <brenda@example.com>" in result.response
    assert "[UNANSWERED_LOOKUP_SEARCH]" in result.response
    assert "[TARGET_EMAIL_BODY]" in result.response
    assert "Full body for reply-unanswered-002" in result.response

    assert toolbox.calls[0] == ("get_unanswered_emails", {"within_days": 7, "max_results": 30})
    assert toolbox.calls[1] == (
        "search_emails",
        {
            "query": 'in:inbox newer_than:7d from:brenda@example.com subject:"Re: Coffee chat next week"',
            "max_results": 1,
        },
    )
    assert toolbox.calls[2] == ("get_email_body", {"email_id": "reply-unanswered-002"})
    assert len(toolbox.calls) == 3


def test_draft_reply_from_email_context_uses_search_query_workflow(repo_root: Path | None = None):
    del repo_root
    toolbox = DraftReplyToolBox()
    tool_function_map = build_tool_function_map([toolbox])
    skills_directory = Path(__file__).resolve().parent.parent / "skills"
    writing_style_path = skills_directory.parent / "test_tmp_writing_style_search.md"
    writing_style_path.write_text(
        "# Writing Style\n\n- Use upbeat greetings.\n- Close with a confident next-step sentence.\n",
        encoding="utf-8",
    )

    try:
        executor = PythonSkillExecutor(
            skills_directory=skills_directory,
            tool_function_map=tool_function_map,
            skill_runtime={
                "paths": {
                    "writing_style_markdown": writing_style_path,
                },
            },
        )

        result = executor.run(
            SkillSpec(
                name="draft_reply_from_email_context",
                description="Locate a target email either by unanswered-message rank or by a mailbox search query, then fetch the target email body so the outer layer can draft a reply.",
                scope="Draft-only reply workflow. Never send email and never modify mailbox state.",
                used_tools=("search_emails", "get_unanswered_emails", "get_email_body"),
                output="A user-facing reply draft grounded only in the located target email, the associated mailbox search results, and the fetched full email body.",
                input_schema=(
                    SkillInputFieldSpec(
                        name="selection_mode",
                        field_type="string",
                        required=True,
                        description="Use unanswered_rank or search_query.",
                    ),
                    SkillInputFieldSpec(
                        name="target_rank",
                        field_type="int",
                        required=False,
                        description="1-based unanswered-email rank.",
                        has_default=True,
                        default=1,
                    ),
                    SkillInputFieldSpec(
                        name="query",
                        field_type="string",
                        required=False,
                        description="Mailbox search fragment used only when selection_mode is search_query.",
                    ),
                    SkillInputFieldSpec(
                        name="days",
                        field_type="int",
                        required=False,
                        description="Search lookback window for search_query mode.",
                        has_default=True,
                        default=30,
                    ),
                ),
            ),
            skill_arguments={
                "selection_mode": "search_query",
                "query": "from:zenglin0813@gmail.com OR to:zenglin0813@gmail.com",
                "days": 14,
            },
            current_message="给 zenglin 那封起草回复",
            intent_decision=type(
                "IntentDecisionLike",
                (),
                {"intent": "用户想让我根据与 Zenglin 的邮件上下文起草回复。"},
            )(),
            recent_context=[],
        )
    finally:
        if writing_style_path.exists():
            writing_style_path.unlink()

    assert result.completed is True
    assert "[WRITING_STYLE]" in result.response
    assert "Use upbeat greetings." in result.response
    assert "selection_mode: search_query" in result.response
    assert "target_email_id: reply-search-001" in result.response
    assert "[SEARCH_RESULTS]" in result.response
    assert "[SEARCH_MATCHED_EMAIL_IDS]" in result.response
    assert "reply-search-001, reply-search-002" in result.response
    assert "[TARGET_EMAIL_BODY]" in result.response
    assert "Full body for reply-search-001" in result.response
    assert "[UNANSWERED_RESULTS]" in result.response
    assert "(not run)" in result.response

    assert toolbox.calls[0] == (
        "search_emails",
        {
            "query": "in:inbox newer_than:14d (from:zenglin0813@gmail.com OR to:zenglin0813@gmail.com)",
            "max_results": 20,
        },
    )
    assert toolbox.calls[1] == ("get_email_body", {"email_id": "reply-search-001"})
    assert len(toolbox.calls) == 2


def test_skill_selector_validates_and_fills_structured_arguments(tmp_path: Path):
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(
        "\n".join(
            [
                "skills:",
                "  - name: weekly_email_summary",
                "    description: Summarize recent inbox activity",
                "    scope: Read-only weekly summary",
                "    used_tools:",
                "      - search_emails",
                "    input_schema:",
                "      days:",
                "        type: int",
                "        required: false",
                "        default: 7",
                "        description: Number of recent days to summarize",
                "      include_unanswered:",
                "        type: bool",
                "        required: false",
                "        default: true",
                "        description: Include unanswered thread context",
                "    output: weekly summary",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    main_agent = FakeAgent(["should not run"], name="main-agent", max_iterations=15)
    intent_agent = FakeAgent(
        [
            json.dumps(
                {
                    "intent": "Summarize recent inbox activity.",
                    "no_execution_confidence": 2,
                    "final_response": None,
                    "reason": "This needs downstream execution.",
                    "user_update_summary": "No meaningful update.",
                }
            )
        ]
    )
    selector_agent = FakeAgent(
        [
            json.dumps(
                {
                    "should_use_skill": True,
                    "skill_name": "weekly_email_summary",
                    "skill_arguments": {"days": "14"},
                    "reason": "This request matches the weekly summary skill.",
                }
            )
        ]
    )
    writer_agent = FakeAgent(
        [
            json.dumps(
                {
                    "should_update": False,
                    "profile_markdown": None,
                    "habits_markdown": None,
                    "reason": "Nothing new to store.",
                }
            )
        ]
    )
    skill_executor = FakeSkillExecutor(
        SkillExecutionResult(
            attempted=True,
            completed=True,
            response="Structured summary response.",
            reason="Skill completed.",
        )
    )

    store = MarkdownMemoryStore(
        profile_path=tmp_path / "USER_PROFILE.md",
        habits_path=tmp_path / "USER_HABITS.md",
        writer_agent=writer_agent,
    )
    orchestrator = IntentLayerOrchestrator(
        main_agent=main_agent,
        intent_agent=intent_agent,
        skill_selector_agent=selector_agent,
        skill_finalizer_agent=FakeAgent(
            [
                json.dumps(
                    {
                        "final_response": "我已经整理好这份周报摘要：\n\nStructured summary response.",
                        "reason": "The completed summary skill already provided the core content.",
                    }
                )
            ],
            name="skill-finalizer",
        ),
        skill_executor=skill_executor,
        memory_store=store,
        skill_registry_path=registry_path,
    )

    result = orchestrator.input("Give me a weekly inbox summary.")

    assert result == "我已经整理好这份周报摘要：\n\nStructured summary response."
    executed_skill, skill_arguments, _, _, _, _ = skill_executor.calls[0]
    assert executed_skill.name == "weekly_email_summary"
    assert skill_arguments == {"days": 14, "include_unanswered": True}


def test_skill_selector_rejects_unknown_structured_arguments(tmp_path: Path):
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(
        "\n".join(
            [
                "skills:",
                "  - name: weekly_email_summary",
                "    description: Summarize recent inbox activity",
                "    scope: Read-only weekly summary",
                "    used_tools:",
                "      - search_emails",
                "    input_schema:",
                "      days:",
                "        type: int",
                "        required: false",
                "        default: 7",
                "        description: Number of recent days to summarize",
                "    output: weekly summary",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    main_agent = FakeAgent(["should not run"], name="main-agent", max_iterations=15)
    intent_agent = FakeAgent(
        [
            json.dumps(
                {
                    "intent": "Summarize recent inbox activity.",
                    "no_execution_confidence": 2,
                    "final_response": None,
                    "reason": "This needs downstream execution.",
                    "user_update_summary": "No meaningful update.",
                }
            )
        ]
    )
    selector_agent = FakeAgent(
        [
            json.dumps(
                {
                    "should_use_skill": True,
                    "skill_name": "weekly_email_summary",
                    "skill_arguments": {"days": 14, "unknown_flag": True},
                    "reason": "This request matches the weekly summary skill.",
                }
            )
        ]
    )
    writer_agent = FakeAgent(
        [
            json.dumps(
                {
                    "should_update": False,
                    "profile_markdown": None,
                    "habits_markdown": None,
                    "reason": "Nothing new to store.",
                }
            )
        ]
    )

    store = MarkdownMemoryStore(
        profile_path=tmp_path / "USER_PROFILE.md",
        habits_path=tmp_path / "USER_HABITS.md",
        writer_agent=writer_agent,
    )
    orchestrator = IntentLayerOrchestrator(
        main_agent=main_agent,
        intent_agent=intent_agent,
        skill_selector_agent=selector_agent,
        skill_finalizer_agent=make_noop_skill_finalizer(),
        skill_executor=None,
        memory_store=store,
        skill_registry_path=registry_path,
    )

    try:
        orchestrator.input("Give me a weekly inbox summary.")
        raise AssertionError("Expected SkillLayerError to be raised.")
    except SkillLayerError:
        pass
