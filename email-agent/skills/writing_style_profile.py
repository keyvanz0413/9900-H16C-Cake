from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SENT_EMAIL_SAMPLE_SIZE = 30
DEFAULT_WRITING_STYLE_CONTENT = """# Writing Style

- No writing style profile yet.
"""


def _extract_json_payload(raw_text: str) -> dict[str, Any]:
    text = str(raw_text or "").strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 3:
            text = parts[1].replace("json", "", 1).strip()

    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in writing style writer response.")

    payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("Writing style writer response JSON was not an object.")
    return payload


def _require_non_empty_string(value: Any, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"Missing or empty required field: {field_name}")
    return normalized


def _resolve_writing_style_path(skill_runtime: dict[str, Any] | None) -> Path:
    runtime = skill_runtime or {}
    paths = runtime.get("paths") or {}
    raw_path = paths.get("writing_style_markdown")
    if raw_path:
        return Path(raw_path)
    return Path(__file__).resolve().parent.parent / "WRITING_STYLE.md"


def _read_existing_writing_style(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, DEFAULT_WRITING_STYLE_CONTENT.strip()

    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return False, DEFAULT_WRITING_STYLE_CONTENT.strip()
    return True, content


def execute_skill(*, arguments, used_tools, skill_spec, skill_runtime=None):
    del arguments

    runtime = skill_runtime or {}
    agents = runtime.get("agents") or {}
    writer_agent = agents.get("writing_style_writer")
    if writer_agent is None:
        raise RuntimeError("writing_style_writer agent is not available in skill runtime.")

    writing_style_path = _resolve_writing_style_path(runtime)
    had_existing_style, current_writing_style = _read_existing_writing_style(writing_style_path)

    print(
        f"[skill:writing_style_profile] start existing_style={'yes' if had_existing_style else 'no'} path={writing_style_path}",
        flush=True,
    )

    sent_kwargs = {"max_results": SENT_EMAIL_SAMPLE_SIZE}
    print(f"[skill:writing_style_profile] calling get_sent_emails with {sent_kwargs}", flush=True)
    sent_emails_result = used_tools["get_sent_emails"](**sent_kwargs)
    sent_emails_text = str(sent_emails_result or "").strip() or "(empty)"
    print("[skill:writing_style_profile] finished get_sent_emails", flush=True)

    prompt = "\n\n".join(
        [
            "[UPDATE_MODE]",
            "update_existing_profile" if had_existing_style else "create_new_profile",
            "[CURRENT_WRITING_STYLE]",
            current_writing_style,
            "[RECENT_SENT_EMAILS]",
            sent_emails_text,
        ]
    )

    print("[skill:writing_style_profile] writing_style_writer_started", flush=True)
    raw_response = writer_agent.input(prompt, max_iterations=1)
    payload = _extract_json_payload(raw_response)
    print("[skill:writing_style_profile] writing_style_writer_finished", flush=True)

    writing_style_markdown = _require_non_empty_string(payload.get("writing_style_markdown"), "writing_style_markdown")
    user_summary = _require_non_empty_string(payload.get("user_summary"), "user_summary")
    reason = _require_non_empty_string(payload.get("reason"), "reason")

    writing_style_path.parent.mkdir(parents=True, exist_ok=True)
    writing_style_path.write_text(writing_style_markdown.rstrip() + "\n", encoding="utf-8")
    print(f"[skill:writing_style_profile] wrote writing style markdown to {writing_style_path}", flush=True)

    action = "updated" if had_existing_style else "created"
    lines = [
        "[WRITING_STYLE_PROFILE_UPDATED]",
        f"skill_name: {skill_spec.get('name', 'writing_style_profile')}",
        f"action: {action}",
        f"path: {writing_style_path}",
        f"sample_size: {SENT_EMAIL_SAMPLE_SIZE}",
        "",
        "[WRITING_STYLE_SUMMARY]",
        user_summary,
        "",
        "[WRITING_STYLE_MARKDOWN]",
        writing_style_markdown,
    ]

    return {
        "completed": True,
        "response": "\n".join(lines).strip(),
        "reason": reason,
    }
