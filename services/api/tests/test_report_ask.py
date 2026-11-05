"""M2a question-driven report against the real authorized 600760 disclosure."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import shutil

import pytest

from app.evidence.corpus_manifest import CorpusHashMismatch
from app.modules.financial_report_analyst import report_builder as rb

AS_OF = datetime(2026, 11, 2, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
REPORT_KEY = "600760-2026H1"
QUESTION = "600760 中航沈飞 2026 年半年度合并利润表中营业收入是多少？"
PDF = Path(__file__).resolve().parents[3] / "data/raw/600760/2026H1/source.pdf"


def require_pdf() -> Path:
    if not PDF.is_file():
        pytest.skip("authorized 600760 PDF not provisioned locally")
    return PDF


@pytest.fixture(scope="module")
def report():
    return rb.build_report_from_question(REPORT_KEY, require_pdf(), QUESTION, as_of=AS_OF)


def test_question_report_publishes_only_the_verified_fact(report):
    assert report["status"] == "REPORT_READY"
    assert report["report_type"] == "FACTS_ONLY_QUESTION_REPORT"
    assert len(report["facts"]) == 1

    fact = report["facts"][0]
    assert fact["statement_title"] == "合并利润表"
    assert fact["row_label"] == "其中：营业收入"
    assert fact["value_verbatim"] == "6,191,107,217.36"
    assert fact["page_number"] == 46
    assert fact["citation"]["page_number"] == 46
    assert report["publication"]["research_publication"] == "FACTS_ONLY"
    assert report["reviews"][0]["verdict"] == "ADMIT"


def test_report_shows_retrieval_and_selection_trace(report):
    assert report["retrieval"]["status"] == "RETRIEVAL_CANDIDATES_READY"
    assert len(report["retrieval"]["hits"]) >= 1
    assert report["retrieval"]["hits"][0]["page_number"] >= 1
    assert report["selection"]["statement_kind"] == "consolidated_income_statement"
    assert report["selection"]["rows"] == ["其中：营业收入"]
    assert report["selection"]["trace"]["selection_basis"] == "QUESTION_STATEMENT_TITLE"


def test_net_profit_question_selects_its_own_row():
    result = rb.build_report_from_question(
        REPORT_KEY, require_pdf(),
        "中航沈飞2026年半年度合并利润表中净利润是多少？", as_of=AS_OF,
    )

    assert result["status"] == "REPORT_READY"
    fact = result["facts"][0]
    assert fact["row_label"].startswith("五、净利润")
    assert fact["value_verbatim"] == "468,144,459.10"
    assert fact["page_number"] == 47


@pytest.fixture(scope="module")
def blank_parent_report():
    return rb.build_report_from_question(
        REPORT_KEY, require_pdf(),
        "中航沈飞2026年半年度母公司利润表中营业收入是多少？", as_of=AS_OF,
    )


def test_blank_parent_cell_is_not_published_as_zero(blank_parent_report):
    result = blank_parent_report

    assert result["status"] == "REPORT_WITHHELD"
    assert result["reason"] == "SOURCE_CELL_BLANK_NOT_ZERO"
    assert result["facts"] == []
    assert result["publication"]["research_publication"] == "BLOCKED"


def test_withheld_report_does_not_expose_source_excerpts(blank_parent_report):
    assert all(hit["excerpt"] == "" for hit in blank_parent_report["retrieval"]["hits"])


def test_prior_period_question_is_out_of_scope():
    result = rb.build_report_from_question(
        REPORT_KEY, require_pdf(),
        "2025年半年度合并利润表中营业收入是多少？", as_of=AS_OF,
    )

    assert result["status"] == "REPORT_WITHHELD"
    assert result["reason"] == "OUT_OF_PERIOD_SCOPE"
    assert result["facts"] == []


def test_unrelated_question_publishes_nothing():
    result = rb.build_report_from_question(
        REPORT_KEY, require_pdf(),
        "公司的研发投入和员工人数是多少？", as_of=AS_OF,
    )

    assert result["status"] == "REPORT_WITHHELD"
    assert result["reason"] in {"NO_STATEMENT_SCOPE", "NO_ROW_MATCH"}
    assert result["facts"] == []


def test_report_id_depends_on_the_question(report):
    other = rb.build_report_from_question(
        REPORT_KEY, require_pdf(),
        "中航沈飞2026年半年度合并利润表中营业成本是多少？", as_of=AS_OF,
    )

    assert len(report["report_id"]) == 64
    assert other["report_id"] != report["report_id"]


def test_altered_document_fails_closed(tmp_path):
    source = require_pdf()
    altered = tmp_path / "altered.pdf"
    shutil.copyfile(source, altered)
    body = bytearray(altered.read_bytes())
    body[2048] ^= 0xFF
    altered.write_bytes(body)

    with pytest.raises(CorpusHashMismatch):
        rb.build_report_from_question(REPORT_KEY, altered, QUESTION, as_of=AS_OF)


def test_empty_question_is_invalid():
    result = rb.build_report_from_question(REPORT_KEY, require_pdf(), "  ", as_of=AS_OF)

    assert result["status"] == "REPORT_WITHHELD"
    assert result["reason"] == "QUESTION_INVALID"

def test_comparison_question_is_blocked_before_selection():
    result = rb.build_report_from_question(
        REPORT_KEY, require_pdf(),
        "中航沈飞2026年半年度合并利润表中营业收入比去年增长多少？", as_of=AS_OF,
    )

    assert result["status"] == "REPORT_WITHHELD"
    assert result["reason"] == "COMPARISON_NOT_PUBLISHABLE"
    assert result["facts"] == []
    assert result["intent"]["value"] == "COMPARISON"
    assert "retrieval" not in result


def test_forecast_question_is_blocked_before_selection():
    result = rb.build_report_from_question(
        REPORT_KEY, require_pdf(),
        "中航沈飞2026全年合并利润表中营业收入预计多少？", as_of=AS_OF,
    )

    assert result["status"] == "REPORT_WITHHELD"
    assert result["reason"] == "FORWARD_VIEW_NOT_PUBLISHABLE"
    assert result["facts"] == []


def test_ambiguous_question_is_blocked_before_selection():
    result = rb.build_report_from_question(
        REPORT_KEY, require_pdf(), "中航沈飞2026年半年度经营情况如何？", as_of=AS_OF,
    )

    assert result["status"] == "REPORT_WITHHELD"
    assert result["reason"] == "QUESTION_INTENT_AMBIGUOUS"
    assert result["facts"] == []

def test_attributable_net_profit_question_publishes_only_that_row():
    result = rb.build_report_from_question(
        REPORT_KEY, require_pdf(),
        "中航沈飞2026年半年度合并利润表中归属于母公司股东的净利润是多少？",
        as_of=AS_OF,
    )

    assert result["status"] == "REPORT_READY"
    assert len(result["facts"]) == 1
    assert result["facts"][0]["row_label"].startswith("1.归属于母公司股东的净利润")
    assert result["facts"][0]["value_verbatim"] == "473,065,863.24"
    assert result["selection"]["trace"]["specificity_dropped"] == ["净利润"]


def test_revenue_synonym_publishes_the_literal_row():
    result = rb.build_report_from_question(
        REPORT_KEY, require_pdf(),
        "中航沈飞2026年半年度合并利润表的营收是多少？", as_of=AS_OF,
    )

    assert result["status"] == "REPORT_READY"
    assert result["facts"][0]["row_label"] == "其中：营业收入"
    assert result["selection"]["trace"]["synonyms_applied"] == [
        {"alias": "营收", "canonical": "营业收入"}
    ]


def test_profit_synonym_is_not_mapped_and_publishes_nothing():
    result = rb.build_report_from_question(
        REPORT_KEY, require_pdf(),
        "中航沈飞2026年半年度合并利润表的净利是多少？", as_of=AS_OF,
    )

    assert result["status"] == "REPORT_WITHHELD"
    assert result["reason"] == "NO_ROW_MATCH"
    assert result["facts"] == []



def test_forced_selection_resolves_attributable_net_profit():
    result = rb.build_report_from_question(
        REPORT_KEY, require_pdf(), "公司上半年的净利是多少？", as_of=AS_OF,
        forced_selection={
            "statement_kind": "consolidated_income_statement",
            "row_label": "1.归属于母公司股东的净利润（净亏损以“-”号填列）",
            "core": "归属于母公司股东的净利润",
        },
    )

    assert result["status"] == "REPORT_READY"
    assert len(result["facts"]) == 1
    assert result["facts"][0]["value_verbatim"] == "473,065,863.24"
    assert result["selection"]["trace"]["selection_basis"] == "USER_RESOLVED_METRIC"


def test_signed_negative_row_publishes():
    result = rb.build_report_from_question(
        REPORT_KEY, require_pdf(), "公司上半年的净利是多少？", as_of=AS_OF,
        forced_selection={
            "statement_kind": "consolidated_income_statement",
            "row_label": "2.少数股东损益（净亏损以“-”号填列）",
            "core": "少数股东损益",
        },
    )

    assert result["status"] == "REPORT_READY"
    assert result["facts"][0]["value_verbatim"] == "-4,921,404.14"
    assert result["publication"]["research_publication"] == "FACTS_ONLY"


def test_multi_requirement_report_covers_two_facts():
    result = rb.build_multi_report(
        REPORT_KEY, require_pdf(),
        "600760 中航沈飞 2026 年半年度合并利润表中营业收入和净利润分别是多少？",
        as_of=AS_OF,
    )

    assert result["status"] == "REPORT_READY"
    assert result["report_type"] == "FACTS_ONLY_MULTI_REQUIREMENT_REPORT"
    assert len(result["facts"]) == 2
    assert result["coverage"]["complete"] is True
    assert result["coverage"]["satisfied"] == 2
    values = {fact["value_verbatim"] for fact in result["facts"]}
    assert values == {"6,191,107,217.36", "468,144,459.10"}


def test_multi_requirement_report_reports_a_missing_fact():
    result = rb.build_multi_report(
        REPORT_KEY, require_pdf(),
        "600760 中航沈飞 2026 年半年度合并利润表中营业收入和研发投入分别是多少？",
        as_of=AS_OF,
    )

    assert result["status"] == "REPORT_READY"
    assert len(result["facts"]) == 1
    assert result["coverage"]["complete"] is False
    assert result["coverage"]["satisfied"] == 1
    missing = [item for item in result["coverage"]["requirements"]
               if item["status"] != "VERIFIED"]
    assert missing and missing[0]["status"] == "NO_ROW_MATCH"


def test_multi_requirement_comparison_is_blocked():
    result = rb.build_multi_report(
        REPORT_KEY, require_pdf(),
        "600760 中航沈飞 2026 年半年度合并利润表中营业收入和净利润相比如何？",
        as_of=AS_OF,
    )

    assert result["status"] == "REPORT_WITHHELD"
    assert result["reason"] == "COMPARISON_NOT_PUBLISHABLE"
    assert result["facts"] == []


def test_multi_report_offers_a_bounded_repair_for_the_missing_facet():
    result = rb.build_multi_report(
        REPORT_KEY, require_pdf(),
        "600760 中航沈飞 2026 年半年度合并利润表中营业收入和研发投入分别是多少？",
        as_of=AS_OF, repair_secret="secret",
    )

    repair = result["coverage"].get("repair")
    assert repair is not None
    assert repair["facet"] == "研发投入"
    assert "研发费用" in {option["core"] for option in repair["options"]}
    assert repair["clarification_id"]


def test_llm_facets_drive_the_multi_plan(monkeypatch):
    monkeypatch.setattr(
        rb.interpretation, "propose_facets",
        lambda question, api_key: {
            "status": "FACETS_READY", "facets": ["营业收入", "营业成本"],
            "rationale": "两个指标。", "model": "deepseek-flash",
        },
    )
    result = rb.build_multi_report(
        REPORT_KEY, require_pdf(),
        "600760 中航沈飞 2026 年半年度合并利润表中营业收入和营业成本分别是多少？",
        as_of=AS_OF, api_key="key",
    )

    assert result["coverage"]["plan_source"] == "LLM_PROPOSAL_VALIDATED"
    assert result["coverage"]["satisfied"] == 2
    assert "5,535,215,299.31" in {fact["value_verbatim"] for fact in result["facts"]}


def test_llm_planning_can_split_a_question_the_conjunction_split_misses(monkeypatch):
    monkeypatch.setattr(
        rb.interpretation, "propose_facets",
        lambda question, api_key: {
            "status": "FACETS_READY", "facets": ["营业收入", "净利润"],
            "rationale": "两个问句。", "model": "deepseek-flash",
        },
    )
    result = rb.build_multi_report(
        REPORT_KEY, require_pdf(),
        "600760 中航沈飞 2026 年半年度合并利润表中营业收入是多少？净利润又是多少？",
        as_of=AS_OF, api_key="key",
    )

    assert result is not None
    assert result["coverage"]["plan_source"] == "LLM_PROPOSAL_VALIDATED"
    assert result["coverage"]["complete"] is True
    assert {"6,191,107,217.36", "468,144,459.10"} == {
        fact["value_verbatim"] for fact in result["facts"]
    }


def test_four_metric_question_publishes_four_facts():
    result = rb.build_multi_report(
        REPORT_KEY, require_pdf(),
        "600760 中航沈飞 2026 年半年度合并利润表中营业收入、净利润、营业成本、研发费用分别是多少？",
        as_of=AS_OF,
    )

    assert result["status"] == "REPORT_READY"
    assert result["coverage"]["total"] == 4
    assert result["coverage"]["complete"] is True
    assert len(result["facts"]) == 4


def test_seven_metric_question_is_rejected_with_the_count():
    result = rb.build_multi_report(
        REPORT_KEY, require_pdf(),
        "600760 中航沈飞 2026 年半年度合并利润表中营业收入、净利润、营业成本、研发费用、"
        "税金及附加、销售费用、管理费用分别是多少？",
        as_of=AS_OF,
    )

    assert result["status"] == "REPORT_WITHHELD"
    assert result["reason"] == "TOO_MANY_REQUIREMENTS"
    assert result["plan"] == {"status": "TOO_MANY_REQUIREMENTS", "detected": 7, "max": 6}
    assert result["facts"] == []


def test_management_question_returns_a_withheld_preview():
    result = rb.build_management_report(
        REPORT_KEY, require_pdf(),
        "600760 中航沈飞 2026 年半年度营业收入变动原因是什么？",
        as_of=AS_OF,
    )

    assert result["status"] == "REPORT_WITHHELD"
    assert result["reason"] == "MANAGEMENT_EXPLANATION_REQUIRES_SEMANTIC_REVIEW"
    assert result["facts"] == []
    preview = result["management_preview"]
    assert preview["status"] == "PREVIEW_ONLY_NOT_PUBLISHED"
    assert preview["semantic_review"] == "NOT_PERFORMED"
    assert preview["pointers"]
    assert any("主要是受" in pointer["excerpt"] for pointer in preview["pointers"])


def test_management_question_without_section_evidence_is_withheld():
    result = rb.build_management_report(
        REPORT_KEY, require_pdf(),
        "600760 中航沈飞 2026 年半年度员工人数为什么变化？",
        as_of=AS_OF,
    )

    assert result["status"] == "REPORT_WITHHELD"
    assert result["reason"] == "NO_MANAGEMENT_EVIDENCE"
    assert result["facts"] == []
    assert "management_preview" not in result


def test_management_preview_stays_inside_the_discussion_section():
    result = rb.build_management_report(
        REPORT_KEY, require_pdf(),
        "600760 中航沈飞 2026 年半年度净利润为什么下降？",
        as_of=AS_OF,
    )

    pointers = result["management_preview"]["pointers"]
    assert pointers
    assert all(8 <= pointer["page_number"] <= 17 for pointer in pointers)
    assert any(
        "利润" in pointer["excerpt"]
        and ("下滑" in pointer["excerpt"] or "下降" in pointer["excerpt"])
        for pointer in pointers
    )


def test_mixed_question_publishes_the_fact_and_previews_the_explanation():
    result = rb.build_mixed_report(
        REPORT_KEY, require_pdf(),
        "600760 中航沈飞 2026 年半年度营业收入是多少？管理层为什么说利润下降？",
        as_of=AS_OF,
    )

    assert result["status"] == "REPORT_READY"
    assert result["report_type"] == "FACTS_WITH_MANAGEMENT_PREVIEW_REPORT"
    assert {fact["value_verbatim"] for fact in result["facts"]} == {"6,191,107,217.36"}
    preview = result["management_preview"]
    assert preview["status"] == "PREVIEW_ONLY_NOT_PUBLISHED"
    assert preview["semantic_review"] == "NOT_PERFORMED"
    assert preview["pointers"]
    assert result["management_publication"] == {
        "may_publish": False,
        "reason": "MANAGEMENT_EXPLANATION_REQUIRES_SEMANTIC_REVIEW",
        "semantic_review": "NOT_PERFORMED",
    }


def test_mixed_question_without_a_publishable_fact_returns_none():
    assert rb.build_mixed_report(
        REPORT_KEY, require_pdf(),
        "600760 中航沈飞 2026 年半年度员工人数是多少？管理层为什么说利润下降？",
        as_of=AS_OF,
    ) is None
