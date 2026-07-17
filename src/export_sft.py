"""
export_sft.py - Export APRIL semantic records to SFT training format.

Usage:
    python export_sft.py [--output state/sft_export.jsonl] [--format chat|alpaca] [--min-confidence 0.6]
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
STATE_DIR = BASE_DIR / "state"
SEMANTIC_PATH = STATE_DIR / "semantic_records.jsonl"
ARCHIVE_PATH = STATE_DIR / "semantic_records_archive.jsonl"
DEFAULT_PROMPT_FILES = ["soul.md", "style.md", "capabilities.md", "rules.md"]

# Known Whisper hallucination phrases to filter out
NOISE_TEXTS = {
    "thank you",
    "thanks",
    "thank you.",
    "thanks.",
    "bye",
    "bye.",
    "you",
    "you.",
    ".",
    "",
    "thank you for watching",
    "thanks for watching",
    "please subscribe",
    "subscribe",
}


def load_system_prompt() -> str:
    """Load the current system prompt from prompt files."""
    prompt_dir = BASE_DIR / "prompts"
    if not prompt_dir.exists():
        return "You are APRIL, a concise home assistant."
    sections = []
    for filename in DEFAULT_PROMPT_FILES:
        path = prompt_dir / filename
        if path.exists():
            try:
                body = path.read_text(encoding="utf-8").strip()
                if body:
                    sections.append(f"[{filename}]\n{body}")
            except OSError:
                continue
    return "\n\n".join(sections).strip() or "You are APRIL, a concise home assistant."


def load_records() -> list[dict[str, Any]]:
    """Load all records from both the main file and archive."""
    records = []
    for path in [ARCHIVE_PATH, SEMANTIC_PATH]:
        if not path.exists():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if isinstance(record, dict):
                        records.append(record)
                except json.JSONDecodeError:
                    continue
        except OSError:
            continue
    return records


def filter_records(
    records: list[dict[str, Any]],
    *,
    min_confidence: float = 0.6,
    require_success: bool = False,
) -> list[dict[str, Any]]:
    """Filter out noise, low-confidence, and empty records."""
    filtered = []
    for record in records:
        text = str(record.get("text", "") or "").strip()
        response = str(record.get("response", "") or "").strip()
        confidence = float(record.get("confidence", 0) or 0)
        outcome = str(record.get("outcome", "") or "").strip().lower()

        # Skip noise
        if text.lower() in NOISE_TEXTS or not text:
            continue
        if not response:
            continue
        if confidence < min_confidence:
            continue
        if require_success and outcome != "success":
            continue
        # Skip very short texts that are likely misheard
        if len(text) < 3:
            continue

        filtered.append(record)
    return filtered


def group_by_session(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group records by session_id for multi-turn conversations."""
    sessions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        session_id = str(record.get("session_id", "") or "").strip() or "unknown"
        sessions[session_id].append(record)
    # Sort each session by timestamp
    for session_id in sessions:
        sessions[session_id].sort(key=lambda r: str(r.get("ts", "") or ""))
    return dict(sessions)


def export_chat_format(
    records: list[dict[str, Any]],
    system_prompt: str,
    *,
    multi_turn: bool = True,
) -> list[dict[str, Any]]:
    """Export records in chat-format SFT (messages array)."""
    output = []

    if multi_turn:
        sessions = group_by_session(records)
        for session_id, session_records in sessions.items():
            messages = [{"role": "system", "content": system_prompt}]
            for record in session_records:
                text = str(record.get("text", "") or "").strip()
                response = str(record.get("response", "") or "").strip()
                if text and response:
                    messages.append({"role": "user", "content": text})
                    messages.append({"role": "assistant", "content": response})
            if len(messages) > 1:  # More than just the system message
                output.append({"messages": messages})
    else:
        for record in records:
            text = str(record.get("text", "") or "").strip()
            response = str(record.get("response", "") or "").strip()
            if text and response:
                output.append(
                    {
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": text},
                            {"role": "assistant", "content": response},
                        ]
                    }
                )
    return output


def export_alpaca_format(
    records: list[dict[str, Any]],
    system_prompt: str,
) -> list[dict[str, Any]]:
    """Export records in Alpaca instruction-format SFT."""
    output = []
    for record in records:
        text = str(record.get("text", "") or "").strip()
        response = str(record.get("response", "") or "").strip()
        if text and response:
            output.append(
                {
                    "instruction": system_prompt,
                    "input": text,
                    "output": response,
                }
            )
    return output


def main():
    parser = argparse.ArgumentParser(
        description="Export APRIL semantic records to SFT training format."
    )
    parser.add_argument(
        "--output",
        "-o",
        default=str(STATE_DIR / "sft_export.jsonl"),
        help="Output JSONL file path",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["chat", "alpaca"],
        default="chat",
        help="SFT format (default: chat)",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.6,
        help="Minimum confidence threshold (default: 0.6)",
    )
    parser.add_argument(
        "--success-only", action="store_true", help="Only include successful outcomes"
    )
    parser.add_argument(
        "--single-turn",
        action="store_true",
        help="Don't group by session (single-turn only)",
    )
    args = parser.parse_args()

    print("Loading records...")
    records = load_records()
    print(f"  Total records: {len(records)}")

    filtered = filter_records(
        records, min_confidence=args.min_confidence, require_success=args.success_only
    )
    print(f"  After filtering: {len(filtered)}")

    system_prompt = load_system_prompt()
    print(f"  System prompt length: {len(system_prompt)} chars")

    if args.format == "chat":
        output = export_chat_format(
            filtered, system_prompt, multi_turn=not args.single_turn
        )
    else:
        output = export_alpaca_format(filtered, system_prompt)

    print(f"  Export entries: {len(output)}")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for entry in output:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"  Written to: {output_path}")
    print("Done.")


if __name__ == "__main__":
    main()
