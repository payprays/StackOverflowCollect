from __future__ import annotations

import json
import logging
import re
import csv
import threading
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional, List, Dict, Any

import pandas as pd

from src.domain.models import Answer, Question, TranslationResult
from src.utils.text import html_to_text

logger = logging.getLogger(__name__)

# Base columns that crawl produces
BASE_COLUMNS = [
    "Question ID",
    "Question Title",
    "Question Body",
    "Question Tags",
    "Answer ID",
    "Answer Body",
    "Answer Creation Date",
    "Question Creation Date",
    "newAnswer Body",
]


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return slug[:80] or "topic"


class Storage:
    def __init__(self, base_dir: Path, out_csv: Optional[Path] = None) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        # Always output to CSV. Default to results.csv in base_dir if not specified.
        self.out_csv = out_csv or (base_dir / "results.csv")
        self._csv_lock = threading.RLock()
        self._df: Optional[pd.DataFrame] = None
        
        self._load_or_init_csv()

    def _load_or_init_csv(self) -> None:
        """Load existing CSV or initialize with base columns."""
        with self._csv_lock:
            if self.out_csv.exists():
                try:
                    self._df = pd.read_csv(self.out_csv, dtype=str)
                    # Ensure Question ID is string
                    if "Question ID" in self._df.columns:
                        self._df["Question ID"] = self._df["Question ID"].astype(str)
                    logger.info("Loaded existing CSV with %d rows and columns: %s", len(self._df), list(self._df.columns))
                except Exception as e:
                    logger.warning("Failed to load existing CSV, creating new: %s", e)
                    self._df = pd.DataFrame(columns=BASE_COLUMNS)
            else:
                self._df = pd.DataFrame(columns=BASE_COLUMNS)
                self._save_csv()

    def _save_csv(self) -> None:
        """Save the dataframe to CSV."""
        if self._df is not None:
            self._df.to_csv(self.out_csv, index=False, encoding="utf-8")

    def _ensure_column(self, col_name: str) -> None:
        """Ensure a column exists in the dataframe."""
        if self._df is not None and col_name not in self._df.columns:
            self._df[col_name] = ""
            logger.info("Added new column: %s", col_name)

    def _upsert_row(self, question_id: str, data: Dict[str, Any]) -> None:
        """Insert or update a row by Question ID."""
        with self._csv_lock:
            if self._df is None:
                return
            
            # Ensure all columns exist
            for col in data.keys():
                self._ensure_column(col)
            
            question_id = str(question_id)
            mask = self._df["Question ID"] == question_id
            
            if mask.any():
                # Update existing row
                for col, val in data.items():
                    self._df.loc[mask, col] = val
            else:
                # Insert new row
                new_row = {col: "" for col in self._df.columns}
                new_row["Question ID"] = question_id
                new_row.update(data)
                self._df = pd.concat([self._df, pd.DataFrame([new_row])], ignore_index=True)
            
            self._save_csv()

    def _topic_dir(self, question: Question) -> Path:
        prefix = question.creation_date.strftime("%Y%m%d_%H%M%S")
        return self.base_dir / f"{prefix}_{slugify(question.title)}"

    def ensure_question_in_csv(self, question: Question) -> None:
        """Ensure question base data is in CSV (upserts base columns only).
        
        This is useful when processing from input-csv mode to ensure
        base question data is in the output CSV.
        
        NOTE: This does NOT overwrite existing Answer Body to preserve
        the original human answer from Stack Overflow.
        """
        with self._csv_lock:
            q_id = str(question.question_id)
            q_tags = ", ".join(question.tags) if question.tags else ""
            
            # Get human answer info if available (answers[1] in csv_loader convention)
            # answers[0] = LLM answer, answers[1] = Human answer
            human_ans_id = ""
            human_ans_body = ""
            human_ans_created = ""
            if question.answers and len(question.answers) > 1:
                # Human answer at index 1
                std_ans = question.answers[1]
                human_ans_id = str(std_ans.answer_id)
                human_ans_body = std_ans.body
                human_ans_created = std_ans.creation_date.isoformat()
            
            # Build base data - but do NOT include Answer Body if it would overwrite
            csv_data = {
                "Question ID": q_id,
                "Question Title": question.title,
                "Question Body": question.body,
                "Question Tags": q_tags,
                "Question Creation Date": question.creation_date.isoformat(),
            }
            
            # Only set Answer Body if we have a human answer AND it's not already set
            if human_ans_body:
                # Check if existing row has Answer Body populated
                existing = self._df[self._df["Question ID"] == q_id] if self._df is not None and "Question ID" in self._df.columns else pd.DataFrame()
                should_write_answer = True
                if not existing.empty:
                    existing_ans = existing.iloc[0].get("Answer Body", "")
                    if existing_ans and isinstance(existing_ans, str) and len(existing_ans) > 0:
                        should_write_answer = False  # Already has answer, don't overwrite
                
                if should_write_answer:
                    csv_data["Answer ID"] = human_ans_id
                    csv_data["Answer Body"] = human_ans_body
                    csv_data["Answer Creation Date"] = human_ans_created
            
            self._upsert_row(q_id, csv_data)

    def save_question(self, topic_dir: Path, question: Question) -> Path:
        """Save question to directory and CSV (base columns for crawl phase)."""
        # CSV Output - base columns for crawl
        q_id = str(question.question_id)
        q_tags = ", ".join(question.tags) if question.tags else ""
        
        # Get first answer info if available
        ans_id = ""
        ans_body = ""
        ans_created = ""
        if question.answers and len(question.answers) > 0:
            std_ans = question.answers[0]
            ans_id = str(std_ans.answer_id)
            ans_body = std_ans.body
            ans_created = std_ans.creation_date.isoformat()
        
        csv_data = {
            "Question ID": q_id,
            "Question Title": question.title,
            "Question Body": question.body,
            "Question Tags": q_tags,
            "Answer ID": ans_id,
            "Answer Body": ans_body,
            "Answer Creation Date": ans_created,
            "Question Creation Date": question.creation_date.isoformat(),
            "newAnswer Body": "",  # Placeholder, can be filled later
        }
        self._upsert_row(q_id, csv_data)

        # Existing directory logic
        topic_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "id": question.question_id,
            "title": question.title,
            "body": question.body,
            "tags": question.tags,
            "link": question.link,
            "created_at": question.creation_date.isoformat(),
            "answer_count": len(question.answers),
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

    def save_translation(self, topic_dir: Path, result: TranslationResult, question: Optional[Question] = None) -> None:
        """Save Q&A translation to directory and CSV (adds QA_Translated column)."""
        # Get Question ID
        q_id = ""
        if question:
            q_id = str(question.question_id)
        else:
            try:
                q_data = json.loads((topic_dir / "question.json").read_text(encoding="utf-8"))
                q_id = str(q_data.get("id", topic_dir.name.split("_")[0]))
            except (FileNotFoundError, json.JSONDecodeError):
                q_id = topic_dir.name.split("_")[0]
        
        # CSV Output - add QA_Translated column
        self._upsert_row(q_id, {"QA_Translated": result.translated_question_answers})

        # Directory Output
        (topic_dir / "question_answer_translated.md").write_text(
            result.translated_question_answers, encoding="utf-8"
        )

        if result.raw_response is not None:
            (topic_dir / "translation_raw.json").write_text(
                json.dumps(result.raw_response, indent=2), encoding="utf-8"
            )
        logger.info("Saved translation output to %s", topic_dir)

    @staticmethod
    def _format_question_answers(question: Question, human_answer: str = "") -> str:
        """Format question and human answer for LLM evaluation context.
        
        Args:
            question: The Question object
            human_answer: Optional human/reference answer (Stack Overflow answer)
        """
        header = [
            f"# {question.title}",
            f"Link: {question.link}",
            f"Created: {question.creation_date.isoformat()}",
            f"Tags: {', '.join(question.tags)}",
            "",
            "## Question",
            html_to_text(question.body),
            "",
        ]
        
        # Add human answer as reference if provided
        if human_answer:
            header.extend([
                "## Reference Answer (Human)",
                html_to_text(human_answer),
                "",
            ])
        
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
        """Save model-generated answer to directory and CSV (adds {model}_Answer column)."""
        from src.utils.model_name import model_token

        token = model_token(model_name)
        
        # Save raw JSON for debugging
        if raw_response:
            (topic_dir / f"{token}_answer_raw.json").write_text(
                json.dumps(raw_response, indent=2, ensure_ascii=False), encoding="utf-8"
            )

        # Get Question ID
        q_id = ""
        if question:
            q_id = str(question.question_id)
        else:
            # Fallback to parsing from topic_dir or question.json
            try:
                q_data = json.loads((topic_dir / "question.json").read_text(encoding="utf-8"))
                q_id = str(q_data.get("id", topic_dir.name.split("_")[0]))
            except (FileNotFoundError, json.JSONDecodeError):
                q_id = topic_dir.name.split("_")[0]
        
        # CSV Output - add {model}_Answer column
        answer_col = f"{model_name}_Answer"
        self._upsert_row(q_id, {answer_col: content})

        # Directory Output
        (topic_dir / f"{token}_answer.md").write_text(content, encoding="utf-8")
        logger.debug("Saved answer for %s to %s", model_name, topic_dir)

    def save_answer_translation(self, topic_dir: Path, model_name: str, content: str) -> None:
        """Save translated answer to directory and CSV (adds {model}_Answer_Translated column)."""
        from src.utils.model_name import model_token

        # Get Question ID
        try:
            q_data = json.loads((topic_dir / "question.json").read_text(encoding="utf-8"))
            q_id = str(q_data.get("id", topic_dir.name.split("_")[0]))
        except (FileNotFoundError, json.JSONDecodeError):
            q_id = topic_dir.name.split("_")[0]
        
        # CSV Output - add {model}_Answer_Translated column
        trans_col = f"{model_name}_Answer_Translated"
        self._upsert_row(q_id, {trans_col: content})

        # Directory Output
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
        """Save evaluation result to directory and CSV (adds {eval_model}_Evaluate_{answer_model}_Answer column)."""
        from src.utils.model_name import model_token

        # Get Question ID
        try:
            q_data = json.loads((topic_dir / "question.json").read_text(encoding="utf-8"))
            q_id = str(q_data.get("id", topic_dir.name.split("_")[0]))
        except (FileNotFoundError, json.JSONDecodeError):
            q_id = topic_dir.name.split("_")[0]
        
        # CSV Output - add {eval_model}_Evaluate_{answer_model}_Answer column
        eval_col = f"{eval_model}_Evaluate_{answer_model}_Answer"
        self._upsert_row(q_id, {eval_col: content})

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

        logger.debug(
            "Saved evaluation for %s on %s by %s",
            topic_dir.name,
            answer_model,
            eval_model,
        )

    def save_lint_result(
        self,
        topic_dir: Path,
        question: Optional[Question],
        model_name: str,
        lint_summary: str,
        code_blocks: str,
        detailed_logs: str = "",
    ) -> None:
        """Save lint result, code blocks, and detailed logs to CSV.
        
        Adds columns:
        - lint: Summary of lint results
        - {model}_Answer_CodeBlocks: Merged YAML code blocks
        - lint_logs: Detailed output from each lint check
        """
        # Get Question ID
        q_id = ""
        if question:
            q_id = str(question.question_id)
        else:
            try:
                q_data = json.loads((topic_dir / "question.json").read_text(encoding="utf-8"))
                q_id = str(q_data.get("id", topic_dir.name.split("_")[0]))
            except (FileNotFoundError, json.JSONDecodeError):
                q_id = topic_dir.name.split("_")[0]
        
        # CSV Output - add lint, code blocks, and logs columns
        code_blocks_col = f"{model_name}_Answer_CodeBlocks"
        self._upsert_row(q_id, {
            "lint": lint_summary,
            code_blocks_col: code_blocks,
            "lint_logs": detailed_logs
        })
        
        logger.debug("Saved lint result for %s: %s", topic_dir.name, lint_summary)

    def save_evaluation_translation(
        self,
        topic_dir: Path,
        answer_model: str,
        eval_model: str,
        content: str,
    ) -> None:
        """Save translated evaluation to directory and CSV (adds {eval_model}_Evaluate_{answer_model}_Answer_Translated column)."""
        from src.utils.model_name import model_token

        # Get Question ID
        try:
            q_data = json.loads((topic_dir / "question.json").read_text(encoding="utf-8"))
            q_id = str(q_data.get("id", topic_dir.name.split("_")[0]))
        except (FileNotFoundError, json.JSONDecodeError):
            q_id = topic_dir.name.split("_")[0]
        
        # CSV Output - add {eval_model}_Evaluate_{answer_model}_Answer_Translated column
        trans_col = f"{eval_model}_Evaluate_{answer_model}_Answer_Translated"
        self._upsert_row(q_id, {trans_col: content})

        # Directory Output
        ans_token = model_token(answer_model)
        eval_token = model_token(eval_model)
        filename = f"{eval_token}_evaluate_{ans_token}_answer_translated.md"
        (topic_dir / filename).write_text(content, encoding="utf-8")
        
        logger.info(
            "Saved evaluation translation for %s on %s by %s",
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
