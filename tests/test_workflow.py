
import json
from unittest.mock import MagicMock
from src.flows.workflow import run_crawl, run_translate, run_batch_answer, run_batch_evaluate
from src.services.storage import Storage


def test_run_crawl_flow(tmp_path, mock_httpx_client):
    # Setup mock responses for SO API
    # 1. Questions response
    questions_resp = {
        "items": [
            {
                "question_id": 1,
                "title": "Test Q",
                "body": "Body",
                "creation_date": 1672531200,
                "link": "http://q/1",
                "tags": ["k8s"],
            }
        ],
        "has_more": False,
    }
    # 2. Answers response
    answers_resp = {"items": []}

    # We need side_effect because different URLs or params are called
    def side_effect(url, params=None):
        mock = MagicMock()
        mock.raise_for_status.return_value = None
        if "/questions" in url and "/answers" not in url:
            mock.json.return_value = questions_resp
        elif "/answers" in url:
            mock.json.return_value = answers_resp
        return mock

    mock_httpx_client.get.side_effect = side_effect

    run_crawl(
        tag="k8s", limit=1, out_dir=tmp_path, session=mock_httpx_client, workers=1
    )

    # Verify data is saved
    dirs = list(tmp_path.iterdir())
    topic_dirs = [d for d in dirs if d.is_dir()]
    assert len(topic_dirs) == 1
    # Storage now saves question.json, not metadata.json
    assert (topic_dirs[0] / "question.json").exists()


def test_run_translate_flow(tmp_path, mock_httpx_client, sample_question):
    store = Storage(tmp_path)
    # Use internal topic dir logic helper or manual
    topic_dir = store._topic_dir(sample_question)
    store.save_question(topic_dir, sample_question)

    mock_resp_json = {
        "choices": [
            {"message": {"content": "# 翻译后问题与回答\nTrans\n# gpt4o回答\nAns"}}
        ]
    }
    # We might need side_effect if translate_text is called and returns simple string
    def translate_side_effect(json_input=None, **kwargs):
        # Inspect input to deduce if it's translate() or translate_text()
        # But here we mock response dict only.
        return mock_resp_json

    mock_httpx_client.post.return_value.json.return_value = mock_resp_json
    
    # Create a dummy answer file to test answer translation detachment
    (topic_dir / "gpt4o_answer.md").write_text("English Answer", encoding="utf-8")

    run_translate(out_dir=tmp_path, session=mock_httpx_client, workers=1, force=True)

    assert (topic_dir / "question_answer_translated.md").exists()
    # Check if answer was also translated (since run_translate logic now covers it)
    # But wait, translate_text calls LLMClient which returns simple string if successful?
    # Translator.translate_text implementation extracts content from response choice.
    # So our mock needs to provide that structure again.
    assert (topic_dir / "gpt4o_answer_translated.md").exists()


def test_run_evaluate_flow(tmp_path, mock_httpx_client, sample_question):
    store = Storage(tmp_path)
    topic_dir = store._topic_dir(sample_question)
    store.save_question(topic_dir, sample_question)

    encoded_resp = {"choices": [{"message": {"content": "Valid Content"}}]}
    mock_httpx_client.post.return_value.json.return_value = encoded_resp

    # Pass api_key to avoid RuntimeError
    # 1. Answer Mode
    run_batch_answer(
        out_dir=tmp_path,
        session=mock_httpx_client,
        workers=1,
        force=True,
        api_key="test",
    )

    # Check if answer generated.
    # model_token("gpt-4o") returns "gpt4o", so file is gpt4o_answer.md
    answer_file = topic_dir / "gpt4o_answer.md"
    assert answer_file.exists()

    # 2. Evaluate Mode
    run_batch_evaluate(
        out_dir=tmp_path,
        session=mock_httpx_client,
        workers=1,
        force=True,
        api_key="test",
    )

    eval_file = topic_dir / "gpt4o_evaluate_gpt4o_answer.md"
    assert eval_file.exists()
