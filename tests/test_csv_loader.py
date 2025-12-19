
import csv
from unittest.mock import MagicMock, patch
from src.utils.csv_loader import load_questions_from_csv
from src.flows.workflow import run_evaluate
from src.domain.models import Question

def test_load_questions_from_csv(tmp_path):
    # Create a dummy CSV file
    csv_file = tmp_path / "test.csv"
    with csv_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Question ID", "Question Title", "Question Body", "Question Tags", "Question Creation Date"])
        writer.writerow(["123", "Test Question", "This is a body", "tag1, tag2", "2023-01-01T00:00:00"])

    output_dir = tmp_path / "output"
    questions = list(load_questions_from_csv(csv_file, output_dir))
    
    assert len(questions) == 1
    topic_dir, q = questions[0]
    assert q.question_id == 123
    assert q.title == "Test Question"
    assert q.body == "This is a body"
    assert q.tags == ["tag1", "tag2"]
    # Verify fallback directory creation logic
    assert output_dir in topic_dir.parents
    assert topic_dir.name.startswith("123_Test_Question")

@patch("src.flows.workflow.Evaluator")
@patch("src.flows.workflow.Storage")
@patch("src.flows.workflow.Translator")
@patch("src.flows.workflow.ThreadPoolExecutor")
def test_run_evaluate_with_csv(mock_executor, mock_translator, mock_storage, mock_evaluator, tmp_path):
    csv_file = tmp_path / "input.csv"
    with csv_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Question ID", "Question Title", "Question Body"])
        writer.writerow(["999", "CSV Flow Test", "Body"])

    out_dir = tmp_path / "out"
    
    # Mock executor to run immediately but return a dummy future
    future = MagicMock()
    future.result.return_value = None
    mock_executor.return_value.__enter__.return_value.submit.side_effect = lambda fn, *args: (fn(*args), future)[1]

    # Mock storage methods to return clean strings
    mock_storage.return_value.has_answer.return_value = False # Force generate
    mock_storage.return_value.get_question_answer_content.return_value = ""
    mock_storage.return_value.get_answer_content.return_value = "Mock Answer"
    
    mock_evaluator.return_value.generate_answer.return_value = "Mock Answer"

    mock_evaluator.return_value.generate_answer.return_value = "Mock Answer"
    
    from src.flows.workflow import run_batch_answer
    run_batch_answer(out_dir=out_dir, input_csv=csv_file, api_key="dummy")
    
    # Check if load_questions_from_csv was used is implicit by checking side effects or
    # we can check if Storage was initialized with output dir
    mock_storage.assert_called_with(out_dir)
    # Ensure evaluator was called
    assert mock_evaluator.called
