# 模型转换测试分析 Agent

一个面向“模型转换/编译失败日志”的单机分析工具。  
它会按下面这条主线工作：

`日志提取 -> 源码定位 -> 错误分类 -> 调试分析 -> 汇总报告`

适合的场景：
- 自动化测试失败后，批量整理模型日志
- 从日志里提取报错位置，再补源码上下文给大模型推理
- 输出终端摘要、Excel 报告和可交互 HTML 报告

## 3 分钟上手

### 1. 安装

```bash
conda create -n model-test-agent python=3.11 -y
conda activate model-test-agent
pip install -r requirements-dev.txt
pip install -e .
cp .env.example .env
```

Python 最低版本是 `3.10`。

### 2. 配 LLM

默认的 [llm.yaml](/Users/wu/Documents/projects/model_test_agent/config/llm.yaml) 已经按 DeepSeek 接口预置，通常只需要在 `.env` 里填：

```bash
DEEPSEEK_API_KEY=your-key
MTA_MODEL_DEFAULT=deepseek-chat
```

如果你用的是内部部署的 Qwen / Kimi，只需要改 [llm.yaml](/Users/wu/Documents/projects/model_test_agent/config/llm.yaml) 里对应 profile 的 `base_url / api_key / model`。

### 3. 跑 demo

```bash
model-test-agent \
  --target-dir examples/demo_models/Models_35 \
  --output ./output/demo \
  --mode full
```

跑完后会得到：
- 终端过程摘要
- `xlsx` 报告
- 可交互 `html` 报告

## 先记住这 3 个参数

- `--target-dir`
  模型测试目录。目录下每个一级子目录都会被当成一个模型目录。

- `--target-layout-config`
  可选。用于显式指定目录布局规则；不传时默认读取 `target-dir/target_layout.yaml`。

- `--codebase-root`
  可选。源码根目录。日志里提取到报错源码路径后，程序会从这里读取上下文。

最常用命令：

```bash
# 完整流程
model-test-agent --target-dir ./Models_35 --output ./output

# 只做分类
model-test-agent --target-dir ./Models_35 --mode classify

# 只做调试分析
model-test-agent --target-dir ./Models_35 --mode debug

# 指定源码根目录（宿主机模式）
model-test-agent --target-dir ./Models_35 --codebase-root /path/to/compiler/repo

# 指定 layout 配置
model-test-agent --target-dir ./Models_35 --target-layout-config ./Models_35/target_layout.yaml
```

## 目录约定

默认情况下，`target-dir` 下面每个一级子目录都视为一个模型目录。程序会在每个模型目录内寻找：
- 配置文件，如 `model_config.yaml` / `config.yaml`
- `package_info.json`
- 日志文件，或名字以 `.log` 结尾的日志目录

示意：

```text
Models_35/
  01-1_yolo/
    model_config.yaml
    package_info.json
    runs/
      20260312_101500/
        convert.log
```

如果你的现场目录不是这个样子，就加一个 `target_layout.yaml`。

示例：

```yaml
model_dir_pattern: "*"
config_patterns:
  - model_config.yaml
  - config.yaml
package_info_patterns:
  - package_info.json
log_dir_patterns:
  - "*.log"
latest_log_file: true
```

这表示：
- 一级子目录是模型目录
- 配置文件按 `config_patterns` 找
- `package_info.json` 按 `package_info_patterns` 找
- 如果存在 `.log` 目录，就读取里面最新的日志文件

demo 示例布局文件在 [target_layout.yaml](/Users/wu/Documents/projects/model_test_agent/examples/demo_models/Models_35/target_layout.yaml)。

## 源码上下文怎么接

这是现在最关键的一层：程序会先从日志里提取报错源码路径和行号，再尝试读取源码上下文，然后把“日志 + 源码片段”一起交给 LLM。

你有两种推荐方式：

### 方式 1：直接在 Docker 里运行

这是最直接的方式。  
如果日志里的源码路径本来就是容器内路径，那么程序和源码在同一个运行环境里，路径解析最省心。

```bash
model-test-agent --target-dir ./Models_35
```

### 方式 2：在宿主机运行，显式指定源码根目录

如果程序跑在宿主机，但源码仓库也能在宿主机访问，就传：

```bash
model-test-agent \
  --target-dir ./Models_35 \
  --codebase-root /path/to/compiler/repo
```

程序会按日志中的路径后缀去匹配这个仓库里的真实文件。

如果源码找不到，也不会中断流程，而是降级成：
- 仅根据日志继续推理

## 输出内容

完整流程会生成：
- 终端摘要
- Excel 报告
- HTML 交互报告

HTML 报告里可以：
- 按状态和错误类别筛选
- 展开查看命中的日志源文件
- 查看 `Suggested Fix`
- 在本地打开报告时直接 `Open File`
- 在 HTTP/SSH 转发访问时自动降级成 `Copy Path`

## 工作流结构

主流程：

```text
extract
  -> source_context
  -> classification
  -> debug
  -> save_history
  -> report
```

三层职责：
- `tools/`：确定性工具，不依赖 LLM
- `skills/`：LLM 推理
- `graphs/`：LangGraph 编排

## 配置文件

最常用的几个：

| 文件 | 用途 |
|------|------|
| [config/llm.yaml](/Users/wu/Documents/projects/model_test_agent/config/llm.yaml) | LLM profile 配置 |
| [config/error_keywords.yaml](/Users/wu/Documents/projects/model_test_agent/config/error_keywords.yaml) | 日志关键词分类规则 |
| [config/report.yaml](/Users/wu/Documents/projects/model_test_agent/config/report.yaml) | 报告列和样式 |
| [config/i18n.yaml](/Users/wu/Documents/projects/model_test_agent/config/i18n.yaml) | 中英文文案 |
| [history/cases.json](/Users/wu/Documents/projects/model_test_agent/history/cases.json) | 历史调试案例 |

## 其他常用参数

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
