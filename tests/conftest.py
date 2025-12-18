import pytest
from datetime import datetime, UTC
from unittest.mock import MagicMock
from src.core.models import Question, Answer


@pytest.fixture
def sample_answer():
    return Answer(
        answer_id=101,
        body="<p>Use kubectl apply -f file.yaml</p>",
        creation_date=datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC),
        is_accepted=True,
        link="http://stackoverflow.com/a/101",
        score=10,
    )


@pytest.fixture
def sample_question(sample_answer):
    return Question(
        question_id=1,
        title="How to deploy to Kubernetes?",
        body="<p>I needed help deploying.</p>",
        creation_date=datetime(2023, 1, 1, 10, 0, 0, tzinfo=UTC),
        link="http://stackoverflow.com/q/1",
        tags=["kubernetes", "deployment"],
        answers=[sample_answer],
    )


@pytest.fixture
def mock_httpx_client():
    client = MagicMock()
    # Mocking a response object
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {}

    # post/get return this response
    client.post.return_value = mock_response
    client.get.return_value = mock_response
    return client
