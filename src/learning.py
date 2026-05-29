"""
learning.py - Lightweight teachable phrase rewrites for APRIL.
"""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

BASE_DIR = Path(__file__).resolve().parent
LEARNING_PATH = BASE_DIR / "learned_phrases.json"
_cache_lock = Lock()
_rules_cache: list[dict[str, str]] | None = None


def load_rules() -> list[dict[str, str]]:
    global _rules_cache
    with _cache_lock:
        if _rules_cache is not None:
            return [dict(item) for item in _rules_cache]
        _rules_cache = _read_rules_from_disk()
        return [dict(item) for item in _rules_cache]


def apply_rewrites(text: str) -> str:
    clean = " ".join(str(text).strip().split())
    if not clean:
        return ""

    lowered = clean.lower()
    for rule in sorted(load_rules(), key=lambda item: len(item["heard"]), reverse=True):
        heard = rule["heard"].lower()
        if lowered == heard:
            return rule["means"]
        if heard in lowered:
            return _replace_case_insensitive(clean, rule["heard"], rule["means"])
    return clean


def remember_phrase(heard: str, means: str) -> None:
    global _rules_cache
    heard_clean = " ".join(str(heard).strip().split())
    means_clean = " ".join(str(means).strip().split())
    if not heard_clean or not means_clean:
        return

    with _cache_lock:
        rules = (
            _read_rules_from_disk()
            if _rules_cache is None
            else [dict(item) for item in _rules_cache]
        )
        updated = False
        for item in rules:
            if item["heard"].lower() == heard_clean.lower():
                item["heard"] = heard_clean
                item["means"] = means_clean
                updated = True
                break
        if not updated:
            rules.append({"heard": heard_clean, "means": means_clean})

        LEARNING_PATH.write_text(json.dumps(rules, indent=2), encoding="utf-8")
        _rules_cache = [dict(item) for item in rules]


def _replace_case_insensitive(text: str, old: str, new: str) -> str:
    lower_text = text.lower()
    lower_old = old.lower()
    index = lower_text.find(lower_old)
    if index == -1:
        return text
    return text[:index] + new + text[index + len(old) :]


def _read_rules_from_disk() -> list[dict[str, str]]:
    try:
        payload = json.loads(LEARNING_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []

    rules: list[dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        heard = " ".join(str(item.get("heard", "") or "").strip().split())
        means = " ".join(str(item.get("means", "") or "").strip().split())
        if heard and means:
            rules.append({"heard": heard, "means": means})
    return rules
