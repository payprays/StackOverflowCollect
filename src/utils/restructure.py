from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def restructure_directories(base_dir: str | Path) -> None:
    base = Path(base_dir)
    if not base.exists():
        logger.warning("Base directory %s does not exist", base)
        return

    for topic_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        _ensure_question_answer(topic_dir)
        _ensure_translated(topic_dir)


def cleanup_extra_files(base_dir: str | Path) -> None:
    base = Path(base_dir)
    legacy_files = [
        "question.md",
        "answers.md",
        "translated_question.md",
        "translated_answers.md",
        "assistant_answer.md",
        "answered_question.md",
    ]
    for topic_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        if not (topic_dir / "question_answer.md").exists():
            continue
        for name in legacy_files:
            target = topic_dir / name
            if target.exists():
                try:
                    target.unlink()
                    logger.info("Removed legacy file %s", target)
                except OSError as exc:
                    logger.warning("Failed to remove %s: %s", target, exc)


def _ensure_question_answer(topic_dir: Path) -> None:
    target = topic_dir / "question_answer.md"
    if target.exists():
        return
    q_path = topic_dir / "question.md"
    a_path = topic_dir / "answers.md"
    if not q_path.exists():
        return
    meta = _load_meta(topic_dir / "metadata.json")
    tags = ", ".join(meta.get("tags", []))
    lines = []
    lines.extend(q_path.read_text(encoding="utf-8").splitlines())
    if tags:
        lines.insert(4, f"Tags: {tags}")
    lines.append("")
    lines.append("## Answers")
    if a_path.exists():
        lines.extend(a_path.read_text(encoding="utf-8").splitlines())
    else:
        lines.append("No answers retrieved.")
    target.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Created %s", target)


def _ensure_translated(topic_dir: Path) -> None:
    target = topic_dir / "question_answer_translated.md"
    if target.exists():
        return
    tq = topic_dir / "translated_question.md"
    ta = topic_dir / "translated_answers.md"
    if not (tq.exists() or ta.exists()):
        return
    lines = ["### 翻译后问题与回答", ""]
    if tq.exists():
        lines.extend(tq.read_text(encoding="utf-8").splitlines())
    if ta.exists():
        lines.append("")
        lines.extend(ta.read_text(encoding="utf-8").splitlines())
    target.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Created %s", target)


def _load_meta(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}
