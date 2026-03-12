"""Skill: classify extracted errors into categories using LLM.

While the Tool-layer :class:`LogExtractor` does keyword-based classification,
this Skill adds LLM-powered refinement for ambiguous cases.  It can also
reclassify errors whose keyword match seems wrong based on full context.
"""

from __future__ import annotations

import json
import re
from typing import Any

from model_test_agent.skills.base import BaseSkill
from model_test_agent.state import ErrorEntry, ModelInfo

_SYSTEM_PROMPT = """\
你是一个模型转换测试错误分类专家。你的任务是根据日志片段和模型配置，
将每个错误归类到以下类别之一：

- shape_mismatch: 张量形状/维度不匹配
- dtype_error: 数据类型不兼容或不支持的量化类型
- missing_operator: 目标框架中未实现的算子
- weight_loading: 权重加载或 checkpoint 解析失败
- memory_error: GPU/CPU 内存不足
- numerical_error: 数值不稳定 (NaN/Inf)
- io_error: 文件系统 I/O 错误
- unknown: 无法分类，需要人工检查

规则：
1. 优先根据错误日志内容判断，而非模型名称。
2. 如果一个错误同时匹配多个类别，选择最具体的那个。
3. 返回格式为 JSON 数组，每个元素包含 index 和 category。
"""

_USER_TEMPLATE = """\
以下是需要分类的错误列表。每个错误附带其初始关键词分类和上下文日志。
请根据完整上下文判断分类是否准确，并返回修正后的分类结果。

模型配置信息：
{model_info}

错误列表：
{error_list}

请返回 JSON 数组，格式如下（不要添加其他文字）：
[{{"index": 0, "category": "shape_mismatch"}}, ...]
"""


class ErrorClassifierSkill(BaseSkill):
    """Use LLM to refine error classification.

    Parameters
    ----------
    llm_profile : str
        LLM config profile (default: ``"classifier"``).
    batch_size : int
        Max errors to send per LLM call (to stay within context limits).
    """

    def __init__(self, llm_profile: str = "classifier", batch_size: int = 20, **kwargs: Any) -> None:
        super().__init__(llm_profile=llm_profile, **kwargs)
        self.batch_size = batch_size

    def run(
        self,
        errors: list[ErrorEntry],
        models: list[ModelInfo] | None = None,
    ) -> list[ErrorEntry]:
        """Classify / reclassify errors.  Returns the same list with updated categories."""
        if not errors:
            return errors

        model_map = {m.name: m for m in (models or [])}

        # Process in batches to fit context window
        for batch_start in range(0, len(errors), self.batch_size):
            batch = errors[batch_start : batch_start + self.batch_size]
            self._classify_batch(batch, model_map)

        return errors

    def _classify_batch(
        self,
        batch: list[ErrorEntry],
        model_map: dict[str, ModelInfo],
    ) -> None:
        """Classify one batch of errors in-place."""
        # Build model info string
        seen_models = {e.model_name for e in batch}
        model_lines = []
        for name in sorted(seen_models):
            m = model_map.get(name)
            if m:
                model_lines.append(
                    f"- {m.name}: quantization={m.quantization}, "
                    f"has_test_data={m.has_test_data}, extra={m.extra}"
                )
            else:
                model_lines.append(f"- {name}: (无配置信息)")
        model_info = "\n".join(model_lines) if model_lines else "无"

        # Build error list string
        error_lines = []
        for idx, err in enumerate(batch):
            error_lines.append(
                f"[{idx}] model={err.model_name}, "
                f"initial_category={err.category}, "
                f"keyword={err.matched_keyword}\n"
                f"    message: {err.message}\n"
                f"    context: {err.raw_context[:500]}"
            )
        error_list = "\n\n".join(error_lines)

        user_msg = _USER_TEMPLATE.format(model_info=model_info, error_list=error_list)
        messages = self._build_messages(_SYSTEM_PROMPT, user_msg)

        try:
            response = self._llm.invoke_messages(messages)
            classifications = self._parse_response(response)
            for item in classifications:
                idx = item.get("index", -1)
                cat = item.get("category", "")
                if 0 <= idx < len(batch) and cat:
                    batch[idx].category = cat
        except Exception:
            # If LLM fails, keep the keyword-based classification
            pass

    @staticmethod
    def _parse_response(text: str) -> list[dict[str, Any]]:
        """Extract JSON array from LLM response, tolerating markdown fences."""
        text = text.strip()
        # Remove markdown code fences
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            text = match.group(1)
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
        return []
