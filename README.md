# Model Debug Agent

智能体辅助日志分析

一个面向“模型转换 / 编译失败日志”的单机分析工具。主流程是：

`日志提取 -> 源码定位 -> 错误分类 -> 调试分析 -> 汇总报告`

输出包括：
- 终端过程摘要
- Excel 报告
- 可交互 HTML 报告
- 可选的共享评注模式（`Checked By / Comment`）

## 3 分钟上手

### 1. 安装

```bash
conda create -n model-test-agent python=3.10 -y
conda activate model-test-agent
pip install -r requirements-dev.txt
pip install -e .
cp .env.example .env
```

Python 最低版本是 `3.10`。

### 2. 配 LLM

默认的 [llm.yaml](/Users/wu/Documents/projects/model_test_agent/config/llm.yaml) 已按 DeepSeek 预置，通常只需要在 `.env` 里填：

```bash
DEEPSEEK_API_KEY=your-key
MTA_MODEL_DEFAULT=deepseek-chat
```

如果你用内部部署的 Qwen / Kimi，改 [config/llm.yaml](/Users/wu/Documents/projects/model_test_agent/config/llm.yaml) 里的 `base_url / api_key / model` 即可。

### 3. 跑 demo

```bash
model-test-agent \
  --target-dir examples/demo_models/Models_35 \
  --output ./output/demo \
  --mode full
```

## 常用参数

- `--target-dir`
  必填。目录下每个一级子目录都视为一个模型目录。

- `--target-layout-config`
  可选。显式指定布局配置；不传时默认读取 `target-dir/target_layout.yaml`。

- `--codebase-root`
  可选。宿主机源码根目录，用于补源码上下文。

- `--docker-script`
  可选。进入 Docker 环境的脚本路径，用于读取容器内源码或执行修复命令。

- `--rag-dir`
  可选。本地知识目录，支持 `txt / md / json / csv / xlsx`。

最常用命令：

```bash
# 完整流程
model-test-agent --target-dir ./Models_to_be_tested --output ./output

# 只做分类
model-test-agent --target-dir ./Models_to_be_tested --mode classify

# 只做调试分析
model-test-agent --target-dir ./Models_to_be_tested --mode debug

# 宿主机源码模式
model-test-agent --target-dir ./Models_to_be_tested --codebase-root /path/to/compiler/repo

# 通过脚本进入已有 Docker 环境
model-test-agent --target-dir ./Models_to_be_tested --docker-script ./enter_container.sh

# 启用本地 RAG
model-test-agent --target-dir ./Models_to_be_tested --rag-dir ./rag_materials

# 用本地服务打开共享评注版报告
model-test-agent --serve-report ./output/test_report_20260315_120000.html

# 启动远端友好的 Web UI
model-test-agent --ui --ui-port 7860
```

共享评注模式会在 HTML 报告旁边生成一个同名的 `.review.json` 文件，用来保存 `Checked By` 和 `Comment`。这样同一个目录下的报告可以共享同一份评注记录。

如果你在 SSH 服务器上运行 UI，推荐本地这样转发：

```bash
ssh -L 7860:127.0.0.1:7860 user@remote-host
```

然后浏览器打开：

```text
http://127.0.0.1:7860
```

这个 UI 的目录浏览器读取的是服务器文件系统，不是你本机浏览器的文件系统。

## 目录约定

默认目录结构：

```text
Models_to_be_tested/
  01-1_yolo/
    01-1_yolo.yaml
    package_info.json
    Converter_result/
      convert/
        .log/
          20260312_101500.txt
```

默认规则是：
- 配置文件：`<model-name>.yaml`
- 重要补充配置：`Config/legacy.yaml`（也可在 layout 里自定义）
- 包信息：`package_info.json`
- 日志目录：`Converter_result/convert/.log/`
- 日志文件：取目录里最新的文件

如果现场目录不一样，就加一个 `target_layout.yaml`。示例见 [examples/demo_models/Models_35/target_layout.yaml](/Users/wu/Documents/projects/model_test_agent/examples/demo_models/Models_35/target_layout.yaml)。

如果除了主配置文件外，`Config/legacy.yaml`、`Config/*.yaml` 这类文件也很关键，可以在 layout 里显式声明：

```yaml
config_patterns:
  - "{model_name}.yaml"
config_context_patterns:
  - "{model_name}.yaml"
  - Config/legacy.yaml
  - Config/*.yaml
config_context_max_files: 4
```

程序不会把整个配置目录原样塞进 prompt，而是：
- 只取你声明的重要配置文件
- 每个模型最多取前几个文件
- 再按 [config/debug.yaml](/Users/wu/Documents/projects/model_test_agent/config/debug.yaml) 里的预算裁剪

## 源码上下文怎么接

推荐三种方式：

### 1. 直接在 Docker 里运行

最直接。如果日志里的源码路径本来就是容器内路径，这种方式最省心。

```bash
model-test-agent --target-dir ./Models_to_be_tested
```

### 2. 在宿主机运行，指定源码根目录

```bash
model-test-agent \
  --target-dir ./Models_to_be_tested \
  --codebase-root /path/to/compiler/repo
```

程序会先从日志里提取一个最像报错位置的文件路径和行号，再在 `codebase-root` 下按“路径后缀匹配”找真实文件。  
例如日志里是：

```text
/usr/local/lib/python/dist-packages/snc_py_api/foo/bar.py:128
```

它会尝试类似这些路径：

```text
/path/to/compiler/repo/usr/local/lib/python/dist-packages/snc_py_api/foo/bar.py
/path/to/compiler/repo/dist-packages/snc_py_api/foo/bar.py
/path/to/compiler/repo/snc_py_api/foo/bar.py
/path/to/compiler/repo/foo/bar.py
```

谁存在就用谁。找不到就退回到“原始日志 + RAG”继续分析，不会中断流程。

### 3. 在宿主机运行，通过脚本进入已有 Docker 环境

```bash
model-test-agent \
  --target-dir ./Models_to_be_tested \
  --docker-script ./enter_container.sh
```

脚本只需要接受一条命令并在容器里执行，例如：

```bash
#!/usr/bin/env bash
docker exec your_container_name bash -lc "$1"
```

这样程序会：
- 通过脚本读取容器内源码上下文
- 在 `--auto-fix` 打开时，也通过脚本执行修复命令

## 关于 traceback 路径

这是当前 MVP 的边界之一。

真实 traceback 里常常会有多层调用路径，出现的文件不一定就是最终根因文件。当前版本会：

1. 从日志里提取所有像源码路径的候选
2. 优先选路径更长、层级更深的候选
3. 只读取这个候选文件附近的一小段上下文
4. 同时把原始日志和 RAG 结果一起交给 LLM

所以当前“源码上下文”是高价值辅助线索，但不是对根因文件的绝对保证。

## 本地 RAG

你可以直接准备一个目录，例如：

```text
rag_materials/
  compiler_notes.md
  known_issues.txt
  workaround.xlsx
```

运行：

```bash
model-test-agent \
  --target-dir ./Models_to_be_tested \
  --rag-dir ./rag_materials
```

当前行为：
- 默认先做本地词法检索，离线也能用
- 如果 [config/llm.yaml](/Users/wu/Documents/projects/model_test_agent/config/llm.yaml) 里配置了 `embedding` profile，会自动追加 embedding 相似度
- 检索结果会作为外部知识一起送进 debug 分析

## 长上下文怎么调

如果以后换成长上下文模型，优先改 [config/debug.yaml](/Users/wu/Documents/projects/model_test_agent/config/debug.yaml)，不用先改代码。

最常调的是：
- `source_context.context_lines`
- `prompt_budget.max_error_samples`
- `prompt_budget.max_log_chars_per_sample`
- `prompt_budget.max_source_chars_per_sample`
- `retrieval.top_k`

简单理解：
- 短上下文模型：这些值保持小一些更稳
- 长上下文模型：可以逐步调大，但建议一次只改 1 到 2 项

## 配置文件

最常用的几个：

| 文件 | 用途 |
|------|------|
| [config/llm.yaml](/Users/wu/Documents/projects/model_test_agent/config/llm.yaml) | LLM profile 配置 |
| [config/debug.yaml](/Users/wu/Documents/projects/model_test_agent/config/debug.yaml) | 控制源码上下文、日志裁剪和 RAG 切块大小 |
| [config/error_keywords.yaml](/Users/wu/Documents/projects/model_test_agent/config/error_keywords.yaml) | 日志关键词分类规则 |
| [config/report.yaml](/Users/wu/Documents/projects/model_test_agent/config/report.yaml) | 报告列和样式 |
| [config/i18n.yaml](/Users/wu/Documents/projects/model_test_agent/config/i18n.yaml) | 中英文文案 |
| [history/cases.json](/Users/wu/Documents/projects/model_test_agent/history/cases.json) | 历史调试案例 |

## 其他参数

| 参数 | 说明 |
|------|------|
| `--output` | 报告和图表输出目录，默认 `./output` |
| `--mode` | `full / classify / debug / snr` |
| `--auto-fix` | 自动执行修复命令 |
| `--max-retries` | 修复失败时最大重试次数，默认 `2` |
| `--llm-config` | 覆盖默认的 `config/llm.yaml` |
| `--locale` | `zh / en` |
| `--check-api` | 检查所有 LLM profile 后退出 |
| `--skip-health-check` | 跳过启动前 LLM 预检 |
| `--show-graph` | 打印工作流图结构后退出 |
| `--export-graph` | 导出图结构到 `.md` 或 `.png` |

`snr` 模式目前还是实验性占位能力，适合开发验证，不建议当成稳定主流程。

## 测试

```bash
pytest -q
```

## 什么时候用 `python -m`

```bash
python -m model_test_agent
```

只在这两种情况推荐：
- 你还没安装脚本入口，临时从源码目录直接运行
- 你在调试 [__main__.py](/Users/wu/Documents/projects/model_test_agent/src/model_test_agent/__main__.py)
