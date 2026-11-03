"""M4 split and coverage planning on a synthetic index."""
from app.modules.financial_report_analyst import evidence_plan as ep

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
    consolidated, parent = [
        section("consolidated_income_statement", 1, [
            HEADER,
            ["一、营业总收入", "61", "6,191,107,217.36", "14,628,337,068.60"],
            ["其中：营业收入", "61", "6,191,107,217.36", "14,628,337,068.60"],
            ["五、净利润（净亏损以“-”号填列）", "", "468,144,459.10", "1,131,941,918.95"],
        ]),
        section("parent_income_statement", 2, [
            HEADER,
            ["一、营业收入", "", "1,000.00", "900.00"],
            ["五、净利润（净亏损以“-”号填列）", "", "800.00", "700.00"],
        ]),
    ]
    return {
        "index_schema": "frp-cn-document-index-candidate-v1",
        "page_count": 2,
        "sections": [consolidated[1], parent[1]],
        "pages": [
            {"page_number": 1, "tables": [consolidated[0]]},
            {"page_number": 2, "tables": [parent[0]]},
        ],
    }


def plan(question, hits=()):
    return ep.plan_requirements(
        index(), question=question, report_period="2026H1",
        column_header=COLUMN, retrieval_hits=list(hits),
    )


def test_splits_two_and_three_facets():
    assert ep.split_facets("合并利润表中营业收入和净利润分别是多少？") == [
        "合并利润表中营业收入", "净利润"
    ]
    assert len(ep.split_facets("营业收入、净利润和营业成本分别是多少？")) == 3
    assert ep.split_facets("营业收入是多少？") == ["营业收入是多少？"]


def test_plan_satisfies_two_requirements():
    result = plan("合并利润表中营业收入和净利润分别是多少？")

    assert result["status"] == "PLAN_READY"
    assert result["statement_kind"] == "consolidated_income_statement"
    assert [item["status"] for item in result["requirements"]] == [
        "SATISFIED", "SATISFIED"
    ]
    assert result["requirements"][0]["row"]["core"] == "营业收入"
    assert result["requirements"][1]["row"]["core"] == "净利润"


def test_plan_reports_a_missing_requirement():
    result = plan("合并利润表中营业收入和研发投入分别是多少？")

    assert result["status"] == "PLAN_READY"
    assert result["requirements"][0]["status"] == "SATISFIED"
    assert result["requirements"][1]["status"] == "NO_ROW_MATCH"


def test_titleless_multi_question_can_be_scope_ambiguous():
    result = plan("营业收入和净利润分别是多少？")

    assert result["status"] == "SCOPE_AMBIGUOUS"
    assert result["present"] == [
        "consolidated_income_statement", "parent_income_statement"
    ]


def test_single_fact_question_has_no_plan():
    assert plan("营业收入是多少？") is None
