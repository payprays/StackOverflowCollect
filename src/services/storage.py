from __future__ import annotations

import json
import logging
import re
import csv
import threading
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from src.domain.models import Answer, Question, TranslationResult
from src.utils.text import html_to_text

logger = logging.getLogger(__name__)


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return slug[:80] or "topic"


class Storage:
    def __init__(self, base_dir: Path, out_csv: Optional[Path] = None) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        # Always output to CSV. Default to results.csv in base_dir if not specified.
        self.out_csv = out_csv or (base_dir / "results.csv")
        self._csv_lock = threading.Lock()
        
        self._init_csv()

    def _init_csv(self) -> None:
        """Initialize CSV file with headers if it doesn't exist."""
        if not self.out_csv.exists():
             with self._csv_lock:
                if not self.out_csv.exists(): # Double check
                    with self.out_csv.open("w", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f)
                        writer.writerow([
                            "Question ID", 
                            "Question Title", 
                            "Question Body",
                            "Question Tags",
                            "Answer ID",
                            "Answer Body",
                            "Answer Creation Date",
                            "Question Creation Date",
                            "newAnswer Body",
                            "{Model}_Answer" # Placeholder, actual usage depends on dynamic or fixed model
                        ])

    def _topic_dir(self, question: Question) -> Path:
        prefix = question.creation_date.strftime("%Y%m%d_%H%M%S")
        return self.base_dir / f"{prefix}_{slugify(question.title)}"

    def save_question(self, topic_dir: Path, question: Question) -> Path:
        if self.out_csv:
             # Identify if we want to save question metadata to CSV?
             # For now, we only focus on appending results (answers/evals)
             pass

        # Existing directory logic
        topic_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "id": question.question_id,
            "title": question.title,
            "body": question.body,
            "tags": question.tags,
            "link": question.link,
            "created_at": question.creation_date.isoformat(), # Added back for consistency with old metadata
            "answer_count": len(question.answers), # Added back for consistency with old metadata
        }
        (topic_dir / "question.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        # The original save_raw also saved question_answer.md, let's keep that behavior
        (topic_dir / "question_answer.md").write_text(
            self._format_question_answers(question), encoding="utf-8"
        )
        logger.info("Saved question content to %s", topic_dir)
        return topic_dir

    def save_translation(self, topic_dir: Path, result: TranslationResult) -> None:
        (topic_dir / "question_answer_translated.md").write_text(
            result.translated_question_answers, encoding="utf-8"
        )
        # We do not save gpt4o_answer.md here anymore, as it is handled by the evaluator/solver step.
        # If the translator produced an extra answer, we ignore it or save it to a different file if needed.
        # (topic_dir / "gpt4o_answer.md").write_text(result.gpt_answer, encoding="utf-8")

        if result.raw_response is not None:
            (topic_dir / "translation_raw.json").write_text(
                json.dumps(result.raw_response, indent=2), encoding="utf-8"
            )
        logger.info("Saved translation output to %s", topic_dir)

    @staticmethod
    def _format_question_answers(question: Question) -> str:
        header = [
            f"# {question.title}",
            f"Link: {question.link}",
            f"Created: {question.creation_date.isoformat()}",
            f"Tags: {', '.join(question.tags)}",
            "",
            "## Question",
            html_to_text(question.body),
            "",
            "## Answers",
        ]
        if question.answers:
            for idx, answer in enumerate(question.answers, start=1):
                header.extend(
                    [
                        f"### Answer {idx}",
                        f"Accepted: {answer.is_accepted}",
                        f"Score: {answer.score}",
                        f"Link: {answer.link}",
                        f"Created: {answer.creation_date.isoformat()}",
                        "",
                        html_to_text(answer.body),
                        "",
                    ]
                )
        else:
            header.append("No answers retrieved.")
        return "\n".join(header)

    def get_question_answer_content(self, topic_dir: Path) -> str:
        path = topic_dir / "question_answer.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def get_answer_content(self, topic_dir: Path, model_name: str) -> str:
        from src.utils.model_name import model_token

        token = model_token(model_name)
        path = topic_dir / f"{token}_answer.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def save_answer(self, topic_dir: Path, model_name: str, content: str, raw_response: Optional[dict] = None, question: Optional[Question] = None) -> None:
        from src.utils.model_name import model_token

        # CSV Output
        # We need ID and Title. Assuming topic_dir name contains ID or we parse it.
        # Ideally we should pass Question object or ID here.
        # But refactoring all signatures is expensive.
        # Let's try to infer ID from topic_dir name (e.g. "1234_Title")
        q_id = topic_dir.name.split("_")[0] 
        # Safe fallback?
        
        if raw_response:
            # Save raw JSON for debugging
            token = model_token(model_name)
            (topic_dir / f"{token}_answer_raw.json").write_text(
                json.dumps(raw_response, indent=2, ensure_ascii=False), encoding="utf-8"
            )

        # 1. Try to use passed Question object (Best source)
        q_id = topic_dir.name.split("_")[0]
        q_title = topic_dir.name
        q_body = ""
        q_tags = ""
        q_created = ""
        
        ans_id = ""
        ans_body = ""
        ans_created = ""
        new_ans_body = ""

        if question:
            q_id = str(question.question_id)
            q_title = question.title
            q_body = question.body
            q_tags = ", ".join(question.tags)
            q_created = question.creation_date.isoformat()
            
            # Use the first answer as the representative "Standard Answer"
            if question.answers and len(question.answers) > 0:
                # We assume the first answer is the target one.
                # Note: If there are multiple answers, this logic simply picks the first one 
                # effectively flattening 1-to-many into 1-to-1-first.
                # If we want 1-to-many, we'd need to iterate and write multiple rows, 
                # but 'save_answer' is called once per MODEL generation.
                std_ans = question.answers[0]
                ans_id = str(std_ans.answer_id)
                ans_body = std_ans.body
                ans_created = std_ans.creation_date.isoformat()
                # newAnswer Body logic: Not standard in Question model, 
                # assuming it might be 'body' or we lack it unless added to Answer model.
                # If 'newAnswer Body' is a specific CSV column from input, it might not be in the Answer object model yet.
                # We'll map std_ans.body to 'Answer Body' and leave 'newAnswer Body' empty or same.
                
        else:
            # 2. Fallback to question.json (Incomplete context)
            try:
                q_data = json.loads((topic_dir / "question.json").read_text(encoding="utf-8"))
                q_id = q_data.get("id", q_id)
                q_title = q_data.get("title", q_title)
                q_body = q_data.get("body", "")
                q_tags = q_data.get("tags", [])
                if isinstance(q_tags, list):
                    q_tags = ", ".join(q_tags)
                q_created = q_data.get("created_at", "")
                
                # Cannot recover Answer ID/Body from question.json alone easily 
                # unless we change save_question to store them fully.
            except (FileNotFoundError, json.JSONDecodeError):
                logger.warning("Could not read question.json for %s, CSV metadata will be incomplete", topic_dir.name)

        
        with self._csv_lock:
            with self.out_csv.open("a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    q_id,
                    q_title,
                    q_body,
                    q_tags,
                    ans_id,
                    ans_body,
                    ans_created,
                    q_created,
                    new_ans_body,
                    content
                ])

        # Directory Output
        token = model_token(model_name)
        (topic_dir / f"{token}_answer.md").write_text(content, encoding="utf-8")
        logger.info("Saved answer for %s to %s", model_name, topic_dir)

    def save_answer_translation(self, topic_dir: Path, model_name: str, content: str) -> None:
        from src.utils.model_name import model_token

        q_id = topic_dir.name.split("_")[0]
        with self._csv_lock:
            with self.out_csv.open("a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    q_id,
                    topic_dir.name,
                    "translation",
                    model_name,
                    content,
                    ""
                ])

        token = model_token(model_name)
        path = topic_dir / f"{token}_answer_translated.md"
        path.write_text(content, encoding="utf-8")
        logger.info("Saved answer translation for %s to %s", model_name, path)

    def save_evaluation(
        self,
        topic_dir: Path,
        answer_model: str,
        eval_model: str,
        content: str,
        raw_response: dict,
    ) -> None:
        from src.utils.model_name import model_token

        # CSV Output
        q_id = topic_dir.name.split("_")[0]
        with self._csv_lock:
            with self.out_csv.open("a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    q_id,
                    topic_dir.name,
                    "evaluation",
                    f"{eval_model}_on_{answer_model}",
                    content,
                    json.dumps(raw_response, ensure_ascii=False)
                ])

        # Directory Output
        ans_token = model_token(answer_model)
        eval_token = model_token(eval_model)
        filename = f"{eval_token}_evaluate_{ans_token}_answer.md"
        (topic_dir / filename).write_text(content, encoding="utf-8")
        
        # Save raw JSON for debugging
        debug_filename = f"{eval_token}_evaluate_{ans_token}_raw.json"
        (topic_dir / debug_filename).write_text(
            json.dumps(raw_response, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        logger.info(
            "Saved evaluation for %s on %s by %s",
            topic_dir.name,
            answer_model,
            eval_model,
        )

    def has_answer(self, topic_dir: Path, model_name: str) -> bool:
        from src.utils.model_name import model_token
        from src.utils.text import is_file_empty

        token = model_token(model_name)
        path = topic_dir / f"{token}_answer.md"
        return path.exists() and not is_file_empty(path)

    def has_evaluation(
        self, topic_dir: Path, answer_model: str, eval_model: str
    ) -> bool:
        from src.utils.model_name import model_token
        from src.utils.text import is_file_empty

        # Note: Checking CSV existence is expensive if we don't index.
        # For now, we rely on directory existence as primary check if directory mode is used.
        # If ONLY CSV mode is used (not current plan, we assume hybrid), this might re-run.
        # Optimization: Init should read existing CSV and build a set of existing keys.
        
        ans_token = model_token(answer_model)
        eval_token = model_token(eval_model)
        filename = f"{eval_token}_evaluate_{ans_token}_answer.md"
        path = topic_dir / filename
        # Removed is_file_chinese check to decouple language logic
        return path.exists() and not is_file_empty(path)
