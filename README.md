# 模型转换测试分析 Agent

基于 LangGraph 框架的自动化模型转换测试日志分析工具。实现"日志提取 → 错误分类 → 根因分析 → 修复验证 → 汇总报告"全流程自动化。

## 架构

```
┌─────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  日志提取    │───▶│  错误分类         │───▶│  历史案例加载     │
│  (Tool)      │    │  (Subgraph)      │    │  (Tool)          │
└─────────────┘    └──────────────────┘    └──────────────────┘
                                                     │
                                                     ▼
┌─────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  汇总报告    │◀──│  保存历史         │◀──│  调试分析+重试     │
│  (Tool)      │    │  (Tool)          │    │  (Subgraph)      │
└─────────────┘    └──────────────────┘    └──────────────────┘
```

三层设计：
- **工具层（Tools）**：纯代码执行逻辑，不依赖大模型
- **技能层（Skills）**：依赖大模型进行理解与决策
- **工作流层（Graphs）**：LangGraph 编排，支持子图独立运行

## 安装

```bash
pip install -e ".[dev]"
```

## 使用

### 交互模式（中文界面）

```bash
python -m model_test_agent
```

### 命令行模式

```bash
# 完整流程
python -m model_test_agent --log-dir ./logs --config ./models.yaml --output ./output

# 仅分类
python -m model_test_agent --log-dir ./logs --mode classify

# 仅调试分析
python -m model_test_agent --log-dir ./logs --config ./models.yaml --mode debug

# SNR 分析（独立子图）
python -m model_test_agent --config ./models.yaml --mode snr

# 英文界面
python -m model_test_agent --locale en
```

### 使用示例数据

```bash
python -m model_test_agent \
  --log-dir examples/sample_logs \
  --config examples/sample_config/models.yaml \
  --output ./output \
  --mode classify
```

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
├── examples/               # 示例日志和配置
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
