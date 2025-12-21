import json
from unittest.mock import MagicMock
from src.core.translator import Translator
from src.core.evaluator import Evaluator
from src.io.storage import Storage


def test_translator_translate(sample_question, mock_httpx_client):
    # Mock response for translation
    mock_resp_json = {
        "choices": [
            {
                "message": {
                    "content": "# 翻译后问题与回答\nQuestion Translated\n# gpt4o回答\nMy Answer"
                }
            }
        ]
    }
    mock_httpx_client.post.return_value.json.return_value = mock_resp_json

    translator = Translator(session=mock_httpx_client, api_key="test-key")
    res = translator.translate(sample_question)

    assert res.translated_question_answers == "Question Translated"
    assert res.gpt_answer == "My Answer"
    assert res.raw_response == mock_resp_json


def test_evaluator_generate_answer(mock_httpx_client):
    mock_resp_json = {"choices": [{"message": {"content": "Generated YAML"}}]}
    mock_httpx_client.post.return_value.json.return_value = mock_resp_json

    evaluator = Evaluator(session=mock_httpx_client, mode="answer", api_key="test")
    ans, raw_resp = evaluator.generate_answer("Some context")
    assert ans == "Generated YAML"
    assert raw_resp == mock_resp_json


def test_evaluator_evaluate(mock_httpx_client):
    mock_resp_json = {
        "choices": [{"message": {"content": '{"semantic_drift": {"label": "Absent"}}'}}]
    }
    mock_httpx_client.post.return_value.json.return_value = mock_resp_json

    evaluator = Evaluator(session=mock_httpx_client, mode="evaluate", api_key="test")
    res, raw_resp = evaluator.evaluate("Q & A", "LLM Answer", "model_name")
    assert "semantic_drift" in res

import pytest

@pytest.mark.skip(reason="save_raw method was removed during refactoring")
def test_storage_save_raw(tmp_path, sample_question):
    store = Storage(tmp_path)
    topic_dir = store.save_raw(sample_question)

    assert topic_dir.exists()
    assert (topic_dir / "metadata.json").exists()
    assert (topic_dir / "question_answer.md").exists()

    meta = json.loads((topic_dir / "metadata.json").read_text())
    assert meta["question_id"] == sample_question.question_id


def test_storage_save_translation(tmp_path):
    from src.domain.models import TranslationResult

    store = Storage(tmp_path)
    topic_dir = tmp_path / "test_topic"
    topic_dir.mkdir()

    res = TranslationResult("Trans Q", "Trans A", "gpt-4o", {})
    store.save_translation(topic_dir, res)

    assert (topic_dir / "question_answer_translated.md").exists()
    assert (topic_dir / "question_answer_translated.md").read_text() == "Trans Q"
    # Note: gpt4o_answer.md is no longer saved by save_translation
