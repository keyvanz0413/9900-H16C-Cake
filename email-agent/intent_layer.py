from __future__ import annotations

import json
import inspect
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol


CONTEXT_WINDOW_LIMIT = 50
OLDER_CONTEXT_LIMIT = 40
RECENT_CONTEXT_LIMIT = 10
DIRECT_RESPONSE_THRESHOLD = 8.0

DEFAULT_USER_PROFILE = """# User Profile

- No confirmed profile details yet.
"""

DEFAULT_USER_HABITS = """# User Habits

- No confirmed habits yet.
"""

SKIP_UPDATE_MARKERS = {
    "",
    "none",
    "n/a",
    "no update",
    "no new user info",
    "no new information",
    "no meaningful update",
}


class SupportsInput(Protocol):
    name: str
    max_iterations: int

    def input(
        self,
        prompt: str,
        max_iterations: int | None = None,
        session: dict[str, Any] | None = None,
        images: list[str] | None = None,
        files: list[dict[str, Any]] | None = None,
    ) -> str:
        ...


@dataclass(frozen=True)
class DialogueItem:
    role: str
    content: str

    def as_context_line(self) -> str:
        speaker = "User" if self.role == "user" else "Assistant"
        return f"{speaker}: {self.content.strip()}"


@dataclass(frozen=True)
class IntentDecision:
    intent: str
    no_execution_confidence: float
    final_response: str | None
    reason: str
    user_update_summary: str

    @property
    def should_direct_respond(self) -> bool:
        return self.no_execution_confidence > DIRECT_RESPONSE_THRESHOLD and bool(self.final_response)


@dataclass(frozen=True)
class SkillSpec:
    name: str
    description: str
    scope: str
    allowed_tools: tuple[str, ...]
    output: str


@dataclass(frozen=True)
class SkillSelection:
    should_use_skill: bool
    skill_name: str | None
    reason: str


@dataclass(frozen=True)
class MemoryUpdate:
    should_update: bool
    profile_markdown: str | None
    habits_markdown: str | None
    reason: str


@dataclass(frozen=True)
class SkillExecutionResult:
    attempted: bool
    completed: bool
    response: str | None
    reason: str


class SupportsSkillExecution(Protocol):
    def run(
        self,
        skill_spec: SkillSpec,
        *,
        current_message: str,
        intent_decision: IntentDecision,
        recent_context: list[DialogueItem],
        max_iterations: int | None = None,
    ) -> SkillExecutionResult:
        ...


class IntentLayerError(RuntimeError):
    pass


class SkillLayerError(RuntimeError):
    pass


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _strip_code_fences(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 3:
            return parts[1].replace("json", "", 1).strip()
    return text


def _extract_json_payload(raw_text: str) -> dict[str, Any]:
    text = _strip_code_fences(raw_text)
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in LLM response.")

    payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("LLM response JSON was not an object.")
    return payload


def _require_non_empty_string(value: Any, *, field_name: str, error_type: type[Exception]) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise error_type(f"Missing or empty required field: {field_name}")
    return normalized


def _summarize_for_log(value: Any, *, limit: int = 160) -> str:
    text = " ".join(str(value or "").strip().split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def split_context(dialogue_items: list[DialogueItem]) -> tuple[list[DialogueItem], list[DialogueItem]]:
    window = dialogue_items[-CONTEXT_WINDOW_LIMIT:]
    if len(window) <= RECENT_CONTEXT_LIMIT:
        return [], window

    recent = window[-RECENT_CONTEXT_LIMIT:]
    older = window[:-RECENT_CONTEXT_LIMIT][-OLDER_CONTEXT_LIMIT:]
    return older, recent


def format_context(items: list[DialogueItem]) -> str:
    if not items:
        return "(empty)"
    return "\n".join(item.as_context_line() for item in items)


def _parse_scalar(raw_value: str) -> str:
    value = raw_value.strip()
    if value in {"", "null", "None"}:
        return ""
    if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
        return value[1:-1]
    return value


def build_tool_function_map(tool_sources: list[Any]) -> dict[str, Callable[..., Any]]:
    tool_function_map: dict[str, Callable[..., Any]] = {}

    for source in tool_sources:
        if inspect.isfunction(source) or inspect.ismethod(source) or inspect.isbuiltin(source):
            name = getattr(source, "__name__", "")
            if name and not name.startswith("_"):
                tool_function_map[name] = source
            continue

        for name, member in inspect.getmembers(source):
            if name.startswith("_") or not callable(member):
                continue
            tool_function_map[name] = member

    return tool_function_map


def _coerce_skill_spec(raw_skill: dict[str, Any]) -> SkillSpec | None:
    name = _normalize_text(raw_skill.get("name"))
    if not name:
        return None

    allowed_tools = raw_skill.get("allowed_tools") or []
    if not isinstance(allowed_tools, (list, tuple)):
        allowed_tools = []

    return SkillSpec(
        name=name,
        description=str(raw_skill.get("description") or "").strip(),
        scope=str(raw_skill.get("scope") or "").strip(),
        allowed_tools=tuple(str(tool).strip() for tool in allowed_tools if str(tool).strip()),
        output=str(raw_skill.get("output") or "").strip(),
    )


def load_skill_registry(path: Path) -> list[SkillSpec]:
    if not path.exists():
        return []

    raw_text = path.read_text(encoding="utf-8")

    try:
        import yaml  # type: ignore
    except ImportError:
        yaml = None

    if yaml is not None:
        payload = yaml.safe_load(raw_text) or {}
        raw_skills = payload.get("skills") or []
        specs = [_coerce_skill_spec(raw_skill) for raw_skill in raw_skills if isinstance(raw_skill, dict)]
        return [spec for spec in specs if spec is not None]

    skills: list[SkillSpec] = []
    current: dict[str, Any] | None = None
    reading_allowed_tools = False

    for raw_line in raw_text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()

        if stripped == "skills:":
            continue

        if indent == 2 and stripped.startswith("- "):
            if current is not None:
                spec = _coerce_skill_spec(current)
                if spec is not None:
                    skills.append(spec)
            current = {"allowed_tools": []}
            reading_allowed_tools = False
            remainder = stripped[2:].strip()
            if remainder and ":" in remainder:
                key, value = remainder.split(":", 1)
                current[key.strip()] = _parse_scalar(value)
            continue

        if current is None:
            continue

        if indent == 4 and ":" in stripped:
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()
            if key == "allowed_tools":
                reading_allowed_tools = True
                if value == "[]":
                    current["allowed_tools"] = []
                    reading_allowed_tools = False
                elif value.startswith("[") and value.endswith("]"):
                    inner = value[1:-1]
                    current["allowed_tools"] = [
                        _parse_scalar(item) for item in inner.split(",") if _parse_scalar(item)
                    ]
                    reading_allowed_tools = False
                else:
                    current.setdefault("allowed_tools", [])
            else:
                reading_allowed_tools = False
                current[key] = _parse_scalar(value)
            continue

        if reading_allowed_tools and indent >= 6 and stripped.startswith("- "):
            current.setdefault("allowed_tools", []).append(_parse_scalar(stripped[2:]))

    if current is not None:
        spec = _coerce_skill_spec(current)
        if spec is not None:
            skills.append(spec)

    return skills


class MarkdownMemoryStore:
    def __init__(self, profile_path: Path, habits_path: Path, writer_agent: SupportsInput):
        self.profile_path = profile_path
        self.habits_path = habits_path
        self.writer_agent = writer_agent

    def read_profile(self) -> str:
        return self._read_or_default(self.profile_path, DEFAULT_USER_PROFILE)

    def read_habits(self) -> str:
        return self._read_or_default(self.habits_path, DEFAULT_USER_HABITS)

    def apply_update(self, *, update_summary: str, latest_user_message: str, latest_response: str) -> MemoryUpdate:
        normalized_summary = _normalize_text(update_summary).lower().strip(" .!?:;")
        if normalized_summary in SKIP_UPDATE_MARKERS:
            return MemoryUpdate(False, None, None, "No user profile or habit updates were detected.")

        current_profile = self.read_profile()
        current_habits = self.read_habits()

        prompt = "\n\n".join(
            [
                "[USER_UPDATE_SUMMARY]",
                update_summary.strip(),
                "[LATEST_USER_MESSAGE]",
                latest_user_message.strip(),
                "[LATEST_ASSISTANT_RESPONSE]",
                latest_response.strip(),
                "[CURRENT_USER_PROFILE]",
                current_profile,
                "[CURRENT_USER_HABITS]",
                current_habits,
            ]
        )

        try:
            payload = _extract_json_payload(self.writer_agent.input(prompt, max_iterations=1))
        except Exception as exc:
            return MemoryUpdate(False, None, None, f"Memory writer fallback: {exc}")

        should_update = bool(payload.get("should_update"))
        if not should_update:
            return MemoryUpdate(False, None, None, str(payload.get("reason") or "Writer decided no update was needed."))

        profile_markdown = str(payload.get("profile_markdown") or "").strip()
        habits_markdown = str(payload.get("habits_markdown") or "").strip()

        if not profile_markdown or not habits_markdown:
            return MemoryUpdate(False, None, None, "Writer returned an incomplete markdown update.")

        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        self.habits_path.parent.mkdir(parents=True, exist_ok=True)
        self.profile_path.write_text(profile_markdown + "\n", encoding="utf-8")
        self.habits_path.write_text(habits_markdown + "\n", encoding="utf-8")
        return MemoryUpdate(True, profile_markdown, habits_markdown, str(payload.get("reason") or "Updated user files."))

    @staticmethod
    def _read_or_default(path: Path, default_content: str) -> str:
        if not path.exists():
            return default_content
        content = path.read_text(encoding="utf-8").strip()
        return content or default_content


class RestrictedSkillExecutor:
    def __init__(
        self,
        *,
        agent_factory: Callable[..., SupportsInput],
        system_prompt: str | Path,
        tool_function_map: dict[str, Callable[..., Any]],
        model: str,
        default_max_iterations: int = 8,
    ):
        self._agent_factory = agent_factory
        self._system_prompt = system_prompt
        self._tool_function_map = dict(tool_function_map)
        self._model = model
        self._default_max_iterations = max(1, int(default_max_iterations))

    def run(
        self,
        skill_spec: SkillSpec,
        *,
        current_message: str,
        intent_decision: IntentDecision,
        recent_context: list[DialogueItem],
        max_iterations: int | None = None,
    ) -> SkillExecutionResult:
        resolved_tools: list[Callable[..., Any]] = []
        missing_tools: list[str] = []

        for tool_name in skill_spec.allowed_tools:
            tool_callable = self._tool_function_map.get(tool_name)
            if tool_callable is None:
                missing_tools.append(tool_name)
            else:
                resolved_tools.append(tool_callable)

        if missing_tools:
            return SkillExecutionResult(
                attempted=True,
                completed=False,
                response=None,
                reason=(
                    f"Skill '{skill_spec.name}' could not start because these allowed tools are unavailable: "
                    + ", ".join(missing_tools)
                ),
            )

        skill_iterations = self._default_max_iterations
        if max_iterations is not None:
            skill_iterations = max(1, min(int(max_iterations), self._default_max_iterations))

        skill_agent = self._agent_factory(
            name=f"email-skill-{skill_spec.name}",
            system_prompt=self._system_prompt,
            tools=resolved_tools,
            max_iterations=skill_iterations,
            model=self._model,
        )

        prompt = "\n\n".join(
            [
                "[SKILL_NAME]",
                skill_spec.name,
                "[SKILL_DESCRIPTION]",
                skill_spec.description or "(empty)",
                "[SKILL_SCOPE]",
                skill_spec.scope or "(empty)",
                "[SKILL_OUTPUT]",
                skill_spec.output or "(empty)",
                "[ALLOWED_TOOLS]",
                ", ".join(skill_spec.allowed_tools) if skill_spec.allowed_tools else "(none)",
                "[INTENT]",
                intent_decision.intent,
                "[RECENT_CONTEXT]",
                format_context(recent_context),
                "[CURRENT_USER_MESSAGE]",
                current_message.strip(),
            ]
        )

        try:
            payload = _extract_json_payload(skill_agent.input(prompt, max_iterations=skill_iterations))
        except Exception as exc:
            raise SkillLayerError(f"Skill '{skill_spec.name}' execution failed: {exc}") from exc

        completed = bool(payload.get("completed"))
        response_raw = payload.get("response")
        response = None if response_raw is None else str(response_raw).strip()
        reason = _require_non_empty_string(payload.get("reason"), field_name="reason", error_type=SkillLayerError)

        if completed and not response:
            raise SkillLayerError(f"Skill '{skill_spec.name}' returned completed=true without a response.")

        if not completed or not response:
            return SkillExecutionResult(
                attempted=True,
                completed=False,
                response=None,
                reason=reason,
            )

        return SkillExecutionResult(
            attempted=True,
            completed=True,
            response=response,
            reason=reason,
        )


class IntentLayerOrchestrator:
    def __init__(
        self,
        *,
        main_agent: SupportsInput,
        intent_agent: SupportsInput,
        skill_selector_agent: SupportsInput,
        skill_executor: SupportsSkillExecution | None,
        memory_store: MarkdownMemoryStore,
        skill_registry_path: Path,
    ):
        self._main_agent = main_agent
        self._intent_agent = intent_agent
        self._skill_selector_agent = skill_selector_agent
        self._skill_executor = skill_executor
        self._memory_store = memory_store
        self._skill_registry_path = skill_registry_path
        self._fallback_dialogue_items: list[dict[str, str]] = []
        self._dialogue_items_by_session_id: dict[str, list[dict[str, str]]] = {}
        self._lock = threading.RLock()
        self.current_session: dict[str, Any] | None = None

        self.name = getattr(main_agent, "name", "email-agent")
        self.max_iterations = getattr(main_agent, "max_iterations", 15)

    def input(
        self,
        prompt: str,
        max_iterations: int | None = None,
        session: dict[str, Any] | None = None,
        images: list[str] | None = None,
        files: list[dict[str, Any]] | None = None,
    ) -> str:
        with self._lock:
            if isinstance(session, dict):
                self.current_session = session
            dialogue_store = self._get_dialogue_store()
            older_context, recent_context = split_context(self._deserialize_dialogue(dialogue_store))
            profile_markdown = self._memory_store.read_profile()
            habits_markdown = self._memory_store.read_habits()

            intent_decision = self._analyze_intent(
                current_message=prompt,
                older_context=older_context,
                recent_context=recent_context,
                profile_markdown=profile_markdown,
                habits_markdown=habits_markdown,
            )

            if intent_decision.should_direct_respond:
                self._log_route(
                    "direct_response",
                    confidence=intent_decision.no_execution_confidence,
                    intent=intent_decision.intent,
                )
                response = intent_decision.final_response or ""
            else:
                available_skills = load_skill_registry(self._skill_registry_path)
                skills_by_name = {skill.name: skill for skill in available_skills}
                selection = self._select_skill(
                    intent_decision=intent_decision,
                    current_message=prompt,
                    recent_context=recent_context,
                    available_skills=available_skills,
                )
                self._log_route(
                    "skill_selection",
                    confidence=intent_decision.no_execution_confidence,
                    intent=intent_decision.intent,
                    should_use_skill=selection.should_use_skill,
                    skill_name=selection.skill_name,
                    reason=selection.reason,
                    registered_skills=len(available_skills),
                )
                skill_execution_result: SkillExecutionResult | None = None

                if selection.should_use_skill and self._skill_executor is not None and selection.skill_name:
                    skill_spec = skills_by_name.get(selection.skill_name)
                    if skill_spec is not None:
                        self._log_route(
                            "skill_execution_started",
                            skill_name=skill_spec.name,
                            allowed_tools=", ".join(skill_spec.allowed_tools),
                        )
                        skill_execution_result = self._skill_executor.run(
                            skill_spec,
                            current_message=prompt,
                            intent_decision=intent_decision,
                            recent_context=recent_context,
                            max_iterations=max_iterations,
                        )
                        self._log_route(
                            "skill_execution_finished",
                            skill_name=skill_spec.name,
                            completed=skill_execution_result.completed,
                            reason=skill_execution_result.reason,
                        )

                if skill_execution_result is not None and skill_execution_result.completed and skill_execution_result.response:
                    self._log_route(
                        "skill_response",
                        skill_name=selection.skill_name,
                    )
                    response = skill_execution_result.response
                else:
                    self._log_route(
                        "main_agent",
                        confidence=intent_decision.no_execution_confidence,
                        intent=intent_decision.intent,
                        via="skill_fallback" if skill_execution_result is not None else "direct_handoff",
                        skill_name=selection.skill_name,
                    )
                    response = self._run_main_agent(
                        user_message=prompt,
                        intent_decision=intent_decision,
                        recent_context=recent_context,
                        skill_selection=selection,
                        skill_execution_result=skill_execution_result,
                        max_iterations=max_iterations,
                        session=session,
                        images=images,
                        files=files,
                    )

            dialogue_store.append({"role": "user", "content": prompt})
            dialogue_store.append({"role": "assistant", "content": response})
            self._sync_dialogue_store(dialogue_store)

            memory_update = self._memory_store.apply_update(
                update_summary=intent_decision.user_update_summary,
                latest_user_message=prompt,
                latest_response=response,
            )
            self._log_route(
                "memory_update",
                applied=memory_update.should_update,
                reason=memory_update.reason,
            )

            return response

    def __getattr__(self, name: str) -> Any:
        return getattr(self._main_agent, name)

    def _log_route(self, event: str, **details: Any) -> None:
        payload: dict[str, Any] = {"event": event}
        current_session = self._resolve_current_session()
        if isinstance(current_session, dict) and current_session.get("session_id"):
            payload["session_id"] = current_session.get("session_id")
        for key, value in details.items():
            if value is None:
                continue
            if isinstance(value, str):
                payload[key] = _summarize_for_log(value)
            else:
                payload[key] = value
        print("[intent-layer] " + json.dumps(payload, ensure_ascii=False), flush=True)

    def _get_dialogue_store(self) -> list[dict[str, str]]:
        current_session = self._resolve_current_session()
        if isinstance(current_session, dict):
            session_id = self._get_session_id(current_session)
            raw_store = current_session.get("_intent_layer_dialogue")

            if session_id:
                if session_id not in self._dialogue_items_by_session_id:
                    if isinstance(raw_store, list):
                        self._dialogue_items_by_session_id[session_id] = raw_store
                    else:
                        self._dialogue_items_by_session_id[session_id] = []
                store = self._dialogue_items_by_session_id[session_id]
                current_session["_intent_layer_dialogue"] = store
                return store

            if isinstance(raw_store, list):
                return raw_store

            raw_store = []
            current_session["_intent_layer_dialogue"] = raw_store
            return raw_store
        return self._fallback_dialogue_items

    def _sync_dialogue_store(self, dialogue_store: list[dict[str, str]]) -> None:
        current_session = self._resolve_current_session()
        if isinstance(current_session, dict):
            current_session["_intent_layer_dialogue"] = dialogue_store
            session_id = self._get_session_id(current_session)
            if session_id:
                self._dialogue_items_by_session_id[session_id] = dialogue_store

    @staticmethod
    def _get_session_id(current_session: dict[str, Any]) -> str | None:
        session_id = _normalize_text(current_session.get("session_id"))
        return session_id or None

    def _resolve_current_session(self) -> dict[str, Any] | None:
        if isinstance(self.current_session, dict):
            return self.current_session

        current_session = getattr(self._main_agent, "current_session", None)
        if isinstance(current_session, dict):
            self.current_session = current_session
            return current_session

        return None

    @staticmethod
    def _deserialize_dialogue(raw_items: list[dict[str, str]]) -> list[DialogueItem]:
        dialogue_items: list[DialogueItem] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip()
            content = str(item.get("content") or "").strip()
            if role in {"user", "assistant"} and content:
                dialogue_items.append(DialogueItem(role=role, content=content))
        return dialogue_items

    def _analyze_intent(
        self,
        *,
        current_message: str,
        older_context: list[DialogueItem],
        recent_context: list[DialogueItem],
        profile_markdown: str,
        habits_markdown: str,
    ) -> IntentDecision:
        prompt = "\n\n".join(
            [
                "[CURRENT_USER_MESSAGE]",
                current_message.strip(),
                "[OLDER_CONTEXT]",
                format_context(older_context),
                "[RECENT_CONTEXT]",
                format_context(recent_context),
                "[USER_PROFILE]",
                profile_markdown,
                "[USER_HABITS]",
                habits_markdown,
            ]
        )

        try:
            payload = _extract_json_payload(self._intent_agent.input(prompt, max_iterations=1))
        except Exception as exc:
            raise IntentLayerError(f"Intent layer execution failed: {exc}") from exc

        intent = _require_non_empty_string(payload.get("intent"), field_name="intent", error_type=IntentLayerError)
        try:
            confidence = float(payload.get("no_execution_confidence", 0))
        except (TypeError, ValueError):
            raise IntentLayerError("Intent layer returned an invalid no_execution_confidence value.")

        if confidence < 0 or confidence > 10:
            raise IntentLayerError("Intent layer returned no_execution_confidence outside the 0-10 range.")

        final_response_raw = payload.get("final_response")
        final_response = None if final_response_raw is None else str(final_response_raw).strip()
        if confidence > DIRECT_RESPONSE_THRESHOLD and not final_response:
            raise IntentLayerError("Intent layer returned no_execution_confidence > 8 without a final_response.")
        if confidence <= DIRECT_RESPONSE_THRESHOLD and final_response is not None:
            raise IntentLayerError("Intent layer returned final_response even though no_execution_confidence <= 8.")
        if confidence <= DIRECT_RESPONSE_THRESHOLD:
            final_response = None

        return IntentDecision(
            intent=intent,
            no_execution_confidence=confidence,
            final_response=final_response,
            reason=_require_non_empty_string(payload.get("reason"), field_name="reason", error_type=IntentLayerError),
            user_update_summary=str(payload.get("user_update_summary") or "").strip(),
        )

    def _select_skill(
        self,
        *,
        intent_decision: IntentDecision,
        current_message: str,
        recent_context: list[DialogueItem],
        available_skills: list[SkillSpec],
    ) -> SkillSelection:
        if not available_skills:
            return SkillSelection(False, None, "No skills are registered in skills/registry.yaml.")

        skills_block = []
        for spec in available_skills:
            lines = [
                f"- skill_name: {spec.name}",
                f"  description: {spec.description or '(empty)'}",
                f"  scope: {spec.scope or '(empty)'}",
            ]
            if spec.allowed_tools:
                lines.append(f"  allowed_tools: {', '.join(spec.allowed_tools)}")
            if spec.output:
                lines.append(f"  output: {spec.output}")
            skills_block.append("\n".join(lines))

        prompt = "\n\n".join(
            [
                "[INTENT]",
                intent_decision.intent,
                "[CURRENT_USER_MESSAGE]",
                current_message.strip(),
                "[RECENT_CONTEXT]",
                format_context(recent_context),
                "[CURRENT_SESSION_STATE]",
                "No explicit session state is available in this implementation.",
                "[AVAILABLE_SKILLS]",
                "\n\n".join(skills_block),
            ]
        )

        try:
            payload = _extract_json_payload(self._skill_selector_agent.input(prompt, max_iterations=1))
        except Exception as exc:
            raise SkillLayerError(f"Skill selector execution failed: {exc}") from exc

        should_use_skill = bool(payload.get("should_use_skill"))
        skill_name_raw = payload.get("skill_name")
        skill_name = None if skill_name_raw is None else str(skill_name_raw).strip()
        allowed_skill_names = {spec.name for spec in available_skills}
        reason = _require_non_empty_string(payload.get("reason"), field_name="reason", error_type=SkillLayerError)

        if should_use_skill:
            if not skill_name:
                raise SkillLayerError("Skill selector returned should_use_skill=true without a skill_name.")
            if skill_name not in allowed_skill_names:
                raise SkillLayerError(f"Skill selector returned unknown skill_name: {skill_name}")
            return SkillSelection(True, skill_name, reason)

        if skill_name is not None:
            raise SkillLayerError("Skill selector returned a skill_name even though should_use_skill=false.")

        return SkillSelection(False, None, reason)

    def _run_main_agent(
        self,
        *,
        user_message: str,
        intent_decision: IntentDecision,
        recent_context: list[DialogueItem],
        skill_selection: SkillSelection,
        skill_execution_result: SkillExecutionResult | None,
        max_iterations: int | None,
        session: dict[str, Any] | None,
        images: list[str] | None,
        files: list[dict[str, Any]] | None,
    ) -> str:
        handoff_sections = [
            "[INTENT_LAYER_HANDOFF]",
            f"intent: {intent_decision.intent}",
            f"reason: {intent_decision.reason or 'No reason provided.'}",
            f"no_execution_confidence: {intent_decision.no_execution_confidence}",
            f"skill_selector: {'use ' + skill_selection.skill_name if skill_selection.should_use_skill and skill_selection.skill_name else 'route to main agent'}",
            f"skill_selector_reason: {skill_selection.reason}",
        ]
        if skill_execution_result is not None:
            handoff_sections.extend(
                [
                    f"skill_attempted: {skill_execution_result.attempted}",
                    f"skill_completed: {skill_execution_result.completed}",
                    f"skill_execution_reason: {skill_execution_result.reason}",
                ]
            )
        handoff_sections.extend(
            [
                "",
                "[RECENT_CONTEXT]",
                format_context(recent_context),
                "",
                "[USER_MESSAGE]",
                user_message.strip(),
            ]
        )
        handoff_prompt = "\n".join(handoff_sections).strip()
        if isinstance(self.current_session, dict):
            setattr(self._main_agent, "current_session", self.current_session)
        response = self._main_agent.input(
            handoff_prompt,
            max_iterations=max_iterations,
            session=session,
            images=images,
            files=files,
        )
        updated_session = getattr(self._main_agent, "current_session", None)
        if isinstance(updated_session, dict):
            self.current_session = updated_session
        return response
