# StackOverflow Collect

## 功能
- 抓取 Stack Overflow 指定标签（默认 `kubernetes`）的最新问答，按时间排序并存档。
- 将原始问题和回答存为 Markdown，包含元数据与原始响应。
- 翻译原始问答为中文，并生成/保存模型回答。
- 调用官方 OpenAI 模型评估已有回答，输出改进建议。

## 目录结构
- `src/`
  - `stack_client.py`：Stack Exchange API 抓取问答。
  - `storage.py`：写入 `question_answer.md`、`question_answer_translated.md`、`<token>_answer.md`、`<eval_token>_evaluate_<answer_token>_answer.md` 等。
  - `translator.py`：翻译原始问答并生成模型回答。
  - `evaluator.py`：用指定模型生成回答并评估（同一模型）。
  - `workflow.py`：爬取/翻译/评估的调度入口。
  - `utils/`：重排数据、模型名规范化、文本处理等。
- `main.py`：统一 CLI，支持 `crawl` / `translate` / `evaluate` / `restructure`。
- `scripts/evaluate_openai.py`：单独评估脚本，按模型自动命名文件。
- `data/`：默认输出目录，每个问题一个子目录，包含：
  - `question_answer.md`、`question_answer_translated.md`
  - `<answer_token>_answer.md`（如 `gpt4o_answer.md`、`gpt5_answer.md`）
  - `<eval_token>_evaluate_<answer_token>_answer.md`
  - `metadata.json`、`translation_raw.json`

## 快速开始
1) 安装依赖：`uv sync`
2) 抓取问答：`uv run python main.py crawl --limit 5 --out-dir data --reverse`
3) 翻译内容：`uv run python main.py translate --out-dir data --limit 5 --verbose`
4) 评估回答（回答与评估用同一模型）：  
   ```
   uv run python main.py evaluate \
     --model gpt-4.1 \
     --base-url https://api.openai.com/v1/chat/completions \
     --reverse --limit 10 --verbose
   ```  
   - 需在 `.env` 配置 `OPENAI_API_KEY`  
   - `--reverse` 最新优先，`--limit` 截断处理数量，`--force` 重跑已存在文件

## 评估模型文件命名
- 模型名会规范化为 token（去掉版本小数/特殊字符），生成：
  - `<token>_answer.md`
  - `<eval_token>_evaluate_<answer_token>_answer.md`

## 其他
- 重排/清理旧文件：`uv run python main.py restructure --out-dir data --cleanup-old`
- 独立评估脚本：`uv run python scripts/evaluate_openai.py --model gpt-4.1 --answer-model gpt-4.1 --reverse-order --limit 10 --verbose`

## 示例命令
- **抓取最新 20 条 Kubernetes 问答**：  
  ```
  uv run python main.py crawl \
    --tag kubernetes \
    --limit 20 --page-size 50 \
    --out-dir data --reverse
  ```
- **只翻译最近 10 条（跳过已有译文）**：  
  ```
  uv run python main.py translate \
    --out-dir data --limit 10 --verbose
  ```
- **评估最近 8 条（回答与评估同一模型，跳过已有评估）**：  
  ```
  uv run python main.py evaluate \
    --model gpt-4.1 \
    --base-url https://api.openai.com/v1/chat/completions \
    --reverse --limit 8 --verbose
  ```
- **评估使用不同回答模型（文件名自动按模型 token 命名）**：  
  先用本地/其他模型生成回答，再评估：`<answer_token>_answer.md`、`<eval_token>_evaluate_<answer_token>_answer.md` 会自动生成。  
  例如：  
  ```
  uv run python main.py evaluate \
    --model gpt-4o \
    --base-url https://api.openai.com/v1/chat/completions \
    --reverse --limit 5
  ```
- **重排并清理旧格式文件**：  
  ```
  uv run python main.py restructure --out-dir data --cleanup-old
  ```
