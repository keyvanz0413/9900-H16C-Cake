from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ACTIVE_STATUS = "active"
HIDDEN_STATUS = "hidden_locally_after_unsubscribe"
DEFAULT_STATE_FILENAME = "UNSUBSCRIBE_STATE.json"


def resolve_unsubscribe_state_path(*, skill_runtime: dict[str, Any] | None = None) -> Path:
    runtime_value = ""
    if isinstance(skill_runtime, dict):
        runtime_value = str(skill_runtime.get("unsubscribe_state_path") or "").strip()
    env_value = str(os.getenv("UNSUBSCRIBE_STATE_PATH") or "").strip()
    raw_path = runtime_value or env_value
    if raw_path:
        return Path(raw_path).expanduser().resolve()
    return Path(__file__).resolve().with_name(DEFAULT_STATE_FILENAME)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _default_state_payload() -> dict[str, Any]:
    return {
        "version": 1,
        "items": [],
    }


def _coerce_string(value: Any) -> str:
    return str(value or "").strip()


def _coerce_string_list(value: Any, *, limit: int = 5) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    seen: set[str] = set()
    for raw_item in value:
        item = _coerce_string(raw_item)
        if not item or item in seen:
            continue
        seen.add(item)
        items.append(item)
        if len(items) >= limit:
            break
    return items


def _coerce_recent_count(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 1
    return max(1, number)


def _normalize_state_record(raw_record: Any) -> dict[str, Any] | None:
    if not isinstance(raw_record, dict):
        return None

    candidate_id = _coerce_string(raw_record.get("candidate_id"))
    if not candidate_id:
        return None

    status = _coerce_string(raw_record.get("status")) or ACTIVE_STATUS
    if status != HIDDEN_STATUS:
        status = ACTIVE_STATUS

    return {
        "candidate_id": candidate_id,
        "sender": _coerce_string(raw_record.get("sender")),
        "sender_email": _coerce_string(raw_record.get("sender_email")).lower(),
        "sender_domain": _coerce_string(raw_record.get("sender_domain")).lower(),
        "representative_email_id": _coerce_string(raw_record.get("representative_email_id")),
        "status": status,
        "updated_at": _coerce_string(raw_record.get("updated_at")),
        "method": _coerce_string(raw_record.get("method")) or "unknown",
        "subjects": _coerce_string_list(raw_record.get("subjects")),
        "sample_email_ids": _coerce_string_list(raw_record.get("sample_email_ids")),
        "recent_count": _coerce_recent_count(raw_record.get("recent_count")),
    }


def _load_state_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _default_state_payload()

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_state_payload()

    if not isinstance(payload, dict):
        return _default_state_payload()

    raw_items = payload.get("items")
    items: list[dict[str, Any]] = []
    if isinstance(raw_items, list):
        for raw_item in raw_items:
            normalized = _normalize_state_record(raw_item)
            if normalized is not None:
                items.append(normalized)

    return {
        "version": 1,
        "items": items,
    }


def _sort_records(records: list[dict[str, Any]]) -> None:
    records.sort(
        key=lambda record: (
            1 if record.get("status") == HIDDEN_STATUS else 0,
            str(record.get("sender_email") or record.get("sender") or record.get("candidate_id") or ""),
        )
    )


def _save_state_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _candidate_to_record(candidate: dict[str, Any], *, now_iso: str) -> dict[str, Any] | None:
    if not isinstance(candidate, dict):
        return None

    candidate_id = _coerce_string(candidate.get("candidate_id"))
    if not candidate_id:
        return None

    return {
        "candidate_id": candidate_id,
        "sender": _coerce_string(candidate.get("sender")),
        "sender_email": _coerce_string(candidate.get("sender_email")).lower(),
        "sender_domain": _coerce_string(candidate.get("sender_domain")).lower(),
        "representative_email_id": _coerce_string(candidate.get("representative_email_id")),
        "status": ACTIVE_STATUS,
        "updated_at": now_iso,
        "method": _coerce_string(candidate.get("method")) or "unknown",
        "subjects": _coerce_string_list(candidate.get("subjects")),
        "sample_email_ids": _coerce_string_list(candidate.get("sample_email_ids")),
        "recent_count": _coerce_recent_count(candidate.get("recent_count")),
    }


def load_unsubscribe_state_records(*, skill_runtime: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    path = resolve_unsubscribe_state_path(skill_runtime=skill_runtime)
    payload = _load_state_payload(path)
    return copy.deepcopy(payload["items"])


def index_unsubscribe_state_records(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for record in records:
        candidate_id = _coerce_string(record.get("candidate_id"))
        if candidate_id:
            index[candidate_id] = record
    return index


def visible_unsubscribe_state_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [copy.deepcopy(record) for record in records if record.get("status") != HIDDEN_STATUS]


def hidden_unsubscribe_state_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [copy.deepcopy(record) for record in records if record.get("status") == HIDDEN_STATUS]


def merge_discovered_candidates(
    candidates: list[dict[str, Any]],
    *,
    skill_runtime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = resolve_unsubscribe_state_path(skill_runtime=skill_runtime)
    payload = _load_state_payload(path)
    records = payload["items"]
    records_by_id = index_unsubscribe_state_records(records)
    inserted_count = 0
    updated_count = 0
    now_iso = _now_iso()

    for candidate in candidates:
        normalized = _candidate_to_record(candidate, now_iso=now_iso)
        if normalized is None:
            continue

        candidate_id = normalized["candidate_id"]
        existing = records_by_id.get(candidate_id)
        if existing is None:
            records.append(normalized)
            records_by_id[candidate_id] = records[-1]
            inserted_count += 1
            continue

        existing_status = _coerce_string(existing.get("status")) or ACTIVE_STATUS
        existing.update(normalized)
        existing["status"] = HIDDEN_STATUS if existing_status == HIDDEN_STATUS else ACTIVE_STATUS
        existing["updated_at"] = now_iso
        updated_count += 1

    _sort_records(records)
    _save_state_payload(path, payload)
    return {
        "path": str(path),
        "items": copy.deepcopy(records),
        "inserted_count": inserted_count,
        "updated_count": updated_count,
    }


def mark_candidates_hidden_after_unsubscribe(
    candidates: list[dict[str, Any]],
    *,
    skill_runtime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = resolve_unsubscribe_state_path(skill_runtime=skill_runtime)
    payload = _load_state_payload(path)
    records = payload["items"]
    records_by_id = index_unsubscribe_state_records(records)
    now_iso = _now_iso()
    updated_items: list[dict[str, Any]] = []

    for candidate in candidates:
        normalized = _candidate_to_record(candidate, now_iso=now_iso)
        if normalized is None:
            continue

        candidate_id = normalized["candidate_id"]
        existing = records_by_id.get(candidate_id)
        if existing is None:
            records.append(normalized)
            records_by_id[candidate_id] = records[-1]
            existing = records[-1]

        existing.update(normalized)
        existing["status"] = HIDDEN_STATUS
        existing["updated_at"] = now_iso
        updated_items.append(copy.deepcopy(existing))

    _sort_records(records)
    _save_state_payload(path, payload)
    return {
        "path": str(path),
        "items": updated_items,
        "all_items": copy.deepcopy(records),
    }
