import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Iterator, Tuple

from src.domain.models import Question, Answer

logger = logging.getLogger(__name__)

def load_questions_from_csv(csv_path: Path, output_base_dir: Path) -> Iterator[Tuple[Path, Question]]:
    """
    Reads a CSV file and yields (topic_dir, Question) tuples.
    CSV format expected: 'Question ID', 'Question Title', 'Question Body', ...
    """
    if not csv_path.exists():
        logger.error(f"CSV file not found: {csv_path}")
        return

    with csv_path.open("r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                # Basic fields
                q_id = int(row.get("Question ID", 0))
                title = row.get("Question Title", "")
                body = row.get("Question Body", "")
                
                # Tags
                tags_str = row.get("Question Tags", "")
                tags = [t.strip() for t in tags_str.split(",")] if tags_str else []
                
                # Dates
                # Attempt to parse creation date, default to now if missing/failed
                # Format unknown, assuming ISO or common simple string for now, fallback to now
                # Or just keep it simple as we primarily need content.
                creation_date_str = row.get("Question Creation Date", "")
                try:
                    # Try common ISO format or similar if present
                    creation_date = datetime.fromisoformat(creation_date_str)
                except ValueError:
                    creation_date = datetime.now()

                # Link
                link = f"https://stackoverflow.com/questions/{q_id}"

                # Answers
                # If we have 'Answer Body' or 'newAnswer Body', we can treat it as an existing answer.
                # In this specific dataset 'latest_input_data_filtered_rewrite_containyaml.csv', 
                # we seem to have one answer per row. 
                # If multiple rows share the same Question ID, we should technically aggregate them, 
                # but the current yield structure is iterator-based per row.
                # Assuming 1 row = 1 question context for now, or the workflow handles duplicates.
                # Given strict iterator, duplicates might re-process. 
                # Let's populate the answer list if data exists.
                
                answers = []
                ans_body = row.get("newAnswer Body") or row.get("Answer Body")
                ans_id_str = row.get("Answer ID")
                if ans_body:
                    ans_id = int(ans_id_str) if ans_id_str and ans_id_str.isdigit() else 0
                    # Try to parse answer creation date
                    ans_date_str = row.get("Answer Creation Date", "")
                    try:
                         ans_creation_date = datetime.fromisoformat(ans_date_str)
                    except ValueError:
                         ans_creation_date = datetime.now()
                    
                    answers.append(Answer(
                        answer_id=ans_id,
                        body=ans_body,
                        creation_date=ans_creation_date,
                        is_accepted=False, # Not in CSV potentially
                        link=f"https://stackoverflow.com/a/{ans_id}",
                        score=0 # Not in CSV
                    ))

                # Construct Question
                question = Question(
                    question_id=q_id,
                    title=title,
                    body=body,
                    creation_date=creation_date,
                    link=link,
                    tags=tags,
                    answers=answers
                )

                # Output directory preparation
                # We use the Question ID to name the folder, similar to crawl mode
                topic_name = f"{q_id}_{_sanitize_filename(title)}"
                # Limit length
                if len(topic_name) > 50:
                    topic_name = topic_name[:50]
                
                topic_dir = output_base_dir / topic_name
                if not topic_dir.exists():
                    topic_dir.mkdir(parents=True, exist_ok=True)
                
                # Also save the raw question parsing result for debugging/reference? 
                # workflow.py usually does this.
                
                yield topic_dir, question

            except ValueError as e:
                logger.warning(f"Skipping row due to error: {e}")
                continue

def _sanitize_filename(name: str) -> str:
    # Simple sanitization
    return "".join(c for c in name if c.isalnum() or c in (' ', '_', '-')).strip().replace(' ', '_')
