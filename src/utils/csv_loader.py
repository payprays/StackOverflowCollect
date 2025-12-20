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
        # Read all rows into memory to avoid issues if the file is overwritten during processing
        all_rows = list(reader)
        
        count = 0
        for row in all_rows:
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
                creation_date_str = row.get("Question Creation Date", "")
                creation_date = datetime.now()  # Default
                if creation_date_str and isinstance(creation_date_str, str) and creation_date_str.strip():
                    try:
                        creation_date = datetime.fromisoformat(creation_date_str.strip())
                    except ValueError:
                        pass  # Keep default

                # Link
                link = f"https://stackoverflow.com/questions/{q_id}"

                # === LLM Answer (to be evaluated) ===
                # From dynamic model columns like 'gpt-5.1_Answer', 'gpt-4o_Answer', etc.
                # EXCLUDE: _Answer_Translated, _Evaluate_*_Answer columns
                llm_answer_body = None
                for col_name in row.keys():
                    # Match pattern: {model}_Answer but NOT {model}_Answer_Translated or {eval}_Evaluate_{model}_Answer
                    if col_name.endswith('_Answer') and \
                       not col_name.endswith('_Answer_Translated') and \
                       '_Evaluate_' not in col_name:
                        potential_body = row.get(col_name, "")
                        if potential_body and potential_body.strip():
                            llm_answer_body = potential_body
                            logger.debug(f"Found LLM answer in column: {col_name}")
                            break
                
                # === Human Answer (reference for evaluation) ===
                # From 'Answer Body' column - Stack Overflow accepted/top answer
                human_answer_body = row.get("Answer Body", "")
                
                ans_id_str = row.get("Answer ID")
                ans_id = int(ans_id_str) if ans_id_str and isinstance(ans_id_str, str) and ans_id_str.isdigit() else 0
                
                # Try to parse answer creation date
                ans_date_str = row.get("Answer Creation Date", "")
                ans_creation_date = datetime.now()  # Default
                if ans_date_str and isinstance(ans_date_str, str) and ans_date_str.strip():
                    try:
                        ans_creation_date = datetime.fromisoformat(ans_date_str.strip())
                    except ValueError:
                        pass  # Keep default

                # Build answers list
                # answers[0] = LLM answer (what we're evaluating)
                # answers[1] = Human answer (reference for evaluator)
                answers = []
                
                if llm_answer_body:
                    answers.append(Answer(
                        answer_id=0,  # LLM answer has no SO answer ID
                        body=llm_answer_body,
                        creation_date=datetime.now(),
                        is_accepted=False,
                        link="",
                        score=0
                    ))
                
                if human_answer_body:
                    answers.append(Answer(
                        answer_id=ans_id,
                        body=human_answer_body,
                        creation_date=ans_creation_date,
                        is_accepted=True,  # Assume human answer is the accepted one
                        link=f"https://stackoverflow.com/a/{ans_id}",
                        score=0
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
                
                # print(f"DEBUG: Yielding row {i}")
                yield topic_dir, question
                count += 1

            except ValueError as e:
                logger.warning(f"Skipping row due to ValueError: {e}")
                continue
            except Exception as e:
                logger.error(f"Skipping row due to unexpected error: {e}")
                continue
    
    # print("DEBUG: csv_loader finished")
    logger.info("csv_loader: finished iterating CSV, yielded %d items", count)

def _sanitize_filename(name: str) -> str:
    # Simple sanitization
    return "".join(c for c in name if c.isalnum() or c in (' ', '_', '-')).strip().replace(' ', '_')
