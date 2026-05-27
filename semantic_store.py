"""
semantic_store.py - Append-only semantic memory and training record store for APRIL.

This module keeps the first implementation deliberately lightweight:
- append-only JSONL records
- deterministic similarity scoring
- reusable record shape for utterances, documents, directories, and other artifacts
- training-ready capture fields for future fine-tuning datasets
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from event_ledger import append_event


BASE_DIR = Path(__file__).resolve().parent
STATE_DIR = BASE_DIR / "state"
SEMANTIC_PATH = STATE_DIR / "semantic_records.jsonl"
_lock = Lock()
_records_cache: list[dict[str, Any]] | None = None
_MAX_CACHE = 5000
_TOKEN_ALIASES = {
    "doc": "document",
    "docs": "document",
    "document": "document",
    "documents": "document",
    "dir": "directory",
    "dirs": "directory",
    "folder": "directory",
    "folders": "directory",
    "app": "app",
    "apps": "app",
    "application": "app",
    "applications": "app",
}


def record_semantic_example(
    *,
    kind: str,
    text: str,
    source: str = "april",
    resolved_intent: str = "",
    response: str = "",
    action: dict[str, Any] | None = None,
    outcome: str = "observed",
    subject_type: str = "",
    subject_ref: str = "",
    confidence: float | None = None,
    metadata: dict[str, Any] | None = None,
    prompt_safe: bool = True,
    sensitivity: str = "low",
    session_id: str = "",
    system_prompt_hash: str = "",
    enriched_context: str = "",
) -> dict[str, Any]:
    clean_text = _normalize_text(text)
    record = {
        "id": f"sem_{uuid4().hex}",
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": _clean_field(kind),
        "source": _clean_field(source) or "april",
        "text": _clean_field(text),
        "normalized_text": clean_text,
        "resolved_intent": _clean_field(resolved_intent),
        "response": _clean_field(response),
        "action": action or {},
        "outcome": _clean_field(outcome) or "observed",
        "subject_type": _clean_field(subject_type),
        "subject_ref": _clean_field(subject_ref),
        "confidence": _clean_confidence(confidence),
        "metadata": metadata or {},
        "session_id": _clean_field(session_id),
        "system_prompt_hash": _clean_field(system_prompt_hash),
        "enriched_context": _clean_field(enriched_context),
    }

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with _lock:
        records = _load_unlocked()
        records.append(record)
        if len(records) > _MAX_CACHE:
            _archive_overflow(records[:-_MAX_CACHE])
            records = records[-_MAX_CACHE:]
        SEMANTIC_PATH.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in records) + ("\n" if records else ""), encoding="utf-8")
        global _records_cache
        _records_cache = [dict(item) for item in records]

    append_event(
        "semantic_example_recorded",
        source=record["source"],
        domain="semantic",
        state="observed",
        entity_id=record["id"],
        sensitivity=sensitivity,
        prompt_safe=prompt_safe,
        payload={
            "kind": record["kind"],
            "text": record["text"],
            "resolved_intent": record["resolved_intent"],
            "subject_type": record["subject_type"],
            "subject_ref": record["subject_ref"],
            "confidence": record["confidence"],
            "outcome": record["outcome"],
        },
    )
    return record


def semantic_recall(text: str, *, limit: int = 5, kind: str = "") -> list[dict[str, Any]]:
    query = _normalize_text(text)
    if not query or limit <= 0:
        return []

    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    records = _load()
    matches: list[dict[str, Any]] = []
    for record in records:
        if kind and str(record.get("kind", "") or "").strip().lower() != kind.strip().lower():
            continue
        score = _score_match(query, query_tokens, record)
        if score <= 0:
            continue
        matches.append({"score": score, "record": dict(record)})

    matches.sort(key=lambda item: (item["score"], _record_ts(item["record"])), reverse=True)
    return matches[:limit]


def semantic_plan(text: str, *, kind: str = "", confidence_threshold: float = 0.74) -> dict[str, Any] | None:
    matches = semantic_recall(text, limit=3, kind=kind)
    if not matches:
        return None

    best = matches[0]
    score = float(best.get("score", 0.0) or 0.0)
    record = best.get("record") if isinstance(best.get("record"), dict) else {}
    if score < confidence_threshold:
        return None

    intent = str(record.get("resolved_intent", "") or "").strip().lower()
    action = record.get("action") if isinstance(record.get("action"), dict) else {}
    if not intent or not action:
        return None

    action = dict(action)
    action.setdefault("text", text)
    preview = str(record.get("response", "") or "").strip()
    if not preview:
        preview = f"Using learned phrasing for {intent}."
    return {
        "intent": intent,
        "response_preview": preview,
        "action": action,
        "_semantic": {
            "score": score,
            "kind": record.get("kind", ""),
            "subject_type": record.get("subject_type", ""),
            "subject_ref": record.get("subject_ref", ""),
        },
    }


def export_training_records(limit: int | None = None) -> list[dict[str, Any]]:
    records = _load()
    if limit is not None and limit > 0:
        records = records[-limit:]
    return [dict(item) for item in records]


def _load() -> list[dict[str, Any]]:
    global _records_cache
    with _lock:
        if _records_cache is not None:
            return [dict(item) for item in _records_cache]
        _records_cache = _load_unlocked()
        return [dict(item) for item in _records_cache]


def _load_unlocked() -> list[dict[str, Any]]:
    if not SEMANTIC_PATH.exists():
        return []
    try:
        lines = SEMANTIC_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    records: list[dict[str, Any]] = []
    for line in lines:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(_normalize_record(payload))
    return records


def _normalize_record(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _clean_field(payload.get("id", "")) or f"sem_{uuid4().hex}",
        "ts": _clean_field(payload.get("ts", "")) or datetime.now(timezone.utc).isoformat(),
        "kind": _clean_field(payload.get("kind", "")),
        "source": _clean_field(payload.get("source", "")) or "april",
        "text": _clean_field(payload.get("text", "")),
        "normalized_text": _clean_field(payload.get("normalized_text", "")) or _normalize_text(str(payload.get("text", "") or "")),
        "resolved_intent": _clean_field(payload.get("resolved_intent", "")),
        "response": _clean_field(payload.get("response", "")),
        "action": payload.get("action") if isinstance(payload.get("action"), dict) else {},
        "outcome": _clean_field(payload.get("outcome", "")) or "observed",
        "subject_type": _clean_field(payload.get("subject_type", "")),
        "subject_ref": _clean_field(payload.get("subject_ref", "")),
        "confidence": _clean_confidence(payload.get("confidence")),
        "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        "session_id": _clean_field(payload.get("session_id", "")),
        "system_prompt_hash": _clean_field(payload.get("system_prompt_hash", "")),
        "enriched_context": _clean_field(payload.get("enriched_context", "")),
    }


ARCHIVE_PATH = STATE_DIR / "semantic_records_archive.jsonl"

def _archive_overflow(overflow: list[dict[str, Any]]) -> None:
    """Append overflow records to the archive file so training data is never lost."""
    if not overflow:
        return
    try:
        with open(ARCHIVE_PATH, "a", encoding="utf-8") as f:
            for item in overflow:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _score_match(query: str, query_tokens: list[str], record: dict[str, Any]) -> float:
    normalized = str(record.get("normalized_text", "") or "").strip()
    if not normalized:
        normalized = _normalize_text(str(record.get("text", "") or ""))
    if not normalized:
        return 0.0

    if normalized == query:
        return 1.0

    record_tokens = _tokenize(normalized)
    if not record_tokens:
        return 0.0

    query_counter = Counter(query_tokens)
    record_counter = Counter(record_tokens)
    intersection = sum(min(query_counter[token], record_counter[token]) for token in query_counter.keys() & record_counter.keys())
    union = sum((query_counter | record_counter).values())
    jaccard = intersection / union if union else 0.0

    overlap = intersection / max(len(query_tokens), len(record_tokens), 1)
    subseq_bonus = 0.15 if query in normalized or normalized in query else 0.0
    prefix_bonus = 0.1 if normalized.startswith(query[: min(len(query), len(normalized))]) else 0.0
    confidence_bonus = min(_clean_confidence(record.get("confidence")), 1.0) * 0.05
    return min(1.0, (jaccard * 0.55) + (overlap * 0.35) + subseq_bonus + prefix_bonus + confidence_bonus)


def _record_ts(record: dict[str, Any]) -> str:
    return str(record.get("ts", "") or "")


def _normalize_text(text: str) -> str:
    clean = " ".join(str(text).strip().lower().split())
    return re.sub(r"[^a-z0-9\s_:/.-]+", "", clean)


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for token in re.findall(r"[a-z0-9_:/.-]+", text.lower()):
        tokens.append(_TOKEN_ALIASES.get(token, token))
    return tokens


def _clean_field(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _clean_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0
    if confidence != confidence:
        return 0.0
    return max(0.0, min(1.0, confidence))
