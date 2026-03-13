# 模型转换测试分析 Agent

基于 LangGraph 框架的自动化模型转换测试日志分析工具。实现"日志提取 → 错误分类 → 根因分析 → 修复验证 → 汇总报告"全流程自动化。

## 架构

```
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  日志提取          │───▶│  错误分类         │───▶│  调试分析+重试    │
│  模型配置加载      │    │  (Subgraph)      │    │  (Subgraph)      │
└──────────────────┘    └──────────────────┘    └──────────────────┘
                                                          │
                                                          ▼
                         ┌──────────────────┐    ┌──────────────────┐
                         │  汇总报告         │◀──│  保存历史案例      │
                         │  (Tool)          │    │  (Tool)          │
                         └──────────────────┘    └──────────────────┘
```

三层设计：
- **工具层（Tools）**：纯代码执行逻辑，不依赖大模型
- **技能层（Skills）**：依赖大模型进行理解与决策
- **工作流层（Graphs）**：LangGraph 编排，支持子图独立运行

## 安装

```bash
pip install -r requirements-dev.txt
pip install -e .
```

如果你用 `conda`，更推荐先建独立环境：

```bash
conda create -n model-test-agent python=3.11 -y
conda activate model-test-agent
pip install -r requirements-dev.txt
pip install -e .
```

Python 最低版本现在是 `3.10`，推荐直接用 `3.11`。

## 使用

### 交互模式（中文界面）

```bash
model-test-agent
```

### 命令行模式

```bash
# 完整流程
model-test-agent --target-dir ./Models_35 --output ./output

# 仅分类
model-test-agent --target-dir ./Models_35 --mode classify

# 仅调试分析
model-test-agent --target-dir ./Models_35 --mode debug

# SNR 分析（独立子图）
model-test-agent --target-dir ./Models_35 --mode snr

# 英文界面
model-test-agent --target-dir ./Models_35 --locale en

# 跳过启动前 LLM 健康检查
model-test-agent --target-dir ./Models_35 --skip-health-check
```

### 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--target-dir` | — | 目标目录路径。目录下每个一级子目录视为一个测试模型目录 |
| `--output` | `./output` | 报告和图表的输出目录 |
| `--mode` | `full` | 运行模式：`full` 完整流程 / `classify` 仅分类 / `debug` 仅调试分析 / `snr` 仅 SNR 分析 |
| `--auto-fix` | `false` | 自动在 Docker 中执行修复命令 |
| `--max-retries` | `2` | 修复失败时的最大重试次数 |
| `--llm-config` | 内置路径 | 覆盖默认的 `config/llm.yaml` 路径 |
| `--locale` | 系统语言 | 界面语言：`zh` 中文 / `en` 英文 |
| `--check-api` | — | 对所有 LLM profile 做健康检查后退出 |
| `--skip-health-check` | — | 跳过启动前的 LLM 连通性预检（服务不稳定时加速启动） |
| `--show-graph` | — | 在终端打印工作流图结构后退出 |
| `--export-graph` | — | 导出工作流图到文件，支持 `.md`（Mermaid）和 `.png` |

### 使用示例数据

```bash
model-test-agent \
  --target-dir examples/demo_models/Models_35 \
  --output ./output/demo \
  --mode full
```

`target-dir` 下面每个一级子目录都会被当成一个模型目录处理，程序会在该子目录内部读取：
- 配置脚本（如 `model_config.yaml` / `config.yaml`）
- `package_info.json`
- 运行日志（递归查找 `.log`）

### `python -m` 什么时候用

```bash
python -m model_test_agent
```

这个方式主要适合两种情况：
- 你还没安装脚本入口，只是临时从源码目录直接运行。
- 你在调试 `src/model_test_agent/__main__.py`，想明确指定解释器。

日常使用时，安装后的 `model-test-agent` 更自然，也更符合 CLI 工具习惯。

## 配置

| 文件 | 用途 |
|------|------|
| `config/llm.yaml` | 大模型 API 配置（支持多 profile） |
| `config/error_keywords.yaml` | 错误分类关键词和正则规则 |
| `config/report.yaml` | 报告列定义和样式配置 |
| `config/i18n.yaml` | 中英文界面文案 |
| `history/cases.json` | 历史调试案例存储 |

### 添加新的 LLM Profile

编辑 `config/llm.yaml`：

```yaml
my_custom_model:
  base_url: "http://your-server:8000/v1"
  api_key: "your-key"
  model: "your-model-name"
  temperature: 0.1
  max_tokens: 4096
```

## 子图独立运行

每个子图可以独立调用，无需运行完整流程：

```python
from model_test_agent.graphs import build_classification_subgraph

graph = build_classification_subgraph().compile()
result = graph.invoke({"errors": errors, "models": models, "error_groups": {}})
```

## 测试

```bash
pytest tests/ -v
```

## 项目结构

```
model_test_agent/
├── config/                 # 配置文件（LLM、关键词、报告、国际化）
├── history/                # 历史调试案例
├── examples/               # 示例模型目录
├── src/model_test_agent/
│   ├── tools/              # 工具层：日志提取、配置读取、Docker执行、报告生成
│   ├── skills/             # 技能层：错误分类、调试分析（依赖LLM）
│   ├── graphs/             # 工作流层：主图 + 可独立运行的子图
│   ├── llm/                # LLM客户端抽象
│   ├── viz/                # 可视化：终端UI、图表生成
│   ├── i18n.py             # 国际化
│   └── __main__.py         # CLI入口
└── tests/                  # 测试
```
