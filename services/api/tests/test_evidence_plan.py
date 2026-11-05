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
            ["其中：营业成本", "61", "5,535,215,299.31", "12,835,954,116.83"],
            ["研发费用", "65", "59,650,843.12", "182,439,746.46"],
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


def test_proposed_facets_are_used_and_recorded():
    result = ep.plan_requirements(
        index(), question="合并利润表中营业收入和净利润分别是多少？",
        report_period="2026H1", column_header=COLUMN,
        proposed_facets=["营业收入", "净利润"],
    )

    assert result["facets_source"] == "LLM_PROPOSAL_VALIDATED"
    assert [item["facet"] for item in result["requirements"]] == ["营业收入", "净利润"]
    assert all(item["status"] == "SATISFIED" for item in result["requirements"])


def test_invalid_proposed_facets_fall_back_to_split():
    result = ep.plan_requirements(
        index(), question="合并利润表中营业收入和净利润分别是多少？",
        report_period="2026H1", column_header=COLUMN,
        proposed_facets=["营业收入"],
    )

    assert result["facets_source"] == "DETERMINISTIC_SPLIT"


def test_four_requirements_are_planned_within_the_dynamic_ceiling():
    result = plan("合并利润表中营业收入、净利润、营业成本和研发费用分别是多少？")

    assert result["status"] == "PLAN_READY"
    assert len(result["requirements"]) == 4
    assert all(item["status"] == "SATISFIED" for item in result["requirements"])


def test_more_than_six_requirements_are_rejected_with_the_count():
    result = plan(
        "合并利润表中营业收入、净利润、营业成本、研发费用、税金及附加、销售费用和管理费用分别是多少？"
    )

    assert result["status"] == "TOO_MANY_REQUIREMENTS"
    assert result["detected"] == 7
    assert result["max"] == 6
