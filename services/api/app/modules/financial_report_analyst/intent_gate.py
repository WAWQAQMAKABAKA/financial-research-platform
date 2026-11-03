"""M2a P0: deterministic intent gate, before any cell selection.

A question that asks for a comparison, a forecast, or something the platform
cannot classify is not a disclosure-fact lookup. It must fail closed *before*
retrieval or row selection, so that a literal token match inside a comparison
question ("营业收入比去年增长多少") can never publish the current-period value.

This is a small deterministic cue gate, not an LLM classifier and not an agent.
Ambiguity is a legitimate outcome. The gate can only remove questions from the
publication path; it never approves anything.
"""
from __future__ import annotations

from enum import StrEnum
import re
import unicodedata


INTENT_VERSION = "m2a-intent-gate-v1"


class Intent(StrEnum):
    FACT_LOOKUP = "FACT_LOOKUP"
    COMPARISON = "COMPARISON"
    FORWARD_VIEW = "FORWARD_VIEW"
    AMBIGUOUS = "AMBIGUOUS"


# Cue vocabulary is about question shape, not financial meaning. A question
# containing a comparison or forecast cue is not proof that the numbers differ;
# it is only proof that a facts-only lookup cannot answer it safely.
_FORWARD_CUES = (
    "预计", "预测", "展望", "预期", "明年", "未来", "全年", "下一年度",
    "下季度", "目标", "有望", "将会",
)
_COMPARISON_CUES = (
    "比去年", "同比", "环比", "增长", "下降", "上升", "增幅", "增速",
    "变化", "相比", "对比", "较上", "差额", "差异", "高于", "低于",
    "提升了", "减少了", "多了", "少了",
)
_AMBIGUOUS_CUES = (
    "为什么", "为何", "如何", "怎么", "是否", "评价", "看法", "建议",
    "意味着", "影响", "趋势", "前景", "分析",
)

_REASON = {
    Intent.COMPARISON: "COMPARISON_NOT_PUBLISHABLE",
    Intent.FORWARD_VIEW: "FORWARD_VIEW_NOT_PUBLISHABLE",
    Intent.AMBIGUOUS: "QUESTION_INTENT_AMBIGUOUS",
}


def _norm(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


def classify_intent(question: str) -> Intent:
    """Ordered cues: forward view, then comparison, then ambiguous, else fact."""
    text = _norm(question)
    if not text:
        return Intent.AMBIGUOUS
    if any(cue in text for cue in _FORWARD_CUES):
        return Intent.FORWARD_VIEW
    if any(cue in text for cue in _COMPARISON_CUES):
        return Intent.COMPARISON
    if any(cue in text for cue in _AMBIGUOUS_CUES):
        return Intent.AMBIGUOUS
    return Intent.FACT_LOOKUP


def rejection_reason(intent: Intent) -> str | None:
    return _REASON.get(intent)


def describe(question: str) -> dict:
    intent = classify_intent(question)
    return {
        "intent": intent.value,
        "intent_version": INTENT_VERSION,
        "rejection_reason": rejection_reason(intent),
    }
