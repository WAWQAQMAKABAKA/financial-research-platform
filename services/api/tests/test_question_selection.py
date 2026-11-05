"""M2a selection: question -> statement scope -> table rows (synthetic index)."""
import pytest

from app.modules.financial_report_analyst import question_selection as qs

COLUMN = "2026 年半年度"

HEADER = ["项目", "附注", COLUMN, "2025 年半年度"]


def table(rows: list[list[str]]) -> list[list[dict]]:
    return [
        [{"row_index": r, "column_index": c, "text": text}
         for c, text in enumerate(row)]
        for r, row in enumerate(rows)
    ]


def section(kind: str, page: int, rows: list[list[str]], relationship="SECTION_ROOT_CANDIDATE"):
    cells = table(rows)
    table_record = {
        "table_index": 0, "bbox_pt": [0.0, 0.0, 100.0, 100.0],
        "row_count": len(cells), "column_count": len(cells[0]),
        "rows": cells, "section_kind": kind, "relationship": relationship,
    }
    return table_record, {
        "page_number": page, "table_index": 0, "section_kind": kind,
        "relationship": relationship, "bbox_pt": table_record["bbox_pt"],
        "shape": [table_record["row_count"], table_record["column_count"]],
    }


def build_index(*sections) -> dict:
    pages = {}
    records = []
    for table_record, record in sections:
        pages.setdefault(record["page_number"], []).append(table_record)
        records.append(record)
    page_count = max(pages) if pages else 0
    return {
        "index_schema": "frp-cn-document-index-candidate-v1",
        "page_count": page_count,
        "sections": records,
        "pages": [
            {"page_number": number, "tables": pages.get(number, [])}
            for number in range(1, page_count + 1)
        ],
    }


def income_statement_index() -> dict:
    consolidated = section("consolidated_income_statement", 1, [
        HEADER,
        ["一、营业总收入", "61", "6,191,107,217.36", "14,628,337,068.60"],
        ["其中：营业收入", "61", "6,191,107,217.36", "14,628,337,068.60"],
        ["二、营业总成本", "", "5,535,215,299.31", "12,882,118,507.83"],
        ["其中：营业成本", "", "5,535,215,299.31", "12,882,118,507.83"],
        ["三、营业利润（亏损以“-”号填列）", "", "565,393,924.81", "1,746,218,560.77"],
        ["五、净利润（净亏损以“-”号填列）", "", "468,144,459.10", "1,504,332,090.00"],
        ["1.归属于母公司股东的净利润（净亏损以“-”号填列）", "", "473,065,863.24", "1,136,413,283.86"],
    ])
    parent = section("parent_income_statement", 2, [
        HEADER,
        ["一、营业收入", "", "", ""],
        ["减：营业成本", "", "", ""],
        ["投资收益（损失以“-”号填列）", "", "1,405,326.00", "2,000,000.00"],
    ])
    return build_index(consolidated, parent)


def select(question, *, index=None, hits=(), column=COLUMN, period="2026H1", forced=None):
    return qs.select_cells(
        index if index is not None else income_statement_index(),
        question=question, report_period=period, column_header=column,
        retrieval_hits=list(hits), forced_statement_kind=forced,
    )


def test_explicit_consolidated_title_selects_literal_row():
    out = select("中航沈飞2026年半年度合并利润表中营业收入是多少？")

    assert out["status"] == "SELECTION_READY"
    assert out["statement_kind"] == "consolidated_income_statement"
    assert [row["row_label"] for row in out["rows"]] == ["其中：营业收入"]
    assert out["trace"]["selection_basis"] == "QUESTION_STATEMENT_TITLE"


def test_explicit_parent_title_selects_parent_statement():
    out = select("2026年半年度母公司利润表中营业收入是多少？")

    assert out["status"] == "SELECTION_READY"
    assert out["statement_kind"] == "parent_income_statement"
    assert out["rows"][0]["row_label"] == "一、营业收入"


def test_two_statement_titles_are_ambiguous():
    out = select("合并利润表和母公司利润表的营业收入各是多少？")

    assert out["status"] == "SELECTION_WITHHELD"
    assert out["reason"] == "AMBIGUOUS_STATEMENT_SCOPE"


def test_titleless_question_uses_retrieval_rank_with_sufficient_margin():
    out = select("2026年上半年营业收入是多少？",
                 hits=[{"page_number": 2}, {"page_number": 1}])

    assert out["status"] == "SELECTION_READY"
    assert out["statement_kind"] == "parent_income_statement"
    assert out["trace"]["selection_basis"] == "RETRIEVAL_PAGE_PRIORITY"


def test_titleless_question_without_hits_is_ambiguous():
    out = select("营业收入是多少？")

    assert out["status"] == "SELECTION_WITHHELD"
    assert out["reason"] == "AMBIGUOUS_STATEMENT_SCOPE"
    assert out["trace"]["present_statement_kinds"] == [
        "consolidated_income_statement", "parent_income_statement"
    ]


def test_other_reporting_year_is_out_of_scope():
    out = select("2025年半年度合并利润表中营业收入是多少？")

    assert out["status"] == "SELECTION_WITHHELD"
    assert out["reason"] == "OUT_OF_PERIOD_SCOPE"


def test_unmatched_metric_is_withheld():
    out = select("2026年半年度合并利润表中研发投入是多少？")

    assert out["status"] == "SELECTION_WITHHELD"
    assert out["reason"] == "NO_ROW_MATCH"


def test_trailing_filing_annotation_is_ignored_for_matching():
    out = select("2026年半年度合并利润表中净利润是多少？")

    assert out["status"] == "SELECTION_READY"
    assert out["rows"][0]["row_label"] == "五、净利润（净亏损以“-”号填列）"
    assert out["rows"][0]["core"] == "净利润"


def test_unknown_column_is_withheld():
    out = select("2026年半年度合并利润表中营业收入是多少？", column="2024 年半年度")

    assert out["status"] == "SELECTION_WITHHELD"
    assert out["reason"] == "COLUMN_HEADER_UNAVAILABLE"


def test_too_many_matching_rows_are_withheld():
    # MAX_FACTS is 6, so seven matches are required to exceed it.
    rows = [HEADER] + [[f"其中：项目{i}", "", "1.00", "2.00"] for i in range(7)]
    index = build_index(section("consolidated_income_statement", 1, rows))

    out = select(
        "2026年半年度合并利润表中项目0项目1项目2项目3项目4项目5项目6是多少？",
        index=index,
    )

    assert out["status"] == "SELECTION_WITHHELD"
    assert out["reason"] == "TOO_MANY_ROW_MATCHES"


def test_row_core_strips_enumeration_and_annotations():
    assert qs.row_label_core("一、营业总收入") == "营业总收入"
    assert qs.row_label_core("其中：营业收入") == "营业收入"
    assert qs.row_label_core("减：营业成本") == "营业成本"
    assert qs.row_label_core("1.归属于母公司股东的净利润（净亏损以“-”号填列）") == "归属于母公司股东的净利润"
    assert qs.row_label_core("（一）基本每股收益(元/股)") == "基本每股收益"

def test_attributable_profit_does_not_publish_generic_net_profit():
    out = select("2026年半年度合并利润表中归属于母公司股东的净利润是多少？")

    assert out["status"] == "SELECTION_READY"
    assert [row["row_label"] for row in out["rows"]] == [
        "1.归属于母公司股东的净利润（净亏损以“-”号填列）"
    ]
    assert "净利润" in out["trace"]["specificity_dropped"]


def test_generic_net_profit_does_not_reach_attributable_row():
    out = select("2026年半年度合并利润表中净利润是多少？")

    assert out["status"] == "SELECTION_READY"
    assert [row["row_label"] for row in out["rows"]] == ["五、净利润（净亏损以“-”号填列）"]


def test_revenue_synonym_is_normalized_for_matching_only():
    out = select("2026年半年度合并利润表的营收是多少？")

    assert out["status"] == "SELECTION_READY"
    assert [row["row_label"] for row in out["rows"]] == ["其中：营业收入"]
    assert out["trace"]["synonyms_applied"] == [
        {"alias": "营收", "canonical": "营业收入"}
    ]


def test_profit_synonym_is_not_auto_mapped():
    out = select("2026年半年度合并利润表的净利是多少？")

    assert out["status"] == "SELECTION_WITHHELD"
    assert out["reason"] == "NO_ROW_MATCH"
    assert out["trace"]["synonyms_applied"] == []


def test_metric_unique_to_one_statement_selects_it():
    out = select("2026年半年度投资收益是多少？")

    assert out["status"] == "SELECTION_READY"
    assert out["statement_kind"] == "parent_income_statement"
    assert out["trace"]["selection_basis"] == "ROW_UNIQUE_STATEMENT"


def test_forced_statement_kind_skips_scope_inference():
    out = select("营业收入是多少？", forced="parent_income_statement")

    assert out["status"] == "SELECTION_READY"
    assert out["statement_kind"] == "parent_income_statement"
    assert out["trace"]["selection_basis"] == "USER_RESOLVED_STATEMENT_SCOPE"
