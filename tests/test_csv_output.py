"""
Comprehensive tests for yaml_lint module and Storage CSV functionality.
"""
import csv
import pytest
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch
import pandas as pd

from src.utils.yaml_lint import (
    extract_yaml_blocks,
    lint_yaml_blocks,
    lint_answer,
    lint_answer_full,
    LintResult,
    OverallLintResult,
)
from src.services.storage import Storage
from src.domain.models import Question, Answer


# =============================================================================
# YAML Lint Tests
# =============================================================================

class TestExtractYamlBlocks:
    """Tests for extract_yaml_blocks function."""

    def test_extract_yaml_blocks_basic(self):
        """Test extraction of basic yaml code blocks."""
        text = """
Here is a Pod:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: test
```
"""
        blocks = extract_yaml_blocks(text)
        assert len(blocks) == 1
        assert "apiVersion: v1" in blocks[0]
        assert "kind: Pod" in blocks[0]

    def test_extract_yaml_blocks_multiple(self):
        """Test extraction of multiple yaml blocks."""
        text = """
First:
```yaml
apiVersion: v1
kind: Pod
```

Second:
```yml
apiVersion: apps/v1
kind: Deployment
```
"""
        blocks = extract_yaml_blocks(text)
        assert len(blocks) == 2
        assert "kind: Pod" in blocks[0]
        assert "kind: Deployment" in blocks[1]

    def test_extract_yaml_blocks_generic_kubernetes(self):
        """Test extraction from generic code blocks with K8s content."""
        text = """
```
apiVersion: v1
kind: ConfigMap
metadata:
  name: config
```
"""
        blocks = extract_yaml_blocks(text)
        assert len(blocks) == 1
        assert "kind: ConfigMap" in blocks[0]

    def test_extract_yaml_blocks_empty(self):
        """Test extraction when no yaml blocks exist."""
        text = "This is just plain text without any code blocks."
        blocks = extract_yaml_blocks(text)
        assert len(blocks) == 0

    def test_extract_yaml_blocks_non_kubernetes(self):
        """Test that non-kubernetes generic blocks are not extracted."""
        text = """
```
print("hello world")
```
"""
        blocks = extract_yaml_blocks(text)
        assert len(blocks) == 0  # No apiVersion or kind


class TestOverallLintResult:
    """Tests for OverallLintResult dataclass."""

    def test_summary_no_yaml(self):
        """Test summary when no YAML found."""
        result = OverallLintResult()
        assert result.summary == "NO_YAML_FOUND"

    def test_summary_with_results(self):
        """Test summary with actual results."""
        result = OverallLintResult(
            yaml_blocks_found=3,
            kubeval_passed=2,
            kubeval_failed=1,
            dryrun_passed=3,
            dryrun_failed=0
        )
        assert "kubeval:2/3" in result.summary
        assert "dryrun:3/3" in result.summary

    def test_all_passed(self):
        """Test all_passed property."""
        result = OverallLintResult(
            yaml_blocks_found=2,
            kubeval_passed=2,
            kubeval_failed=0,
            dryrun_passed=2,
            dryrun_failed=0
        )
        assert result.all_passed is True

    def test_not_all_passed(self):
        """Test all_passed when some checks fail."""
        result = OverallLintResult(
            yaml_blocks_found=2,
            kubeval_passed=1,
            kubeval_failed=1,
        )
        assert result.all_passed is False

    def test_merged_code_blocks_empty(self):
        """Test merged_code_blocks when empty."""
        result = OverallLintResult()
        assert result.merged_code_blocks == ""

    def test_merged_code_blocks_single(self):
        """Test merged_code_blocks with single block."""
        result = OverallLintResult(code_blocks=["block1"])
        assert result.merged_code_blocks == "block1"

    def test_merged_code_blocks_multiple(self):
        """Test merged_code_blocks with multiple blocks."""
        result = OverallLintResult(code_blocks=["block1", "block2", "block3"])
        assert result.merged_code_blocks == "block1\n---BLOCK---\nblock2\n---BLOCK---\nblock3"


class TestLintYamlBlocks:
    """Tests for lint_yaml_blocks function."""

    def test_lint_no_yaml(self):
        """Test linting text without YAML."""
        result = lint_yaml_blocks("Just plain text", run_kubeval_check=False, run_dryrun_check=False)
        assert result.yaml_blocks_found == 0
        assert result.summary == "NO_YAML_FOUND"

    def test_lint_stores_code_blocks(self):
        """Test that code blocks are stored in result."""
        text = """
```yaml
apiVersion: v1
kind: Pod
```
"""
        result = lint_yaml_blocks(text, run_kubeval_check=False, run_dryrun_check=False)
        assert result.yaml_blocks_found == 1
        assert len(result.code_blocks) == 1
        assert "apiVersion: v1" in result.code_blocks[0]


class TestLintAnswerFull:
    """Tests for lint_answer_full function."""

    @patch("src.utils.yaml_lint.run_kubeval")
    @patch("src.utils.yaml_lint.run_kubectl_dryrun")
    def test_lint_answer_full_returns_tuple(self, mock_dryrun, mock_kubeval):
        """Test that lint_answer_full returns both summary and code blocks."""
        mock_kubeval.return_value = LintResult(tool="kubeval", passed=True, output="OK")
        mock_dryrun.return_value = LintResult(tool="kubectl-dryrun", passed=True, output="OK")

        text = """
```yaml
apiVersion: v1
kind: Pod
```
"""
        summary, code_blocks = lint_answer_full(text)
        assert isinstance(summary, str)
        assert isinstance(code_blocks, str)
        assert "apiVersion: v1" in code_blocks


# =============================================================================
# Storage Tests
# =============================================================================

class TestStorageCSV:
    """Tests for Storage CSV functionality."""

    def test_storage_init_creates_csv(self, tmp_path):
        """Test that Storage creates CSV file on init."""
        storage = Storage(base_dir=tmp_path)
        assert storage.out_csv.exists()

    def test_storage_upsert_new_row(self, tmp_path):
        """Test upserting a new row."""
        storage = Storage(base_dir=tmp_path)
        storage._upsert_row("123", {"Question Title": "Test Title"})
        
        df = pd.read_csv(storage.out_csv, dtype=str)
        assert len(df) == 1
        assert str(df.iloc[0]["Question ID"]) == "123"
        assert df.iloc[0]["Question Title"] == "Test Title"

    def test_storage_upsert_update_row(self, tmp_path):
        """Test updating an existing row."""
        storage = Storage(base_dir=tmp_path)
        storage._upsert_row("123", {"Question Title": "Title 1"})
        storage._upsert_row("123", {"Question Body": "Body 1"})
        
        df = pd.read_csv(storage.out_csv)
        assert len(df) == 1
        assert df.iloc[0]["Question Title"] == "Title 1"
        assert df.iloc[0]["Question Body"] == "Body 1"

    def test_storage_dynamic_columns(self, tmp_path):
        """Test that new columns are added dynamically."""
        storage = Storage(base_dir=tmp_path)
        storage._upsert_row("123", {"gpt-4o_Answer": "Answer content"})
        
        df = pd.read_csv(storage.out_csv)
        assert "gpt-4o_Answer" in df.columns
        assert df.iloc[0]["gpt-4o_Answer"] == "Answer content"

    def test_storage_save_question(self, tmp_path):
        """Test save_question writes to CSV."""
        storage = Storage(base_dir=tmp_path)
        question = Question(
            question_id=101,
            title="Test Question",
            body="Question body",
            tags=["k8s", "python"],
            link="http://example.com",
            creation_date=datetime.now(),
            answers=[]
        )
        topic_dir = storage._topic_dir(question)
        storage.save_question(topic_dir, question)
        
        df = pd.read_csv(storage.out_csv, dtype=str)
        assert len(df) == 1
        assert str(df.iloc[0]["Question ID"]) == "101"
        assert df.iloc[0]["Question Title"] == "Test Question"

    def test_storage_save_answer(self, tmp_path):
        """Test save_answer writes to CSV with model column."""
        storage = Storage(base_dir=tmp_path)
        topic_dir = tmp_path / "test_topic"
        topic_dir.mkdir()
        
        # Create question.json for ID lookup
        import json
        (topic_dir / "question.json").write_text(json.dumps({"id": "202"}))
        
        storage.save_answer(topic_dir, "gpt-4o", "This is the answer")
        
        df = pd.read_csv(storage.out_csv)
        assert "gpt-4o_Answer" in df.columns
        assert df.iloc[0]["gpt-4o_Answer"] == "This is the answer"

    def test_storage_save_lint_result(self, tmp_path):
        """Test save_lint_result writes lint and code blocks."""
        storage = Storage(base_dir=tmp_path)
        topic_dir = tmp_path / "test_topic"
        topic_dir.mkdir()
        
        import json
        (topic_dir / "question.json").write_text(json.dumps({"id": "303"}))
        
        storage.save_lint_result(
            topic_dir, 
            question=None,
            model_name="gpt-4o",
            lint_summary="kubeval:1/1; dryrun:1/1",
            code_blocks="apiVersion: v1\nkind: Pod"
        )
        
        df = pd.read_csv(storage.out_csv)
        assert "lint" in df.columns
        assert "gpt-4o_Answer_CodeBlocks" in df.columns
        assert "kubeval:1/1" in df.iloc[0]["lint"]

    def test_storage_thread_safe(self, tmp_path):
        """Test that storage is thread-safe for concurrent writes."""
        storage = Storage(base_dir=tmp_path)
        
        def write_op(i):
            storage._upsert_row(str(i), {f"col_{i}": f"value_{i}"})
        
        with ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(write_op, range(10)))
        
        df = pd.read_csv(storage.out_csv)
        assert len(df) == 10


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for the full pipeline."""

    def test_end_to_end_csv_flow(self, tmp_path):
        """Test complete CSV flow from question to evaluation."""
        storage = Storage(base_dir=tmp_path)
        
        # 1. Save question (crawl phase)
        question = Question(
            question_id=999,
            title="K8s Question",
            body="How to deploy?",
            tags=["kubernetes"],
            link="http://example.com/q/999",
            creation_date=datetime.now(),
            answers=[
                Answer(
                    answer_id=1001,
                    body="Use kubectl apply",
                    is_accepted=True,
                    score=10,
                    link="http://example.com/a/1001",
                    creation_date=datetime.now()
                )
            ]
        )
        topic_dir = storage._topic_dir(question)
        storage.save_question(topic_dir, question)
        
        # 2. Save answer (answer phase)
        storage.save_answer(topic_dir, "gpt-5.1", "Use deployment YAML:\n```yaml\napiVersion: apps/v1\nkind: Deployment\n```")
        
        # 3. Save lint result (evaluate phase)
        storage.save_lint_result(topic_dir, question, "gpt-5.1", "kubeval:1/1", "apiVersion: apps/v1\nkind: Deployment")
        
        # 4. Save evaluation (evaluate phase)
        storage.save_evaluation(topic_dir, "gpt-5.1", "gpt-5.1", "Good answer", {"tokens": 100})
        
        # Verify final CSV
        df = pd.read_csv(storage.out_csv, dtype=str)
        assert len(df) == 1
        row = df.iloc[0]
        
        # Check all columns exist
        assert row["Question ID"] == "999"
        assert row["Question Title"] == "K8s Question"
        assert "gpt-5.1_Answer" in df.columns
        assert "lint" in df.columns
        assert "gpt-5.1_Answer_CodeBlocks" in df.columns
        assert "gpt-5.1_Evaluate_gpt-5.1_Answer" in df.columns
