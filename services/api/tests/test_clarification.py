"""M3 clarification: option generation and signed token."""
from datetime import datetime
from pathlib import Path

import pytest

from app.evidence.corpus_manifest import load_corpus_manifest
from app.modules.financial_report_analyst import clarification as cl

COLUMN = "2026 年半年度"
HEADER = ["项目", "附注", COLUMN, "2025 年半年度"]


def table(rows):
    return [
        [{"row_index": r, "column_index": c, "text": t} for c, t in enumerate(row)]
        for r, row in enumerate(rows)
    ]


def section(kind, page, rows, relationship="SECTION_ROOT_CANDIDATE"):
    cells = table(rows)
    trec = {
        "table_index": 0, "bbox_pt": [0.0, 0.0, 100.0, 100.0],
        "row_count": len(cells), "column_count": len(cells[0]),
        "rows": cells, "section_kind": kind, "relationship": relationship,
    }
    return trec, {
        "page_number": page, "table_index": 0, "section_kind": kind,
        "relationship": relationship, "bbox_pt": trec["bbox_pt"],
        "shape": [trec["row_count"], trec["column_count"]],
    }


def index():
    records = [
        section("consolidated_income_statement", 1, [
            HEADER,
            ["一、营业总收入", "61", "6,191,107,217.36", "14,628,337,068.60"],
            ["其中：营业收入", "61", "6,191,107,217.36", "14,628,337,068.60"],
            ["五、净利润（净亏损以“-”号填列）", "", "468,144,459.10", "1,131,941,918.95"],
            ["1.归属于母公司股东的净利润（净亏损以“-”号填列）", "", "473,065,863.24", "1,136,413,283.86"],
        ]),
    ]
    return {
        "index_schema": "frp-cn-document-index-candidate-v1",
        "page_count": 1,
        "sections": [rec for _, rec in records],
        "pages": [{"page_number": 1, "tables": [trec for trec, _ in records]}],
    }


def document():
    return load_corpus_manifest().require_report_key("600760-2026H1")


def test_closed_options_are_source_rows_with_stable_ids():
    closed = cl.closed_options(index(), document(), "consolidated_income_statement")

    labels = {option["core"] for option in closed}
    assert "净利润" in labels
    assert "归属于母公司股东的净利润" in labels
    assert len({option["option_id"] for option in closed}) == len(closed)
    for option in closed:
        assert len(option["option_id"]) == 64
        assert option["statement_title"] == "合并利润表"


def test_near_match_options_find_net_profit_ambiguity():
    closed = cl.closed_options(index(), document(), "consolidated_income_statement")
    options = cl.near_match_options(closed, "公司上半年的净利是多少？")

    cores = {option["core"] for option in options}
    assert "净利润" in cores
    assert "归属于母公司股东的净利润" in cores


def test_sign_and_verify_roundtrip():
    token = cl.sign_clarification(
        question="公司上半年的净利是多少？", document=document(),
        report_key="600760-2026H1", statement_kind="consolidated_income_statement",
        option_ids=["a" * 64, "b" * 64], secret="secret",
    )
    payload = cl.verify_clarification(token, "secret")

    assert payload["question_sha256"]
    assert payload["option_ids"] == ["a" * 64, "b" * 64]
    assert payload["statement_kind"] == "consolidated_income_statement"


def test_tampered_token_is_rejected():
    token = cl.sign_clarification(
        question="q", document=document(), report_key="600760-2026H1",
        statement_kind="consolidated_income_statement",
        option_ids=["a" * 64, "b" * 64], secret="secret",
    )
    with pytest.raises(ValueError, match="CLARIFICATION_TOKEN_INVALID"):
        cl.verify_clarification(token[:-1] + ("0" if token[-1] != "0" else "1"), "secret")


def test_wrong_secret_is_rejected():
    token = cl.sign_clarification(
        question="q", document=document(), report_key="600760-2026H1",
        statement_kind="consolidated_income_statement",
        option_ids=["a" * 64, "b" * 64], secret="secret",
    )
    with pytest.raises(ValueError, match="CLARIFICATION_TOKEN_INVALID"):
        cl.verify_clarification(token, "other-secret")


def test_build_clarification_prefers_validated_llm_proposal():
    idx = index()
    result = cl.build_clarification(
        report_key="600760-2026H1", document=document(), index=idx,
        question="公司上半年的净利是多少？",
        statement_kind="consolidated_income_statement", secret="secret",
        proposed_option_ids=[
            cl.option_id(document(), "consolidated_income_statement",
                         "五、净利润（净亏损以“-”号填列）"),
            cl.option_id(document(), "consolidated_income_statement",
                         "1.归属于母公司股东的净利润（净亏损以“-”号填列）"),
        ],
        interpretation_rationale="净利可指净利润或归母净利润。",
    )

    assert result["status"] == "CLARIFICATION_REQUIRED"
    assert result["option_basis"] == "LLM_PROPOSAL_VALIDATED"
    assert len(result["options"]) == 2
    assert result["interpretation"]["status"] == "UNVERIFIED_PROPOSAL"
    assert result["research_publication"] == "BLOCKED"


def test_build_clarification_falls_back_to_near_match_without_llm():
    result = cl.build_clarification(
        report_key="600760-2026H1", document=document(), index=index(),
        question="公司上半年的净利是多少？",
        statement_kind="consolidated_income_statement", secret="secret",
        proposed_option_ids=None,
    )

    assert result["status"] == "CLARIFICATION_REQUIRED"
    assert result["option_basis"] == "NEAR_MATCH"
    assert result["interpretation"]["status"] == "NOT_PERFORMED"


def test_build_clarification_returns_none_when_unresolvable():
    result = cl.build_clarification(
        report_key="600760-2026H1", document=document(), index=index(),
        question="研发投入是多少？",
        statement_kind="consolidated_income_statement", secret="secret",
    )

    assert result is None
