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
