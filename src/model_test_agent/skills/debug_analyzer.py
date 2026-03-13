"""Skill: analyze errors and generate debug / fix suggestions.

This is the most LLM-intensive skill.  It receives classified error groups,
historical cases, and model configuration, then outputs structured fix
recommendations with optional Docker commands for automated verification.
"""

from __future__ import annotations

import json
import re
from typing import Any

from model_test_agent.skills.base import BaseSkill
from model_test_agent.state import DebugResult, ErrorEntry, FixStatus, ModelInfo

_SYSTEM_PROMPT = """\
你是一个模型转换调试专家。你的任务是分析一组同类错误，找出根本原因，
并给出具体的修复建议。如果可能，还要生成可以在 Docker 容器中执行的
验证命令。

你的分析应当包括：
1. 根本原因分析（root_cause）：为什么出现这个错误
2. 修复建议（suggested_fix）：具体怎么做
3. 验证命令（fix_command）：可选的 shell 命令，用于在 Docker 中验证修复

返回格式为 JSON 对象：
{{
  "root_cause": "...",
  "suggested_fix": "...",
  "fix_command": "..."
}}
"""

_USER_TEMPLATE = """\
## 错误类别：{category}

## 影响的模型
{model_info}

## 错误样本（共 {total} 个，展示前 {shown} 个）
{error_samples}

## 历史案例参考
{history_context}

请分析以上信息，给出根本原因、修复建议和验证命令。
返回 JSON 格式（不要添加其他文字）。
"""


class DebugAnalyzerSkill(BaseSkill):
    """Analyze error groups and produce :class:`DebugResult` objects.

    Parameters
    ----------
    llm_profile : str
        LLM config profile (default: ``"debugger"``).
    max_samples : int
        Maximum error samples per category sent to LLM.
    """

    def __init__(self, llm_profile: str = "debugger", max_samples: int = 5, **kwargs: Any) -> None:
        super().__init__(llm_profile=llm_profile, **kwargs)
        self.max_samples = max_samples

    def run(
        self,
        error_groups: dict[str, list[ErrorEntry]],
        models: list[ModelInfo] | None = None,
        history_per_category: dict[str, list[dict[str, Any]]] | None = None,
    ) -> list[DebugResult]:
        """Analyze each error category and return debug results."""
        model_map = {m.name: m for m in (models or [])}
        history_per_category = history_per_category or {}
        results: list[DebugResult] = []

        for category, errors in error_groups.items():
            relevant = history_per_category.get(category, [])
            result = self._analyze_category(category, errors, model_map, relevant)
            results.append(result)

        return results

    def _analyze_category(
        self,
        category: str,
        errors: list[ErrorEntry],
        model_map: dict[str, ModelInfo],
        history_cases: list[dict[str, Any]],  # pre-retrieved, already ranked
    ) -> DebugResult:
        affected = sorted({e.model_name for e in errors})

        # Build model info
        model_lines = []
        for name in affected:
            m = model_map.get(name)
            if m:
                model_lines.append(
                    f"- {m.name}: quantization={m.quantization}, "
                    f"has_test_data={m.has_test_data}"
                )
            else:
                model_lines.append(f"- {name}")
        model_info = "\n".join(model_lines) if model_lines else "无"

        # Build error samples
        samples = errors[: self.max_samples]
        sample_lines = []
        for i, err in enumerate(samples):
            sample_lines.append(
                f"### 样本 {i + 1}（{err.model_name}，行 {err.line_number}）\n"
                f"{err.raw_context[:600]}"
            )
        error_samples = "\n\n".join(sample_lines)

        # Build history context (cases already retrieved and ranked by SemanticRetriever)
        relevant_history = history_cases
        if relevant_history:
            history_lines = []
            for c in relevant_history[:3]:
                history_lines.append(
                    f"- [{c.get('id', '?')}] model={c.get('model_name')}, "
                    f"原因: {c.get('root_cause', '?')}, "
                    f"方案: {c.get('solution', '?')}, "
                    f"有效: {'是' if c.get('effective') else '否'}"
                )
            history_context = "\n".join(history_lines)
        else:
            history_context = "无相关历史案例"

        # Find history match
        history_match_id = relevant_history[0]["id"] if relevant_history else ""

        user_msg = _USER_TEMPLATE.format(
            category=category,
            model_info=model_info,
            total=len(errors),
            shown=len(samples),
            error_samples=error_samples,
            history_context=history_context,
        )
        messages = self._build_messages(_SYSTEM_PROMPT, user_msg)

        try:
            response = self._llm.invoke_messages(messages)
            parsed = self._parse_response(response)
            return DebugResult(
                error_category=category,
                affected_models=affected,
                root_cause=parsed.get("root_cause", "LLM 未返回分析结果"),
                suggested_fix=parsed.get("suggested_fix", ""),
                fix_command=parsed.get("fix_command", ""),
                fix_status=FixStatus.PENDING,
                history_match_id=history_match_id,
            )
        except Exception as exc:
            return DebugResult(
                error_category=category,
                affected_models=affected,
                root_cause=f"分析失败: {exc}",
                suggested_fix="",
                fix_command="",
                fix_status=FixStatus.SKIPPED,
                history_match_id=history_match_id,
            )

    @staticmethod
    def _parse_response(text: str) -> dict[str, Any]:
        text = text.strip()
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            text = match.group(1)
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass
        return {"root_cause": text}
