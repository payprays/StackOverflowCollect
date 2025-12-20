# StackOverflow Collect

一个用于抓取、分析和评估 Stack Overflow Kubernetes 相关问答的工具集。支持 LLM 回答生成、YAML 校验、覆盖率分析和自动评估。

## 功能概览

| 命令        | 功能                                            |
| ----------- | ----------------------------------------------- |
| `crawl`     | 抓取 Stack Overflow 指定标签的问答              |
| `answer`    | 使用 LLM 为问题生成回答                         |
| `evaluate`  | 对 LLM 回答进行 Lint 检查、覆盖率分析和质量评估 |
| `translate` | 翻译原始问答为中文                              |

---

## 快速开始

### 1. 安装依赖
<!--  -->
```bash
uv sync
```

### 2. 配置环境变量

创建 `.env` 文件：
```bash
OPENAI_API_KEY=sk-your-openai-key
STACK_API_KEY=your-stack-exchange-api-key  # 可选，提高 API 配额
```

### 3. 抓取问答 (Crawl)

```bash
uv run python main.py crawl \
  --tag kubernetes \
  --limit 20 \
  --out-dir data
```

**参数说明：**
- `--tag`: Stack Overflow 标签（默认 `kubernetes`）
- `--limit`: 抓取数量
- `--out-dir`: 输出目录
- `--stack-key`: Stack Exchange API Key（可从 `.env` 自动加载）

### 4. 生成 LLM 回答 (Answer)

```bash
uv run python main.py answer \
  --out-dir data \
  --model gpt-5.1 \
  --base-url https://api.openai.com/ \
  --workers 4 \
  --limit 10
```

**参数说明：**
- `--model`: 使用的 LLM 模型
- `--base-url`: API 端点
- `--workers`: 并行 worker 数量
- `--force`: 重新生成已存在的回答

### 5. 评估回答 (Evaluate)

```bash
uv run python main.py evaluate \
  --input-dir data \
  --model gpt-5.1 \
  --base-url https://api.openai.com/ \
  --workers 3 \
  --limit 10
```

**评估包括：**
1. **Lint 检查**: kubeval + datree + kubectl dry-run
2. **覆盖率分析**: LLM 回答与人类回答的 YAML 块覆盖对比
3. **质量评估**: 使用 LLM 对回答质量进行评分

---

## CSV 输出列说明

运行后生成的 `results.csv` 包含以下列：

| 列名                              | 说明                                                          |
| --------------------------------- | ------------------------------------------------------------- |
| `Question ID`                     | Stack Overflow 问题 ID                                        |
| `Question Title`                  | 问题标题                                                      |
| `Question Body`                   | 问题正文（Markdown 格式）                                     |
| `Question Tags`                   | 问题标签，逗号分隔                                            |
| `Answer ID`                       | 人类回答 ID                                                   |
| `Answer Body`                     | 人类回答正文                                                  |
| `Answer Creation Date`            | 人类回答创建时间                                              |
| `Question Creation Date`          | 问题创建时间                                                  |
| `gpt-5.1_Answer`                  | LLM 生成的回答内容                                            |
| `lint`                            | Lint 检查结果摘要（如 `kubeval:4/4; datree:3/4; dryrun:4/4`） |
| `gpt-5.1_Answer_CodeBlocks`       | 从 LLM 回答中提取的 YAML 代码块                               |
| `lint_logs`                       | Lint 检查的详细日志                                           |
| `gpt-5.1_Evaluate_gpt-5.1_Answer` | LLM 对自己回答的评估结果                                      |
| `gpt5_Coverage`                   | 覆盖率百分比（LLM 回答覆盖人类回答的 YAML 配置程度）          |

---

## 项目结构

```
src/
├── conf/
│   └── config.py          # 配置管理（环境变量加载）
├── domain/
│   └── models.py          # 数据模型定义（Question, Answer 等）
├── flows/
│   └── workflow.py        # 工作流调度（crawl, answer, evaluate）
├── services/
│   ├── stack_client.py    # Stack Exchange API 客户端
│   ├── storage.py         # 数据存储（文件 + CSV）
│   ├── evaluator.py       # LLM 评估器（生成回答、评估质量）
│   └── llm_client.py      # LLM API 客户端
└── utils/
    ├── rehydrate.py       # 从磁盘重新加载问题数据
    ├── yaml_lint.py       # YAML 校验（kubeval, datree, kubectl）
    ├── coverage.py        # 覆盖率分析
    ├── model_name.py      # 模型名规范化
    └── text.py            # 文本处理工具
```

### 模块功能说明

#### `src/services/stack_client.py`
- 封装 Stack Exchange API 调用
- 分页获取问题列表
- 获取问题对应的回答

#### `src/services/storage.py`
- 管理文件输出（`question_answer.md`, `gpt5_answer.md` 等）
- 管理 CSV 输出（自动添加列、更新行）
- 线程安全的数据持久化

#### `src/services/evaluator.py`
- 调用 LLM 生成回答
- 调用 LLM 进行质量评估
- 调用 LLM 进行覆盖率分析

#### `src/utils/yaml_lint.py`
- 从回答中提取完整的 K8s YAML 块
- 运行 kubeval 校验 YAML 合法性
- 运行 datree 检查最佳实践
- 运行 kubectl dry-run 验证资源创建

#### `src/utils/coverage.py`
- 比较人类回答和 LLM 回答的 YAML 配置
- 计算 key-path 覆盖率百分比

---

## 文件输出说明

每个问题在输出目录下生成一个子目录（格式：`YYYYMMDD_HHMMSS_slug`）：

| 文件                           | 说明                        |
| ------------------------------ | --------------------------- |
| `question.json`                | 问题元数据                  |
| `question_answer.md`           | 原始问答（问题 + 人类回答） |
| `gpt5_answer.md`               | LLM 生成的回答              |
| `gpt5_answer_raw.json`         | LLM 原始响应（调试用）      |
| `gpt5_evaluate_gpt5_answer.md` | LLM 评估结果                |
| `gpt5_coverage.json`           | 覆盖率分析详情              |

---

## 依赖工具

以下工具需要单独安装以启用完整功能：

| 工具      | 用途             | 安装                                                     |
| --------- | ---------------- | -------------------------------------------------------- |
| `kubeval` | YAML schema 校验 | [kubeval.io](https://kubeval.instrumenta.dev/)           |
| `datree`  | K8s 最佳实践检查 | [datree.io](https://datree.io/)                          |
| `kubectl` | dry-run 验证     | [kubernetes.io](https://kubernetes.io/docs/tasks/tools/) |

**Datree 离线模式：**
```bash
datree config set offline local
```

---

## 示例工作流

```bash
# 1. 抓取 100 条 Kubernetes 问答
uv run python main.py crawl --tag kubernetes --limit 100 --out-dir data

# 2. 生成 LLM 回答（8 并发）
uv run python main.py answer --out-dir data --model gpt-5.1 --workers 8 --limit 100

# 3. 评估回答质量（3 并发）
uv run python main.py evaluate --input-dir data --model gpt-5.1 --workers 3 --limit 100

# 4. 查看结果
open data/results.csv
```

---

## License

MIT
