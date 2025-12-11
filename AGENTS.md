# Repository Guidelines

## Project Structure & Module Organization
- Source lives in `stackoverflowcollect/`: `stack_client.py` handles Stack Exchange API calls, `translator.py` sends content to the GPT-4o-compatible endpoint, `storage.py` writes artifacts, and `workflow.py` coordinates the pipeline. Public helpers and dataclasses sit in `models.py`.
- The CLI entrypoint is `main.py`; run it from the repo root. Output artifacts default to `data/` with one subfolder per question.
- Dependency metadata lives in `pyproject.toml`; lock state is in `uv.lock`.

## Build, Test, and Development Commands
- `uv sync`: 创建并同步虚拟环境和依赖（使用 `pyproject.toml` / `uv.lock`）。
- `uv run python main.py --limit 3 --out-dir data`: 拉取最新 3 个 Kubernetes Q&A，保存原始内容并调用本地模型翻译。
- 在命令后加 `--no-translate` 跳过 GPT 调用，加 `--verbose` 查看调试日志，加 `--tag` 选择其他标签。

## Coding Style & Naming Conventions
- Target Python 3.12+. Keep modules small and focused; prefer explicit exports in `__all__`.
- Use snake_case for functions/variables and CapWords for classes/dataclasses. Keep line length near 100 characters.
- Network calls go through `httpx` clients; pass shared clients to keep connection reuse explicit.
- Avoid non-ASCII in code; UTF-8 only for saved content.

## Testing Guidelines
- No test suite is present yet. Add lightweight unit tests around fetchers, translators, and storage formatters using `pytest`.
- When mocking HTTP calls, prefer `httpx`’s built-in `MockTransport` to avoid brittle network dependencies.
- Validate that saved directories contain `metadata.json`, `question.md`, `answers.md`, and translation outputs when enabled.

## Commit & Pull Request Guidelines
- Keep commits scoped and message in imperative present (e.g., “Add StackOverflow client”).
- In PRs, describe the behavior change, note testing performed, and call out any network assumptions (e.g., reliance on `localhost:4141`).
- Include sample commands to reproduce the fetch/translate flow and mention any new dependencies.
