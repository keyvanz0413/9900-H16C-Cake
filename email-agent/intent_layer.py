from __future__ import annotations

import copy
import importlib.util
import json
import inspect
import threading
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


CONTEXT_WINDOW_LIMIT = 50
OLDER_CONTEXT_LIMIT = 40
RECENT_CONTEXT_LIMIT = 10
DIRECT_RESPONSE_THRESHOLD = 9.0

DEFAULT_USER_PROFILE = """# User Profile

- No confirmed profile details yet.
"""

DEFAULT_USER_HABITS = """# User Habits

- No confirmed habits yet.
"""

DEFAULT_WRITING_STYLE = """# Writing Style

- No writing style profile yet.
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
    used_tools: tuple[str, ...]
    output: str
    input_schema: tuple[SkillInputFieldSpec, ...] = ()


@dataclass(frozen=True)
class SkillInputFieldSpec:
    name: str
    field_type: str
    required: bool
    description: str
    has_default: bool = False
    default: Any = None


@dataclass(frozen=True)
class SkillSelection:
    should_use_skill: bool
    skill_name: str | None
    reason: str
    skill_arguments: dict[str, Any] = field(default_factory=dict)


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


@dataclass(frozen=True)
class PlannedStep:
    step_id: str
    step_type: str
    name: str | None
    goal: str
    reads: tuple[str, ...]


@dataclass(frozen=True)
class ExecutionPlan:
    steps: tuple[PlannedStep, ...]
    reason: str


@dataclass(frozen=True)
class StepExecutionResult:
    step_id: str
    step_type: str
    name: str | None
    status: str
    artifact: dict[str, Any]
    reason: str


class SupportsSkillExecution(Protocol):
    def run(
        self,
        skill_spec: SkillSpec,
        *,
        skill_arguments: dict[str, Any],
        current_message: str,
        intent_decision: IntentDecision,
        recent_context: list[DialogueItem],
        step_goal: str | None = None,
        read_results: list[dict[str, Any]] | None = None,
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

    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload

    raise ValueError("No JSON object found in LLM response.")


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


def serialize_step_result(step_result: StepExecutionResult) -> dict[str, Any]:
    return {
        "step_id": step_result.step_id,
        "type": step_result.step_type,
        **({"name": step_result.name} if step_result.name else {}),
        "status": step_result.status,
        "artifact": copy.deepcopy(step_result.artifact),
        "reason": step_result.reason,
    }


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


def _parse_yaml_scalar(raw_value: str) -> Any:
    value = raw_value.strip()
    if value in {"", "null", "None"}:
        return None
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_yaml_scalar(item) for item in inner.split(",")]
    if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
        return value[1:-1]
    try:
        if value.startswith("0") and value != "0" and not value.startswith("0."):
            raise ValueError
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _parse_simple_yaml_block(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines):
        return {}, index
    if lines[index][1].startswith("- "):
        return _parse_simple_yaml_list(lines, index, indent)
    return _parse_simple_yaml_mapping(lines, index, indent)


def _parse_simple_yaml_mapping(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        current_indent, stripped = lines[index]
        if current_indent < indent:
            break
        if current_indent != indent or stripped.startswith("- "):
            break

        key, separator, remainder = stripped.partition(":")
        if not separator:
            index += 1
            continue
        key = key.strip()
        remainder = remainder.strip()
        index += 1

        if remainder:
            result[key] = _parse_yaml_scalar(remainder)
            continue

        if index < len(lines) and lines[index][0] > current_indent:
            nested, index = _parse_simple_yaml_block(lines, index, lines[index][0])
            result[key] = nested
        else:
            result[key] = None

    return result, index


def _parse_simple_yaml_list(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[list[Any], int]:
    items: list[Any] = []
    while index < len(lines):
        current_indent, stripped = lines[index]
        if current_indent < indent:
            break
        if current_indent != indent or not stripped.startswith("- "):
            break

        remainder = stripped[2:].strip()
        index += 1

        if not remainder:
            items.append(None)
            continue

        if ":" in remainder:
            key, _, value = remainder.partition(":")
            item: dict[str, Any] = {}
            key = key.strip()
            value = value.strip()
            if value:
                item[key] = _parse_yaml_scalar(value)
            else:
                item[key] = None

            if index < len(lines) and lines[index][0] > current_indent:
                nested, index = _parse_simple_yaml_mapping(lines, index, lines[index][0])
                item.update(nested)
            items.append(item)
            continue

        items.append(_parse_yaml_scalar(remainder))

    return items, index


def _parse_simple_yaml(raw_text: str) -> dict[str, Any]:
    lines: list[tuple[int, str]] = []
    for raw_line in raw_text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        lines.append((indent, raw_line.strip()))

    if not lines:
        return {}

    parsed, _ = _parse_simple_yaml_block(lines, 0, lines[0][0])
    if isinstance(parsed, dict):
        return parsed
    return {}


def _normalize_skill_input_type(raw_type: Any) -> str:
    normalized = str(raw_type or "").strip().lower()
    alias_map = {
        "str": "string",
        "text": "string",
        "integer": "int",
        "number": "float",
        "boolean": "bool",
        "array": "list",
        "dict": "object",
        "map": "object",
    }
    normalized = alias_map.get(normalized, normalized)
    if normalized in {"string", "int", "float", "bool", "list", "object", "any"}:
        return normalized
    return "any"


def _coerce_input_field_spec(field_name: str, raw_field: Any) -> SkillInputFieldSpec | None:
    name = _normalize_text(field_name)
    if not name:
        return None

    if isinstance(raw_field, dict):
        return SkillInputFieldSpec(
            name=name,
            field_type=_normalize_skill_input_type(raw_field.get("type")),
            required=bool(raw_field.get("required")),
            description=str(raw_field.get("description") or "").strip(),
            has_default="default" in raw_field,
            default=raw_field.get("default"),
        )

    return SkillInputFieldSpec(
        name=name,
        field_type="string",
        required=False,
        description=str(raw_field or "").strip(),
    )


def _coerce_skill_input_schema(raw_input_schema: Any) -> tuple[SkillInputFieldSpec, ...]:
    if not isinstance(raw_input_schema, dict):
        return ()

    fields: list[SkillInputFieldSpec] = []
    for field_name, raw_field in raw_input_schema.items():
        spec = _coerce_input_field_spec(str(field_name), raw_field)
        if spec is not None:
            fields.append(spec)
    return tuple(fields)


def _coerce_skill_argument_value(value: Any, field_spec: SkillInputFieldSpec, *, error_type: type[Exception]) -> Any:
    field_name = field_spec.name
    field_type = field_spec.field_type

    if field_type == "any":
        return value
    if value is None:
        return None

    if field_type == "string":
        if isinstance(value, (dict, list)):
            raise error_type(f"Skill argument '{field_name}' must be a string-compatible value.")
        return str(value)

    if field_type == "int":
        if isinstance(value, bool):
            raise error_type(f"Skill argument '{field_name}' must be an int.")
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        try:
            return int(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise error_type(f"Skill argument '{field_name}' must be an int.") from exc

    if field_type == "float":
        if isinstance(value, bool):
            raise error_type(f"Skill argument '{field_name}' must be a float.")
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise error_type(f"Skill argument '{field_name}' must be a float.") from exc

    if field_type == "bool":
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
        raise error_type(f"Skill argument '{field_name}' must be a bool.")

    if field_type == "list":
        if not isinstance(value, list):
            raise error_type(f"Skill argument '{field_name}' must be a list.")
        return value

    if field_type == "object":
        if not isinstance(value, dict):
            raise error_type(f"Skill argument '{field_name}' must be an object.")
        return value

    return value


def validate_skill_arguments(
    skill_spec: SkillSpec,
    raw_arguments: Any,
    *,
    error_type: type[Exception],
) -> dict[str, Any]:
    if raw_arguments is None:
        raw_arguments = {}
    if not isinstance(raw_arguments, dict):
        raise error_type(f"Skill '{skill_spec.name}' requires skill_arguments to be a JSON object.")

    fields_by_name = {field.name: field for field in skill_spec.input_schema}
    unknown_fields = sorted(set(raw_arguments.keys()) - set(fields_by_name.keys()))
    if unknown_fields:
        raise error_type(
            f"Skill '{skill_spec.name}' received unknown skill_arguments: {', '.join(unknown_fields)}"
        )

    validated: dict[str, Any] = {}
    for field_spec in skill_spec.input_schema:
        if field_spec.name in raw_arguments:
            validated[field_spec.name] = _coerce_skill_argument_value(
                raw_arguments[field_spec.name],
                field_spec,
                error_type=error_type,
            )
            continue

        if field_spec.has_default:
            validated[field_spec.name] = copy.deepcopy(field_spec.default)
            continue

        if field_spec.required:
            raise error_type(
                f"Skill '{skill_spec.name}' is missing required skill argument: {field_spec.name}"
            )

    return validated


def _format_skill_input_schema_for_prompt(skill_spec: SkillSpec) -> str:
    if not skill_spec.input_schema:
        return "{}"

    lines: list[str] = []
    for field_spec in skill_spec.input_schema:
        metadata = [
            f"type={field_spec.field_type}",
            f"required={str(field_spec.required).lower()}",
        ]
        if field_spec.has_default:
            metadata.append(f"default={json.dumps(field_spec.default, ensure_ascii=False)}")
        if field_spec.description:
            metadata.append(f"description={field_spec.description}")
        lines.append(f"    - {field_spec.name}: " + "; ".join(metadata))
    return "\n".join(lines)


def _coerce_skill_spec(raw_skill: dict[str, Any]) -> SkillSpec | None:
    name = _normalize_text(raw_skill.get("name"))
    if not name:
        return None

    used_tools = raw_skill.get("used_tools")
    if not isinstance(used_tools, (list, tuple)):
        used_tools = []

    return SkillSpec(
        name=name,
        description=str(raw_skill.get("description") or "").strip(),
        scope=str(raw_skill.get("scope") or "").strip(),
        used_tools=tuple(str(tool).strip() for tool in used_tools if str(tool).strip()),
        output=str(raw_skill.get("output") or "").strip(),
        input_schema=_coerce_skill_input_schema(raw_skill.get("input_schema")),
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

    payload = _parse_simple_yaml(raw_text)
    raw_skills = payload.get("skills") or []
    specs = [_coerce_skill_spec(raw_skill) for raw_skill in raw_skills if isinstance(raw_skill, dict)]
    return [spec for spec in specs if spec is not None]


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


class PythonSkillExecutor:
    def __init__(
        self,
        *,
        skills_directory: Path,
        tool_function_map: dict[str, Callable[..., Any]],
        skill_runtime: dict[str, Any] | None = None,
    ):
        self._skills_directory = skills_directory
        self._tool_function_map = dict(tool_function_map)
        self._skill_runtime = dict(skill_runtime or {})
        self._execute_cache: dict[str, Callable[..., Any]] = {}

    def run(
        self,
        skill_spec: SkillSpec,
        *,
        skill_arguments: dict[str, Any],
        current_message: str,
        intent_decision: IntentDecision,
        recent_context: list[DialogueItem],
        step_goal: str | None = None,
        read_results: list[dict[str, Any]] | None = None,
        max_iterations: int | None = None,
    ) -> SkillExecutionResult:
        del current_message, intent_decision, recent_context, max_iterations
        resolved_tools: dict[str, Callable[..., Any]] = {}
        missing_tools: list[str] = []

        for tool_name in skill_spec.used_tools:
            tool_callable = self._tool_function_map.get(tool_name)
            if tool_callable is None:
                missing_tools.append(tool_name)
            else:
                resolved_tools[tool_name] = tool_callable

        if missing_tools:
            return SkillExecutionResult(
                attempted=True,
                completed=False,
                response=None,
                reason=(
                    f"Skill '{skill_spec.name}' could not start because these required tools are unavailable: "
                    + ", ".join(missing_tools)
                ),
            )

        try:
            validated_arguments = validate_skill_arguments(
                skill_spec,
                skill_arguments,
                error_type=SkillLayerError,
            )
            execute_skill = self._load_execute_skill(skill_spec)
            execute_skill_signature = inspect.signature(execute_skill)
            execute_skill_kwargs = {
                "arguments": validated_arguments,
                "used_tools": resolved_tools,
                "skill_spec": {
                    "name": skill_spec.name,
                    "description": skill_spec.description,
                    "scope": skill_spec.scope,
                    "output": skill_spec.output,
                    "input_schema": [
                        {
                            "name": field_spec.name,
                            "type": field_spec.field_type,
                            "required": field_spec.required,
                            "description": field_spec.description,
                            **({"default": copy.deepcopy(field_spec.default)} if field_spec.has_default else {}),
                        }
                        for field_spec in skill_spec.input_schema
                    ],
                },
            }
            if (
                "skill_runtime" in execute_skill_signature.parameters
                or any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in execute_skill_signature.parameters.values())
            ):
                execute_skill_kwargs["skill_runtime"] = self._skill_runtime
            if (
                step_goal is not None
                and (
                    "step_goal" in execute_skill_signature.parameters
                    or any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in execute_skill_signature.parameters.values())
                )
            ):
                execute_skill_kwargs["step_goal"] = step_goal
            if (
                read_results is not None
                and (
                    "read_results" in execute_skill_signature.parameters
                    or any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in execute_skill_signature.parameters.values())
                )
            ):
                execute_skill_kwargs["read_results"] = copy.deepcopy(read_results)

            payload = execute_skill(
                **execute_skill_kwargs,
            )
        except Exception as exc:
            raise SkillLayerError(f"Skill '{skill_spec.name}' execution failed: {exc}") from exc

        if isinstance(payload, SkillExecutionResult):
            return payload
        if not isinstance(payload, dict):
            raise SkillLayerError(f"Skill '{skill_spec.name}' returned a non-dict result.")

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

    def _load_execute_skill(self, skill_spec: SkillSpec) -> Callable[..., Any]:
        module_path = (self._skills_directory / f"{skill_spec.name}.py").resolve()
        cache_key = str(module_path)
        cached = self._execute_cache.get(cache_key)
        if cached is not None:
            return cached

        if not module_path.exists():
            raise SkillLayerError(
                f"Skill '{skill_spec.name}' is registered but its Python file is missing: {module_path}"
            )

        module_name = "email_agent_skill_" + "".join(
            character if character.isalnum() or character == "_" else "_"
            for character in skill_spec.name
        )
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise SkillLayerError(f"Skill '{skill_spec.name}' could not be loaded from {module_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        execute_skill = getattr(module, "execute_skill", None)
        if not callable(execute_skill):
            raise SkillLayerError(
                f"Skill '{skill_spec.name}' must expose a callable execute_skill(arguments=..., used_tools=..., skill_spec=...)"
            )

        self._execute_cache[cache_key] = execute_skill
        return execute_skill


class IntentLayerOrchestrator:
    def __init__(
        self,
        *,
        main_agent: SupportsInput,
        intent_agent: SupportsInput,
        planner_agent: SupportsInput,
        skill_input_resolver_agent: SupportsInput,
        finalizer_agent: SupportsInput,
        skill_executor: SupportsSkillExecution | None,
        memory_store: MarkdownMemoryStore,
        skill_registry_path: Path,
        writing_style_path: Path | None = None,
        timezone_name: str | None = None,
    ):
        self._main_agent = main_agent
        self._intent_agent = intent_agent
        self._planner_agent = planner_agent
        self._skill_input_resolver_agent = skill_input_resolver_agent
        self._finalizer_agent = finalizer_agent
        self._skill_executor = skill_executor
        self._memory_store = memory_store
        self._skill_registry_path = skill_registry_path
        self._writing_style_path = writing_style_path
        self._timezone_name = _normalize_text(timezone_name) or None
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
            writing_style_markdown = self._read_writing_style_markdown()
            date_grounding = self._build_date_grounding()

            intent_decision = self._analyze_intent(
                current_message=prompt,
                older_context=older_context,
                recent_context=recent_context,
                profile_markdown=profile_markdown,
                habits_markdown=habits_markdown,
                writing_style_markdown=writing_style_markdown,
                date_grounding=date_grounding,
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
                execution_plan = self._plan_execution(
                    intent_decision=intent_decision,
                    current_message=prompt,
                    older_context=older_context,
                    recent_context=recent_context,
                    available_skills=available_skills,
                )
                self._log_route(
                    "planner",
                    confidence=intent_decision.no_execution_confidence,
                    intent=intent_decision.intent,
                    reason=execution_plan.reason,
                    step_count=len(execution_plan.steps),
                    steps=[self._serialize_plan_step(step) for step in execution_plan.steps],
                    registered_skills=len(available_skills),
                )
                step_results = self._execute_plan(
                    execution_plan=execution_plan,
                    available_skills=available_skills,
                    user_message=prompt,
                    intent_decision=intent_decision,
                    older_context=older_context,
                    recent_context=recent_context,
                    date_grounding=date_grounding,
                    max_iterations=max_iterations,
                    session=session,
                    images=images,
                    files=files,
                )
                self._log_route(
                    "finalizer_started",
                    step_count=len(step_results),
                )
                response, finalizer_reason = self._finalize_execution(
                    intent_decision=intent_decision,
                    older_context=older_context,
                    recent_context=recent_context,
                    step_results=step_results,
                )
                self._log_route(
                    "finalizer_finished",
                    reason=finalizer_reason,
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
        writing_style_markdown: str,
        date_grounding: str,
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
                "[WRITING_STYLE]",
                writing_style_markdown,
                "[DATE_GROUNDING]",
                date_grounding,
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
            raise IntentLayerError("Intent layer returned no_execution_confidence > 9.0 without a final_response.")
        if confidence <= DIRECT_RESPONSE_THRESHOLD and final_response is not None:
            raise IntentLayerError("Intent layer returned final_response even though no_execution_confidence <= 9.0.")
        if confidence <= DIRECT_RESPONSE_THRESHOLD:
            final_response = None

        return IntentDecision(
            intent=intent,
            no_execution_confidence=confidence,
            final_response=final_response,
            reason=_require_non_empty_string(payload.get("reason"), field_name="reason", error_type=IntentLayerError),
            user_update_summary=str(payload.get("user_update_summary") or "").strip(),
        )

    def _read_writing_style_markdown(self) -> str:
        path = self._writing_style_path
        if path is None:
            return DEFAULT_WRITING_STYLE
        return MarkdownMemoryStore._read_or_default(path, DEFAULT_WRITING_STYLE)

    def _build_date_grounding(self) -> str:
        timezone_name = self._timezone_name or "system-local"
        timezone = None
        if self._timezone_name:
            try:
                timezone = ZoneInfo(self._timezone_name)
            except ZoneInfoNotFoundError:
                timezone = None

        now = datetime.now(timezone) if timezone is not None else datetime.now().astimezone()
        today = now.date()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)
        day_after_tomorrow = today + timedelta(days=2)

        return "\n".join(
            [
                f"timezone: {timezone_name}",
                f"today: {today.isoformat()}",
                f"tomorrow: {tomorrow.isoformat()}",
                f"yesterday: {yesterday.isoformat()}",
                f"day_after_tomorrow: {day_after_tomorrow.isoformat()}",
            ]
        )

    @staticmethod
    def _serialize_plan_step(step: PlannedStep) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "step_id": step.step_id,
            "type": step.step_type,
            "goal": step.goal,
            "reads": list(step.reads),
        }
        if step.name:
            payload["name"] = step.name
        return payload

    @staticmethod
    def _build_skills_block(available_skills: list[SkillSpec]) -> str:
        skill_blocks: list[str] = []
        for spec in available_skills:
            lines = [
                f"- skill_name: {spec.name}",
                f"  description: {spec.description or '(empty)'}",
                f"  scope: {spec.scope or '(empty)'}",
            ]
            if spec.used_tools:
                lines.append(f"  used_tools: {', '.join(spec.used_tools)}")
            lines.append("  input_schema:")
            lines.append(_format_skill_input_schema_for_prompt(spec))
            if spec.output:
                lines.append(f"  output: {spec.output}")
            skill_blocks.append("\n".join(lines))
        return "\n\n".join(skill_blocks)

    def _build_default_agent_plan(
        self,
        *,
        intent_decision: IntentDecision,
        reason: str,
    ) -> ExecutionPlan:
        return ExecutionPlan(
            steps=(
                PlannedStep(
                    step_id="step_1",
                    step_type="agent",
                    name="main_agent",
                    goal=intent_decision.intent,
                    reads=(),
                ),
            ),
            reason=reason,
        )

    def _plan_execution(
        self,
        *,
        intent_decision: IntentDecision,
        current_message: str,
        older_context: list[DialogueItem],
        recent_context: list[DialogueItem],
        available_skills: list[SkillSpec],
    ) -> ExecutionPlan:
        if not available_skills:
            return self._build_default_agent_plan(
                intent_decision=intent_decision,
                reason="No skills are registered in skills/registry.yaml.",
            )
        if self._planner_agent is None:
            raise SkillLayerError("Planner agent is not configured.")

        prompt = "\n\n".join(
            [
                "[INTENT]",
                intent_decision.intent,
                "[CURRENT_USER_MESSAGE]",
                current_message.strip(),
                "[OLDER_CONTEXT]",
                format_context(older_context),
                "[RECENT_CONTEXT]",
                format_context(recent_context),
                "[CURRENT_SESSION_STATE]",
                "No explicit session state is available in this implementation.",
                "[AVAILABLE_SKILLS]",
                self._build_skills_block(available_skills),
            ]
        )

        try:
            payload = _extract_json_payload(self._planner_agent.input(prompt, max_iterations=1))
        except Exception as exc:
            raise SkillLayerError(f"Planner execution failed: {exc}") from exc

        raw_steps = payload.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            raise SkillLayerError("Planner must return a non-empty steps array.")
        reason = _require_non_empty_string(payload.get("reason"), field_name="reason", error_type=SkillLayerError)
        skills_by_name = {spec.name: spec for spec in available_skills}
        seen_step_ids: set[str] = set()
        steps: list[PlannedStep] = []

        for raw_step in raw_steps:
            if not isinstance(raw_step, dict):
                raise SkillLayerError("Each planner step must be a JSON object.")

            step_id = _require_non_empty_string(
                raw_step.get("step_id"),
                field_name="step_id",
                error_type=SkillLayerError,
            )
            if step_id in seen_step_ids:
                raise SkillLayerError(f"Planner returned duplicate step_id: {step_id}")

            step_type = _normalize_text(raw_step.get("type")).lower()
            if step_type not in {"skill", "agent"}:
                raise SkillLayerError(f"Planner returned unsupported step type '{step_type}' for {step_id}.")

            goal = _require_non_empty_string(raw_step.get("goal"), field_name="goal", error_type=SkillLayerError)

            raw_reads = raw_step.get("reads")
            if raw_reads is None:
                reads: tuple[str, ...] = ()
            else:
                if not isinstance(raw_reads, list):
                    raise SkillLayerError(f"Planner step '{step_id}' must use a reads array.")
                reads_list: list[str] = []
                for raw_read in raw_reads:
                    read_step_id = _require_non_empty_string(
                        raw_read,
                        field_name=f"{step_id}.reads[]",
                        error_type=SkillLayerError,
                    )
                    if read_step_id not in seen_step_ids:
                        raise SkillLayerError(
                            f"Planner step '{step_id}' references unknown or future step '{read_step_id}'."
                        )
                    reads_list.append(read_step_id)
                reads = tuple(reads_list)

            name: str | None = None
            if step_type == "skill":
                name = _require_non_empty_string(
                    raw_step.get("name"),
                    field_name="name",
                    error_type=SkillLayerError,
                )
                if name not in skills_by_name:
                    raise SkillLayerError(f"Planner returned unknown skill name '{name}' for {step_id}.")
            elif raw_step.get("name") is not None:
                name = str(raw_step.get("name") or "").strip() or None

            if raw_step.get("skill_arguments") is not None:
                raise SkillLayerError(
                    f"Planner step '{step_id}' must not include skill_arguments. Skill arguments belong to the skill input resolver."
                )

            steps.append(
                PlannedStep(
                    step_id=step_id,
                    step_type=step_type,
                    name=name,
                    goal=goal,
                    reads=reads,
                )
            )
            seen_step_ids.add(step_id)

        return ExecutionPlan(steps=tuple(steps), reason=reason)

    def _resolve_skill_arguments(
        self,
        *,
        skill_spec: SkillSpec,
        intent_decision: IntentDecision,
        step: PlannedStep,
        read_results: tuple[StepExecutionResult, ...],
    ) -> dict[str, Any]:
        serialized_read_results = [serialize_step_result(result) for result in read_results]
        prompt = "\n\n".join(
            [
                "[INTENT]",
                intent_decision.intent,
                "[STEP_GOAL]",
                step.goal,
                "[CURRENT_SKILL]",
                "\n".join(
                    [
                        f"skill_name: {skill_spec.name}",
                        f"skill_description: {skill_spec.description or '(empty)'}",
                        f"skill_scope: {skill_spec.scope or '(empty)'}",
                        "skill_input_schema:",
                        _format_skill_input_schema_for_prompt(skill_spec),
                    ]
                ),
                "[READ_RESULTS]",
                json.dumps(serialized_read_results, ensure_ascii=False, indent=2),
            ]
        )

        try:
            raw_response = self._skill_input_resolver_agent.input(prompt, max_iterations=1)
            payload = _extract_json_payload(raw_response)
        except Exception as exc:
            raise SkillLayerError(f"Skill input resolver failed for '{skill_spec.name}': {exc}") from exc

        skill_arguments = payload.get("skill_arguments")
        if not isinstance(skill_arguments, dict):
            raise SkillLayerError(f"Skill input resolver must return skill_arguments as a JSON object for '{skill_spec.name}'.")

        validated_arguments = validate_skill_arguments(
            skill_spec,
            skill_arguments,
            error_type=SkillLayerError,
        )
        self._log_route(
            "skill_input_resolved",
            step_id=step.step_id,
            skill_name=skill_spec.name,
            skill_arguments=validated_arguments,
        )
        return validated_arguments

    def _execute_skill_step(
        self,
        *,
        step: PlannedStep,
        skill_spec: SkillSpec,
        read_results: tuple[StepExecutionResult, ...],
        user_message: str,
        intent_decision: IntentDecision,
        recent_context: list[DialogueItem],
        max_iterations: int | None,
    ) -> StepExecutionResult:
        if self._skill_executor is None:
            raise SkillLayerError("Skill executor is not configured.")

        skill_arguments = self._resolve_skill_arguments(
            skill_spec=skill_spec,
            intent_decision=intent_decision,
            step=step,
            read_results=read_results,
        )
        self._log_route(
            "skill_execution_started",
            step_id=step.step_id,
            skill_name=skill_spec.name,
            used_tools=", ".join(skill_spec.used_tools),
            skill_arguments=skill_arguments,
        )
        execute_kwargs: dict[str, Any] = {
            "skill_arguments": skill_arguments,
            "current_message": user_message,
            "intent_decision": intent_decision,
            "recent_context": recent_context,
            "max_iterations": max_iterations,
        }
        run_signature = inspect.signature(self._skill_executor.run)
        if (
            "step_goal" in run_signature.parameters
            or any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in run_signature.parameters.values())
        ):
            execute_kwargs["step_goal"] = step.goal
        if (
            "read_results" in run_signature.parameters
            or any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in run_signature.parameters.values())
        ):
            execute_kwargs["read_results"] = [serialize_step_result(result) for result in read_results]

        skill_execution_result = self._skill_executor.run(
            skill_spec,
            **execute_kwargs,
        )
        self._log_route(
            "skill_execution_finished",
            step_id=step.step_id,
            skill_name=skill_spec.name,
            completed=skill_execution_result.completed,
            reason=skill_execution_result.reason,
        )
        artifact_summary = str(skill_execution_result.response or "").strip()
        if not artifact_summary:
            artifact_summary = skill_execution_result.reason
        status = "completed" if skill_execution_result.completed and skill_execution_result.response else "failed"
        return StepExecutionResult(
            step_id=step.step_id,
            step_type="skill",
            name=skill_spec.name,
            status=status,
            artifact={
                "kind": "skill_result",
                "summary": artifact_summary,
                "data": {
                    "response": skill_execution_result.response or "",
                    "completed": skill_execution_result.completed,
                    "skill_arguments": copy.deepcopy(skill_arguments),
                },
            },
            reason=skill_execution_result.reason,
        )

    def _execute_agent_step(
        self,
        *,
        step: PlannedStep,
        read_results: tuple[StepExecutionResult, ...],
        user_message: str,
        intent_decision: IntentDecision,
        older_context: list[DialogueItem],
        recent_context: list[DialogueItem],
        date_grounding: str,
        max_iterations: int | None,
        session: dict[str, Any] | None,
        images: list[str] | None,
        files: list[dict[str, Any]] | None,
    ) -> StepExecutionResult:
        self._log_route(
            "main_agent",
            step_id=step.step_id,
            confidence=intent_decision.no_execution_confidence,
            intent=intent_decision.intent,
            goal=step.goal,
            reads=list(step.reads),
        )
        handoff_prompt = "\n".join(
            [
                "[SERIAL_AGENT_STEP]",
                f"intent: {intent_decision.intent}",
                f"step_id: {step.step_id}",
                f"step_goal: {step.goal}",
                "",
                "[STEP_BOUNDARY]",
                "Execute only the current step_goal.",
                "Do not do work for any other requested task from the original user message.",
                "Do not preemptively perform later planner steps.",
                "Assume other steps and the finalizer will handle the rest.",
                "",
                "[READ_RESULTS]",
                json.dumps([serialize_step_result(result) for result in read_results], ensure_ascii=False, indent=2),
                "",
                "[DATE_GROUNDING]",
                date_grounding,
                "",
                "[OLDER_CONTEXT]",
                format_context(older_context),
                "",
                "[RECENT_CONTEXT]",
                format_context(recent_context),
                "",
                "[USER_MESSAGE]",
                user_message.strip(),
            ]
        ).strip()

        if isinstance(self.current_session, dict):
            setattr(self._main_agent, "current_session", self.current_session)
        raw_response = self._main_agent.input(
            handoff_prompt,
            max_iterations=max_iterations,
            session=session,
            images=images,
            files=files,
        )
        updated_session = getattr(self._main_agent, "current_session", None)
        if isinstance(updated_session, dict):
            self.current_session = updated_session

        response_text = str(raw_response or "").strip()
        if not response_text:
            raise SkillLayerError("Main agent step returned an empty response.")

        return StepExecutionResult(
            step_id=step.step_id,
            step_type="agent",
            name=step.name or "main_agent",
            status="completed",
            artifact={
                "response": response_text,
            },
            reason="Main agent step completed.",
        )

    def _execute_plan(
        self,
        *,
        execution_plan: ExecutionPlan,
        available_skills: list[SkillSpec],
        user_message: str,
        intent_decision: IntentDecision,
        older_context: list[DialogueItem],
        recent_context: list[DialogueItem],
        date_grounding: str,
        max_iterations: int | None,
        session: dict[str, Any] | None,
        images: list[str] | None,
        files: list[dict[str, Any]] | None,
    ) -> tuple[StepExecutionResult, ...]:
        skills_by_name = {skill.name: skill for skill in available_skills}
        results_by_step_id: dict[str, StepExecutionResult] = {}
        step_results: list[StepExecutionResult] = []

        for step in execution_plan.steps:
            read_results = tuple(results_by_step_id[step_id] for step_id in step.reads)
            self._log_route(
                "step_execution_started",
                step_id=step.step_id,
                type=step.step_type,
                name=step.name,
                goal=step.goal,
                reads=list(step.reads),
            )
            try:
                if step.step_type == "skill":
                    if not step.name:
                        raise SkillLayerError(f"Skill step '{step.step_id}' is missing a skill name.")
                    skill_spec = skills_by_name.get(step.name)
                    if skill_spec is None:
                        raise SkillLayerError(f"Skill step '{step.step_id}' references unknown skill '{step.name}'.")
                    step_result = self._execute_skill_step(
                        step=step,
                        skill_spec=skill_spec,
                        read_results=read_results,
                        user_message=user_message,
                        intent_decision=intent_decision,
                        recent_context=recent_context,
                        max_iterations=max_iterations,
                    )
                else:
                    step_result = self._execute_agent_step(
                        step=step,
                        read_results=read_results,
                        user_message=user_message,
                        intent_decision=intent_decision,
                        older_context=older_context,
                        recent_context=recent_context,
                        date_grounding=date_grounding,
                        max_iterations=max_iterations,
                        session=session,
                        images=images,
                        files=files,
                    )
            except Exception as exc:
                step_result = StepExecutionResult(
                    step_id=step.step_id,
                    step_type=step.step_type,
                    name=step.name or ("main_agent" if step.step_type == "agent" else None),
                    status="failed",
                    artifact={"error": str(exc)},
                    reason=str(exc),
                )

            results_by_step_id[step.step_id] = step_result
            step_results.append(step_result)
            self._log_route(
                "step_execution_finished",
                step_id=step_result.step_id,
                type=step_result.step_type,
                name=step_result.name,
                status=step_result.status,
                reason=step_result.reason,
            )

        return tuple(step_results)

    def _finalize_execution(
        self,
        *,
        intent_decision: IntentDecision,
        older_context: list[DialogueItem],
        recent_context: list[DialogueItem],
        step_results: tuple[StepExecutionResult, ...],
    ) -> tuple[str, str]:
        prompt = "\n\n".join(
            [
                "[INTENT]",
                intent_decision.intent,
                "[OLDER_CONTEXT]",
                format_context(older_context),
                "[RECENT_CONTEXT]",
                format_context(recent_context),
                "[ALL_STEP_RESULTS]",
                json.dumps([serialize_step_result(result) for result in step_results], ensure_ascii=False, indent=2),
            ]
        )

        try:
            raw_response = self._finalizer_agent.input(prompt, max_iterations=1)
            payload = _extract_json_payload(raw_response)
        except Exception as exc:
            raise SkillLayerError(f"Finalizer execution failed: {exc}") from exc

        final_response = _require_non_empty_string(
            payload.get("final_response"),
            field_name="final_response",
            error_type=SkillLayerError,
        )
        reason = str(payload.get("reason") or "Finalizer completed.").strip() or "Finalizer completed."
        return final_response, reason
