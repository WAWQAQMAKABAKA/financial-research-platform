"""P0 intent gate: comparison / forward / ambiguous questions never publish."""
import pytest

from app.modules.financial_report_analyst import intent_gate as gate


@pytest.mark.parametrize("question", [
    "600760 中航沈飞 2026 年半年度合并利润表中营业收入是多少？",
    "合并利润表中净利润是多少？",
    "研发投入是多少？",
    "合并利润表中归属于母公司股东的净利润是多少？",
])
def test_fact_lookups_pass_the_gate(question):
    assert gate.classify_intent(question) is gate.Intent.FACT_LOOKUP


@pytest.mark.parametrize("question", [
    "合并利润表中营业收入比去年增长多少？",
    "营业收入同比增速是多少？",
    "本期净利润相比上期变化多少？",
    "毛利率是否高于去年？",
])
def test_comparisons_are_blocked(question):
    assert gate.classify_intent(question) is gate.Intent.COMPARISON


@pytest.mark.parametrize("question", [
    "2026 全年营业收入预计多少？",
    "明年营业收入会是多少？",
    "未来三年的收入展望如何？",
])
def test_forward_views_are_blocked(question):
    assert gate.classify_intent(question) is gate.Intent.FORWARD_VIEW


@pytest.mark.parametrize("question", [
    "公司经营情况如何？",
    "这项披露意味着什么？",
    "",
])
def test_ambiguous_questions_are_blocked(question):
    assert gate.classify_intent(question) is gate.Intent.AMBIGUOUS


def test_forward_takes_precedence_over_comparison():
    assert gate.classify_intent("预计同比增速是多少？") is gate.Intent.FORWARD_VIEW


def test_only_fact_lookup_has_no_rejection_reason():
    assert gate.rejection_reason(gate.Intent.FACT_LOOKUP) is None
    assert gate.rejection_reason(gate.Intent.COMPARISON) == "COMPARISON_NOT_PUBLISHABLE"
    assert gate.rejection_reason(gate.Intent.FORWARD_VIEW) == "FORWARD_VIEW_NOT_PUBLISHABLE"
    assert gate.rejection_reason(gate.Intent.AMBIGUOUS) == "QUESTION_INTENT_AMBIGUOUS"


def test_describe_exposes_version_and_reason():
    described = gate.describe("营业收入比去年增长多少？")

    assert described == {
        "intent": "COMPARISON",
        "intent_version": gate.INTENT_VERSION,
        "rejection_reason": "COMPARISON_NOT_PUBLISHABLE",
    }
