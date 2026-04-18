from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

from intent_layer import (
    DialogueItem,
    IntentLayerError,
    IntentLayerOrchestrator,
    MarkdownMemoryStore,
    RestrictedSkillExecutor,
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
        self.calls: list[tuple[SkillSpec, str, str, list[DialogueItem], int | None]] = []

    def run(
        self,
        skill_spec: SkillSpec,
        *,
        current_message: str,
        intent_decision,
        recent_context: list[DialogueItem],
        max_iterations: int | None = None,
    ) -> SkillExecutionResult:
        self.calls.append((skill_spec, current_message, intent_decision.intent, recent_context, max_iterations))
        return self.result


class ToolBox:
    def search_emails(self, query: str) -> str:
        """Search emails."""
        return f"search:{query}"

    def send(self, recipient: str, body: str) -> str:
        """Send email."""
        return f"sent:{recipient}:{body}"


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
                "    allowed_tools:",
                "      - search_emails",
                "      - read_memory",
                "    output: email_draft",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    skills = load_skill_registry(registry)

    assert len(skills) == 1
    assert skills[0].name == "compose_email_from_context"
    assert skills[0].allowed_tools == ("search_emails", "read_memory")


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
                "    allowed_tools:",
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
        skill_executor=skill_executor,
        memory_store=store,
        skill_registry_path=registry_path,
    )

    result = orchestrator.input("Draft a reply to the client.", max_iterations=6)

    assert result == "Here is a concise draft you can send."
    assert len(main_agent.calls) == 0
    assert len(skill_executor.calls) == 1
    executed_skill, current_message, intent_text, _, forwarded_max_iterations = skill_executor.calls[0]
    assert executed_skill.name == "compose_email_from_context"
    assert current_message == "Draft a reply to the client."
    assert intent_text == "Draft an email reply from existing mailbox context."
    assert forwarded_max_iterations == 6


def test_orchestrator_falls_back_to_main_agent_when_skill_cannot_complete(tmp_path: Path):
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(
        "\n".join(
            [
                "skills:",
                "  - name: compose_email_from_context",
                "    description: Draft an email from mailbox context",
                "    scope: Can only draft, never send",
                "    allowed_tools:",
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
        skill_executor=skill_executor,
        memory_store=store,
        skill_registry_path=registry_path,
    )

    result = orchestrator.input("Draft a reply to the client.")

    assert result == "main-agent fallback response"
    assert len(main_agent.calls) == 1
    handoff_prompt, _, _, _, _ = main_agent.calls[0]
    assert "skill_selector: use compose_email_from_context" in handoff_prompt
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
                "    allowed_tools:",
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


def test_restricted_skill_executor_passes_only_allowed_tools():
    toolbox = ToolBox()
    tool_function_map = build_tool_function_map([toolbox])
    built_agents: list[dict[str, object]] = []

    def fake_agent_factory(**kwargs):
        built_agents.append(kwargs)
        return FakeAgent(
            [
                json.dumps(
                    {
                        "completed": True,
                        "response": "Draft ready.",
                        "reason": "Completed inside the restricted skill scope.",
                    }
                )
            ],
            name=kwargs["name"],
            max_iterations=kwargs["max_iterations"],
        )

    executor = RestrictedSkillExecutor(
        agent_factory=fake_agent_factory,
        system_prompt="prompt.md",
        tool_function_map=tool_function_map,
        model="test-model",
        default_max_iterations=8,
    )

    result = executor.run(
        SkillSpec(
            name="compose_email_from_context",
            description="Draft an email",
            scope="Can only draft, never send",
            allowed_tools=("search_emails",),
            output="email_draft",
        ),
        current_message="Draft a reply.",
        intent_decision=type(
            "IntentDecisionLike",
            (),
            {"intent": "Draft an email reply from mailbox context."},
        )(),
        recent_context=[],
        max_iterations=10,
    )

    assert result.completed is True
    assert len(built_agents) == 1
    passed_tools = built_agents[0]["tools"]
    assert [tool.__name__ for tool in passed_tools] == ["search_emails"]


def test_restricted_skill_executor_fails_when_allowed_tool_is_missing():
    executor = RestrictedSkillExecutor(
        agent_factory=lambda **kwargs: FakeAgent(["should not be created"]),
        system_prompt="prompt.md",
        tool_function_map={},
        model="test-model",
        default_max_iterations=8,
    )

    result = executor.run(
        SkillSpec(
            name="compose_email_from_context",
            description="Draft an email",
            scope="Can only draft, never send",
            allowed_tools=("search_emails",),
            output="email_draft",
        ),
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


def test_restricted_skill_executor_raises_when_llm_output_is_invalid():
    executor = RestrictedSkillExecutor(
        agent_factory=lambda **kwargs: FakeAgent(["not json"]),
        system_prompt="prompt.md",
        tool_function_map={"search_emails": lambda query: f"search:{query}"},
        model="test-model",
        default_max_iterations=8,
    )

    try:
        executor.run(
            SkillSpec(
                name="compose_email_from_context",
                description="Draft an email",
                scope="Can only draft, never send",
                allowed_tools=("search_emails",),
                output="email_draft",
            ),
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
