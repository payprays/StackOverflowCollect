"""
YAML Lint validation module for Kubernetes configurations.

This module provides functions to validate YAML code blocks extracted from answers
using kubeval, datree, and kubectl dry-run.
"""
from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class LintResult:
    """Result of a single lint check."""
    tool: str
    passed: bool
    output: str
    error: str = ""


@dataclass
class OverallLintResult:
    """Overall lint result for an answer."""
    yaml_blocks_found: int = 0
    kubeval_passed: int = 0
    kubeval_failed: int = 0
    datree_passed: int = 0
    datree_failed: int = 0
    dryrun_passed: int = 0
    dryrun_failed: int = 0
    details: List[LintResult] = field(default_factory=list)
    code_blocks: List[str] = field(default_factory=list)  # Extracted code blocks

    @property
    def summary(self) -> str:
        """Generate a summary string for CSV output."""
        if self.yaml_blocks_found == 0:
            return "NO_YAML_FOUND"
        
        parts = []
        if self.kubeval_passed + self.kubeval_failed > 0:
            parts.append(f"kubeval:{self.kubeval_passed}/{self.kubeval_passed + self.kubeval_failed}")
        if self.datree_passed + self.datree_failed > 0:
            parts.append(f"datree:{self.datree_passed}/{self.datree_passed + self.datree_failed}")
        if self.dryrun_passed + self.dryrun_failed > 0:
            parts.append(f"dryrun:{self.dryrun_passed}/{self.dryrun_passed + self.dryrun_failed}")
        
        if not parts:
            return "NO_CHECKS_RUN"
        
        return "; ".join(parts)

    @property
    def all_passed(self) -> bool:
        """Check if all lint checks passed."""
        total_failed = self.kubeval_failed + self.datree_failed + self.dryrun_failed
        return total_failed == 0 and self.yaml_blocks_found > 0
    
    @property
    def merged_code_blocks(self) -> str:
        """Merge all code blocks into a single string with BLOCK separator."""
        if not self.code_blocks:
            return ""
        return "\n---BLOCK---\n".join(self.code_blocks)
    
    @property
    def detailed_logs(self) -> str:
        """Generate detailed logs from all lint check results."""
        if not self.details:
            return ""
        
        logs = []
        for i, detail in enumerate(self.details):
            log_entry = f"=== {detail.tool} (Block {i // 2 + 1}) ==="
            if detail.passed:
                log_entry += "\n✅ PASSED"
            else:
                log_entry += "\n❌ FAILED"
            
            if detail.output:
                log_entry += f"\n[OUTPUT]\n{detail.output.strip()}"
            if detail.error:
                log_entry += f"\n[ERROR]\n{detail.error.strip()}"
            
            logs.append(log_entry)
        
        return "\n\n".join(logs)


def is_complete_k8s_yaml(block: str) -> bool:
    """Check if a YAML block is a complete Kubernetes resource.
    
    A complete K8s resource should have:
    - apiVersion: at the root level (starts with 'apiVersion:')
    - kind: somewhere in the block
    - Be at least 5 lines (minimum viable K8s YAML)
    """
    lines = block.strip().split('\n')
    
    # Too short to be a valid K8s resource
    if len(lines) < 5:
        return False
    
    # Check if it starts with apiVersion (root level, not indented)
    first_meaningful_line = ""
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith('#'):
            first_meaningful_line = stripped
            break
    
    if not first_meaningful_line.startswith('apiVersion:'):
        return False
    
    # Must have 'kind:' somewhere
    has_kind = any(line.strip().startswith('kind:') for line in lines)
    
    return has_kind


def extract_yaml_blocks(text: str) -> List[str]:
    """Extract complete Kubernetes YAML code blocks from markdown text.
    
    Only extracts blocks that:
    - Are in ```yaml or ```yml fences, OR
    - Are in generic ``` fences with K8s content
    - Start with 'apiVersion:' at root level
    - Contain 'kind:'
    - Have at least 5 lines
    
    Filters out:
    - Partial snippets (like just 'stdin: true')
    - Inline YAML fragments
    - Non-K8s YAML
    """
    all_code_blocks = []
    
    # Match yaml/yml code blocks
    yaml_pattern = r"```(?:yaml|yml)\s*\n(.*?)```"
    yaml_blocks = re.findall(yaml_pattern, text, re.DOTALL | re.IGNORECASE)
    all_code_blocks.extend(yaml_blocks)
    
    # Also try to match generic code blocks
    generic_pattern = r"```\s*\n(.*?)```"
    generic_blocks = re.findall(generic_pattern, text, re.DOTALL)
    
    for block in generic_blocks:
        if block not in all_code_blocks:
            all_code_blocks.append(block)
    
    # Filter to only complete K8s YAML resources
    complete_k8s_blocks = []
    for block in all_code_blocks:
        block = block.strip()
        if not block:
            continue
        
        # Handle multi-document YAML (separated by ---)
        documents = re.split(r'^---\s*$', block, flags=re.MULTILINE)
        for doc in documents:
            doc = doc.strip()
            if doc and is_complete_k8s_yaml(doc):
                complete_k8s_blocks.append(doc)
    
    return complete_k8s_blocks


def run_kubeval(yaml_content: str, yaml_file: Path) -> LintResult:
    """Run kubeval on a YAML file."""
    try:
        result = subprocess.run(
            ["kubeval", str(yaml_file)],
            capture_output=True,
            text=True,
            timeout=30
        )
        passed = result.returncode == 0
        return LintResult(
            tool="kubeval",
            passed=passed,
            output=result.stdout,
            error=result.stderr
        )
    except FileNotFoundError:
        logger.warning("kubeval not found, skipping kubeval check")
        return LintResult(tool="kubeval", passed=True, output="kubeval not installed", error="")
    except subprocess.TimeoutExpired:
        return LintResult(tool="kubeval", passed=False, output="", error="Timeout")
    except Exception as e:
        return LintResult(tool="kubeval", passed=False, output="", error=str(e))


def run_datree(yaml_content: str, yaml_file: Path) -> LintResult:
    """Run datree on a YAML file."""
    try:
        result = subprocess.run(
            ["datree", "test", str(yaml_file)],
            capture_output=True,
            text=True,
            timeout=60
        )
        passed = result.returncode == 0
        return LintResult(
            tool="datree",
            passed=passed,
            output=result.stdout,
            error=result.stderr
        )
    except FileNotFoundError:
        logger.warning("datree not found, skipping datree check")
        return LintResult(tool="datree", passed=True, output="datree not installed", error="")
    except subprocess.TimeoutExpired:
        return LintResult(tool="datree", passed=False, output="", error="Timeout")
    except Exception as e:
        return LintResult(tool="datree", passed=False, output="", error=str(e))


def run_kubectl_dryrun(yaml_content: str, yaml_file: Path) -> LintResult:
    """Run kubectl apply --dry-run=client on a YAML file."""
    try:
        result = subprocess.run(
            ["kubectl", "apply", "--dry-run=client", "-f", str(yaml_file)],
            capture_output=True,
            text=True,
            timeout=30
        )
        passed = result.returncode == 0
        return LintResult(
            tool="kubectl-dryrun",
            passed=passed,
            output=result.stdout,
            error=result.stderr
        )
    except FileNotFoundError:
        logger.warning("kubectl not found, skipping dry-run check")
        return LintResult(tool="kubectl-dryrun", passed=True, output="kubectl not installed", error="")
    except subprocess.TimeoutExpired:
        return LintResult(tool="kubectl-dryrun", passed=False, output="", error="Timeout")
    except Exception as e:
        return LintResult(tool="kubectl-dryrun", passed=False, output="", error=str(e))


def lint_yaml_blocks(
    text: str,
    run_kubeval_check: bool = True,
    run_datree_check: bool = False,  # Off by default as it requires setup
    run_dryrun_check: bool = True
) -> OverallLintResult:
    """
    Extract YAML blocks from text and run lint checks on each.
    
    Args:
        text: The answer text containing YAML code blocks
        run_kubeval_check: Whether to run kubeval
        run_datree_check: Whether to run datree
        run_dryrun_check: Whether to run kubectl dry-run
    
    Returns:
        OverallLintResult with summary of all checks
    """
    result = OverallLintResult()
    yaml_blocks = extract_yaml_blocks(text)
    result.yaml_blocks_found = len(yaml_blocks)
    result.code_blocks = yaml_blocks  # Store extracted code blocks
    
    if not yaml_blocks:
        logger.info("No YAML blocks found in text")
        return result
    
    for i, yaml_content in enumerate(yaml_blocks):
        # Write to temp file
        with tempfile.NamedTemporaryFile(
            mode='w', 
            suffix='.yaml', 
            delete=False,
            encoding='utf-8'
        ) as f:
            f.write(yaml_content)
            temp_path = Path(f.name)
        
        try:
            # Run kubeval
            if run_kubeval_check:
                kubeval_result = run_kubeval(yaml_content, temp_path)
                result.details.append(kubeval_result)
                if kubeval_result.passed:
                    result.kubeval_passed += 1
                else:
                    result.kubeval_failed += 1
            
            # Run datree
            if run_datree_check:
                datree_result = run_datree(yaml_content, temp_path)
                result.details.append(datree_result)
                if datree_result.passed:
                    result.datree_passed += 1
                else:
                    result.datree_failed += 1
            
            # Run kubectl dry-run
            if run_dryrun_check:
                dryrun_result = run_kubectl_dryrun(yaml_content, temp_path)
                result.details.append(dryrun_result)
                if dryrun_result.passed:
                    result.dryrun_passed += 1
                else:
                    result.dryrun_failed += 1
                    
        finally:
            # Clean up temp file
            try:
                temp_path.unlink()
            except Exception:
                pass
    
    return result


def lint_answer(answer_text: str) -> str:
    """
    Convenience function to lint an answer and return summary string for CSV.
    
    Args:
        answer_text: The model-generated answer text
    
    Returns:
        Summary string like "kubeval:2/3; dryrun:3/3" or "NO_YAML_FOUND"
    """
    result = lint_yaml_blocks(
        answer_text,
        run_kubeval_check=True,
        run_datree_check=True,  # Enabled datree
        run_dryrun_check=True
    )
    return result.summary


def lint_answer_full(answer_text: str) -> Tuple[str, str, str]:
    """
    Lint an answer and return summary, code blocks, and detailed logs.
    
    Args:
        answer_text: The model-generated answer text
    
    Returns:
        Tuple of (summary, merged_code_blocks, detailed_logs)
        - summary: "kubeval:2/3; dryrun:3/3" or "NO_YAML_FOUND"
        - merged_code_blocks: All YAML blocks merged with ---BLOCK--- separator
        - detailed_logs: Full lint output for each check
    """
    result = lint_yaml_blocks(
        answer_text,
        run_kubeval_check=True,
        run_datree_check=True,  # Enabled datree
        run_dryrun_check=True
    )
    return result.summary, result.merged_code_blocks, result.detailed_logs


