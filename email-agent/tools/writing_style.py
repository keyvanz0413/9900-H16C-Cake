"""Writing style profile tool.

This module stores a compact writing-style profile under email-agent/data so
the agent can reuse the user's style across sessions. It never stores raw sent
email bodies; it only saves summarized style signals.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


_email_tool: Any | None = None
_profile_path: Path = Path(__file__).resolve().parents[1] / "data" / "writing_style_profile.json"


def configure_writing_style(email_tool: Any | None = None, profile_path: str = "") -> None:
    """Attach provider tools and optionally override the local profile path."""
    global _email_tool, _profile_path
    _email_tool = email_tool
    if profile_path:
        _profile_path = Path(profile_path)


def get_writing_style_profile(
    sample_count: int = 20,
    recipient_query: str = "",
    purpose: str = "",
    use_saved_profile: bool = True,
    refresh_profile: bool = False,
    stale_after_days: int = 7,
) -> str:
    """Return the user's structured writing style profile.

    Args:
        sample_count: Number of sent emails to inspect when learning or refreshing.
        recipient_query: Optional recipient name/email to prefer specific samples.
        purpose: Optional draft purpose for audience adjustment notes.
        use_saved_profile: Whether to read the saved data profile first.
        refresh_profile: Whether the user has confirmed relearning from sent mail.
        stale_after_days: Number of days before a saved profile needs refresh.

    Returns:
        JSON string with profile state, freshness metadata, profile content, and
        recommended next action. This tool does not send email.
    """
    sample_count = _clamp_int(sample_count, default=20, minimum=1, maximum=100)
    stale_after_days = _clamp_int(stale_after_days, default=7, minimum=1, maximum=365)
    saved_profile, saved_error = _load_saved_profile() if use_saved_profile else (None, "")

    if refresh_profile:
        return _refresh_profile(
            sample_count=sample_count,
            recipient_query=recipient_query,
            purpose=purpose,
            stale_after_days=stale_after_days,
            previous_error=saved_error,
        )

    if saved_profile:
        return _to_json(
            _profile_response(
                profile_state="stale" if _is_stale(saved_profile, stale_after_days) else "fresh",
                profile=saved_profile,
                sample_count_requested=sample_count,
                recipient_query=recipient_query,
                purpose=purpose,
                stale_after_days=stale_after_days,
                saved_profile_used=True,
                limitations=[],
            )
        )

    limitations = []
    if saved_error:
        limitations.append(saved_error)
    return _to_json(
        {
            "intent": "writing_style_profile",
            "source": {
                "sample_count_requested": sample_count,
                "sample_count_used": 0,
                "scope": "saved_profile",
                "recipient_specific": bool(recipient_query),
                "saved_profile_used": False,
                "profile_path": _display_profile_path(),
                "profile_created_at": "",
                "profile_last_updated": "",
                "profile_age_days": None,
                "is_stale": False,
                "stale_after_days": stale_after_days,
            },
            "profile": _empty_profile(),
            "audience_adjustment": _audience_adjustment(recipient_query, purpose),
            "profile_state": "unavailable" if saved_error else "missing",
            "requires_user_confirmation": True,
            "recommended_agent_action": (
                "Ask the user whether to relearn their writing style from recent sent emails."
            ),
            "confidence": "low",
            "limitations": limitations
            + [
                "No saved writing style profile is available.",
                "Do not analyze sent emails until the user confirms learning their style.",
            ],
            "safety_notes": [
                "No email has been sent.",
                "No draft has been created in the email provider.",
                "No sent email body content has been saved.",
            ],
        }
    )


def _refresh_profile(
    sample_count: int,
    recipient_query: str,
    purpose: str,
    stale_after_days: int,
    previous_error: str,
) -> str:
    """Learn a style profile from sent emails and save only summarized signals."""
    if _email_tool is None:
        return _to_json(
            {
                "intent": "writing_style_profile",
                "source": {
                    "sample_count_requested": sample_count,
                    "sample_count_used": 0,
                    "scope": "sent_emails",
                    "recipient_specific": bool(recipient_query),
                    "saved_profile_used": False,
                    "profile_path": _display_profile_path(),
                    "profile_created_at": "",
                    "profile_last_updated": "",
                    "profile_age_days": None,
                    "is_stale": False,
                    "stale_after_days": stale_after_days,
                },
                "profile": _empty_profile(),
                "audience_adjustment": _audience_adjustment(recipient_query, purpose),
                "profile_state": "unavailable",
                "requires_user_confirmation": True,
                "recommended_agent_action": "Explain that no email provider is configured.",
                "confidence": "low",
                "limitations": ["No email provider tool is configured."],
                "safety_notes": [
                    "No email has been sent.",
                    "No draft has been created in the email provider.",
                    "No sent email body content has been saved.",
                ],
            }
        )

    raw_sent = _safe_call(lambda: _email_tool.get_sent_emails(max_results=sample_count), fallback="")
    sent_items = _parse_provider_email_list(raw_sent)
    samples = _build_samples(raw_sent, sent_items, recipient_query)
    profile = _build_profile(samples)
    now = datetime.now().strftime("%Y-%m-%d")
    saved_data = {
        "version": 1,
        "created_at": now,
        "last_updated": now,
        "stale_after_days": stale_after_days,
        "source": {
            "sample_count_used": len(samples),
            "scope": "sent_emails",
            "recipient_specific_profiles": [],
        },
        "profile": profile,
        "confidence": _confidence_for_samples(len(samples)),
        "limitations": _profile_limitations(len(samples), previous_error),
    }
    save_error = _save_profile(saved_data)
    profile_state = "refreshed" if not save_error else "unavailable"
    limitations = list(saved_data["limitations"])
    if save_error:
        limitations.append(save_error)

    return _to_json(
        _profile_response(
            profile_state=profile_state,
            profile=saved_data,
            sample_count_requested=sample_count,
            recipient_query=recipient_query,
            purpose=purpose,
            stale_after_days=stale_after_days,
            saved_profile_used=False,
            limitations=limitations,
        )
    )


def _load_saved_profile() -> tuple[dict[str, Any] | None, str]:
    """Load the local JSON profile and validate required fields."""
    if not _profile_path.exists():
        return None, ""
    try:
        data = json.loads(_profile_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, f"Saved writing style profile could not be read: {exc}"

    required = ("created_at", "last_updated", "profile", "confidence")
    missing = [field for field in required if field not in data]
    if missing:
        return None, f"Saved writing style profile is missing required field(s): {', '.join(missing)}"
    if not isinstance(data.get("profile"), dict):
        return None, "Saved writing style profile has invalid profile data."
    return data, ""


def _save_profile(data: dict[str, Any]) -> str:
    """Persist summarized style data to email-agent/data."""
    try:
        _profile_path.parent.mkdir(parents=True, exist_ok=True)
        _profile_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        return f"Writing style profile could not be saved: {exc}"
    return ""


def _profile_response(
    profile_state: str,
    profile: dict[str, Any],
    sample_count_requested: int,
    recipient_query: str,
    purpose: str,
    stale_after_days: int,
    saved_profile_used: bool,
    limitations: list[str],
) -> dict[str, Any]:
    """Create the public JSON response from a saved or refreshed profile."""
    profile_age_days = _profile_age_days(profile)
    is_stale = profile_state == "stale"
    sample_count_used = int(profile.get("source", {}).get("sample_count_used", 0) or 0)
    return {
        "intent": "writing_style_profile",
        "source": {
            "sample_count_requested": sample_count_requested,
            "sample_count_used": sample_count_used,
            "scope": profile.get("source", {}).get("scope", "saved_profile"),
            "recipient_specific": bool(recipient_query),
            "saved_profile_used": saved_profile_used,
            "profile_path": _display_profile_path(),
            "profile_created_at": profile.get("created_at", ""),
            "profile_last_updated": profile.get("last_updated", ""),
            "profile_age_days": profile_age_days,
            "is_stale": is_stale,
            "stale_after_days": stale_after_days,
        },
        "profile": profile.get("profile", _empty_profile()),
        "audience_adjustment": _audience_adjustment(recipient_query, purpose),
        "profile_state": profile_state,
        "requires_user_confirmation": profile_state in ("missing", "stale", "unavailable"),
        "recommended_agent_action": _recommended_action(profile_state),
        "confidence": profile.get("confidence", "low"),
        "limitations": limitations or profile.get("limitations", []),
        "safety_notes": [
            "No email has been sent.",
            "No draft has been created in the email provider.",
            "Saved data contains summarized style signals, not raw sent email bodies.",
        ],
    }


def _build_samples(raw_sent: str, sent_items: list[dict[str, Any]], recipient_query: str) -> list[dict[str, str]]:
    """Build sanitized samples from provider summaries without keeping full bodies."""
    if recipient_query:
        recipient_lower = recipient_query.lower()
        matched = [
            item for item in sent_items
            if recipient_lower in _sample_haystack(item).lower()
        ]
        if matched:
            sent_items = matched

    if sent_items:
        return [
            {
                "subject": item.get("subject", ""),
                "preview": item.get("preview", ""),
                "recipient": item.get("sender", ""),
            }
            for item in sent_items
        ]

    fallback_text = _strip_provider_counts(raw_sent)
    return [{"subject": "", "preview": line.strip(), "recipient": ""} for line in fallback_text.splitlines() if line.strip()]


def _build_profile(samples: list[dict[str, str]]) -> dict[str, Any]:
    """Infer a compact writing style profile from sanitized sent-mail samples."""
    combined = "\n".join(f"{sample.get('subject', '')}\n{sample.get('preview', '')}" for sample in samples)
    lowered = combined.lower()
    words = re.findall(r"\b[\w']+\b", combined)
    sentences = [part.strip() for part in re.split(r"[.!?]+", combined) if part.strip()]
    greetings = _extract_patterns(combined, _GREETING_PATTERNS, default=["Hi {name}"])
    sign_offs = _extract_patterns(combined, _SIGN_OFF_PATTERNS, default=["Best"])
    common_phrases = _common_phrases(lowered)

    return {
        "tone": _tone(lowered),
        "formality": _formality(lowered),
        "directness": _directness(lowered),
        "warmth": _warmth(lowered),
        "greeting_patterns": greetings,
        "sign_off_patterns": sign_offs,
        "sentence_style": {
            "average_length": _average_sentence_length(words, sentences),
            "uses_contractions": bool(re.search(r"\b\w+'(m|re|ve|ll|d|t|s)\b", lowered)),
            "uses_bullets": "often" if re.search(r"(^|\n)\s*[-*]\s+", combined) else "rarely",
            "uses_exclamation_marks": _frequency_label(combined.count("!"), len(samples)),
        },
        "structure": _structure(lowered),
        "common_phrasing": common_phrases,
        "avoid": _avoidance_rules(lowered),
    }


def _parse_provider_email_list(raw: str) -> list[dict[str, Any]]:
    """Parse provider read/search results into lightweight email records."""
    items: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for line in raw.splitlines():
        item_match = re.match(r"\s*(\d+)\.\s*(?:\[UNREAD\]\s*)?(?:From|To):\s*(.+)", line)
        if item_match:
            if current:
                items.append(current)
            current = {
                "index": int(item_match.group(1)),
                "sender": item_match.group(2).strip(),
                "subject": "",
                "date": "",
                "preview": "",
                "id": "",
            }
            continue

        if current is None:
            continue

        stripped = line.strip()
        for key, prefix in (
            ("subject", "Subject:"),
            ("date", "Date:"),
            ("preview", "Preview:"),
            ("id", "ID:"),
        ):
            if stripped.startswith(prefix):
                current[key] = stripped[len(prefix):].strip()
                break

    if current:
        items.append(current)
    return items


_GREETING_PATTERNS = {
    "hi": "Hi {name}",
    "hey": "Hey {name}",
    "dear": "Dear {name}",
    "hello": "Hello {name}",
}

_SIGN_OFF_PATTERNS = {
    "best": "Best",
    "thanks": "Thanks",
    "thank you": "Thank you",
    "cheers": "Cheers",
    "regards": "Regards",
    "best regards": "Best regards",
}


def _extract_patterns(text: str, patterns: dict[str, str], default: list[str]) -> list[str]:
    """Find common greeting or sign-off patterns."""
    lowered = text.lower()
    matches = []
    for raw, normalized in patterns.items():
        if re.search(rf"(^|\n)\s*{re.escape(raw)}\b", lowered) or re.search(rf"\b{re.escape(raw)}[,!\n]", lowered):
            matches.append(normalized)
    return matches[:3] or default


def _tone(lowered: str) -> str:
    """Infer a readable tone label from common signals."""
    if any(term in lowered for term in ("appreciate", "thanks", "thank you", "happy to", "sounds good")):
        return "polite, concise, and collaborative"
    if any(term in lowered for term in ("please find", "regards", "sincerely")):
        return "professional and formal"
    return "concise and direct"


def _formality(lowered: str) -> str:
    """Estimate formality from phrase choices."""
    formal_hits = sum(lowered.count(term) for term in ("dear", "regards", "sincerely", "please find", "thank you"))
    casual_hits = sum(lowered.count(term) for term in ("hey", "thanks", "cheers", "sounds good", "happy to"))
    if formal_hits > casual_hits + 1:
        return "high"
    if casual_hits > formal_hits + 1:
        return "low-to-medium"
    return "medium"


def _directness(lowered: str) -> str:
    """Estimate whether the user tends to give clear next steps."""
    if any(term in lowered for term in ("let me know", "i can", "i will", "please", "could you", "can you")):
        return "high"
    return "medium"


def _warmth(lowered: str) -> str:
    """Estimate friendliness from gratitude and softening phrases."""
    hits = sum(lowered.count(term) for term in ("thanks", "thank you", "appreciate", "happy", "great", "sounds good"))
    if hits >= 4:
        return "high"
    if hits >= 1:
        return "medium"
    return "low-to-medium"


def _average_sentence_length(words: list[str], sentences: list[str]) -> str:
    """Classify average sentence length as short, medium, or long."""
    if not sentences:
        return "short"
    average = len(words) / max(1, len(sentences))
    if average <= 12:
        return "short"
    if average <= 22:
        return "medium"
    return "long"


def _frequency_label(count: int, sample_count: int) -> str:
    """Convert a count into a simple frequency label."""
    if count == 0:
        return "rarely"
    if count >= max(2, sample_count // 2):
        return "often"
    return "sometimes"


def _structure(lowered: str) -> list[str]:
    """Describe the likely response structure."""
    result = ["short acknowledgement"]
    if any(term in lowered for term in ("i can", "i will", "happy to", "let me")):
        result.append("direct answer")
    if any(term in lowered for term in ("let me know", "next", "tomorrow", "by ", "when")):
        result.append("clear next step")
    if len(result) == 1:
        result.append("concise message body")
    return result


def _common_phrases(lowered: str) -> list[str]:
    """Return common reusable phrases without exposing private content."""
    phrase_options = (
        "thanks",
        "thank you",
        "sounds good",
        "happy to",
        "let me know",
        "i can",
        "i will",
        "please",
        "appreciate",
    )
    counts = Counter({phrase: lowered.count(phrase) for phrase in phrase_options})
    return [phrase for phrase, count in counts.most_common(5) if count > 0]


def _avoidance_rules(lowered: str) -> list[str]:
    """Suggest style constraints for drafting."""
    avoid = ["copying wording from unrelated sent emails"]
    if "!" not in lowered:
        avoid.append("unnecessary exclamation marks")
    if "dear" not in lowered and "sincerely" not in lowered:
        avoid.append("overly formal wording")
    avoid.append("long explanations unless the thread requires detail")
    return avoid


def _confidence_for_samples(sample_count: int) -> str:
    """Map usable sample count to confidence."""
    if sample_count >= 10:
        return "high"
    if sample_count >= 4:
        return "medium"
    return "low"


def _profile_limitations(sample_count: int, previous_error: str) -> list[str]:
    """Explain limits in the learned profile."""
    limitations = []
    if previous_error:
        limitations.append(previous_error)
    if sample_count == 0:
        limitations.append("No usable sent email samples were available.")
    elif sample_count < 4:
        limitations.append("Only a few usable sent email samples were available.")
    limitations.append("The saved profile contains summarized style signals, not raw sent emails.")
    return limitations


def _audience_adjustment(recipient_query: str, purpose: str) -> dict[str, str]:
    """Tell the agent how to adapt the general profile for this draft."""
    recommendation = "Use the general style profile unless the current thread is formal."
    if recipient_query:
        recommendation = "Use the general style profile and adapt it to this recipient's thread tone."
    if purpose:
        recommendation += f" Draft purpose: {purpose}."
    return {
        "recipient_query": recipient_query,
        "purpose": purpose,
        "recommendation": recommendation,
    }


def _recommended_action(profile_state: str) -> str:
    """Return the next action the agent should take."""
    if profile_state == "fresh":
        return "Draft using the saved style profile."
    if profile_state == "stale":
        return "Ask whether to relearn the writing style from recent sent emails before drafting."
    if profile_state == "refreshed":
        return "Draft using the refreshed style profile."
    if profile_state == "unavailable":
        return "Explain the profile problem and ask whether to continue without a saved style profile."
    return "Ask the user whether to learn their writing style from recent sent emails."


def _is_stale(profile: dict[str, Any], stale_after_days: int) -> bool:
    """Check whether the saved profile is older than the refresh threshold."""
    age = _profile_age_days(profile)
    return age is None or age > stale_after_days


def _profile_age_days(profile: dict[str, Any]) -> int | None:
    """Return the age in days for the saved profile."""
    last_updated = str(profile.get("last_updated", ""))
    try:
        updated_date = datetime.strptime(last_updated, "%Y-%m-%d")
    except ValueError:
        return None
    return (datetime.now() - updated_date).days


def _sample_haystack(sample: dict[str, Any]) -> str:
    """Combine searchable sample fields."""
    return f"{sample.get('sender', '')} {sample.get('subject', '')} {sample.get('preview', '')}"


def _strip_provider_counts(raw: str) -> str:
    """Remove provider boilerplate from fallback text sampling."""
    return re.sub(r"Found\s+\d+\s+email\(s\):?", "", raw, flags=re.IGNORECASE).strip()


def _empty_profile() -> dict[str, Any]:
    """Return an empty profile shape for missing/unavailable states."""
    return {
        "tone": "",
        "formality": "",
        "directness": "",
        "warmth": "",
        "greeting_patterns": [],
        "sign_off_patterns": [],
        "sentence_style": {},
        "structure": [],
        "common_phrasing": [],
        "avoid": [],
    }


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    """Convert a value to int and keep it inside a safe range."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _safe_call(callable_obj: Any, fallback: str) -> str:
    """Call a provider function safely and convert the result to text."""
    try:
        result = callable_obj()
    except Exception as exc:  # pragma: no cover - defensive around provider tools
        return fallback or f"Error: {exc}"
    return str(result)


def _display_profile_path() -> str:
    """Return a stable human-readable profile path."""
    try:
        return str(_profile_path.relative_to(Path(__file__).resolve().parents[1]))
    except ValueError:
        return str(_profile_path)


def _to_json(data: dict[str, Any]) -> str:
    """Serialize the structured profile result for the agent."""
    return json.dumps(data, ensure_ascii=False, indent=2)
