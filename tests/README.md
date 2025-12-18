# Tests

This directory contains the test suite for the StackOverflowCollect project.

## Running Tests

Ensure you have `pytest` installed:

```bash
pip install pytest
```

Run the tests from the root directory:

```bash
python -m pytest tests
```

## Structure

- `conftest.py`: Shared fixtures (Mock data, Mock HTTP client).
- `test_units.py`: Unit tests for utility functions.
- `test_services.py`: Tests for service classes (Translator, Evaluator, Storage) using mocks.
- `test_workflow.py`: Integration-style tests for the main workflow functions (`run_crawl`, `run_translate`, `run_evaluate`).
