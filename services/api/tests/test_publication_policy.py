"""M1 facts-only publication policy: every approval is re-verified."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.evidence.corpus_manifest import load_corpus_manifest
from app.modules.financial_report_analyst import publication_policy as pp

AS_OF = datetime(2026, 11, 2, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
EVIDENCE_ID = "df11966ce33c857538ae55fad9306bfe1c7d21c29290bbceefebee61ef5fa32d"


def document():
    return load_corpus_manifest().require_report_key("600760-2026H1")


def observation(**overrides):
    values = {
        "claim_id": "SRC1",
        "evidence_id": EVIDENCE_ID,
        "statement_type_candidate": "consolidated_income_statement",
        "statement_title": "合并利润表",
        "row_label": "其中：营业收入",
        "column_header": "2026 年半年度",
        "value_verbatim": "6,191,107,217.36",
        "statement_context": "2026 年1—6 月\n             单位：元币种：人民币",
        "page_number": 46,
        "source_text_span_status": "NOT_PROVEN_FROM_TABLE_GEOMETRY",
        "review_scope": "LITERAL_CELL_LOCATION_ONLY",
        "document_id": "600760-2026H1-cninfo-1225517994",
        "source_sha256": "d53ee98c091fdcbb8df3ebcc3f8d9bef87f61b374615dc3165dadb594f637d99",
        "canonical_sha256": "620d3a30f73423527dd662e21ebf3367b546dfa6795c6fcf618f35ebf0008aa5",
        "source_url": "https://static.cninfo.com.cn/finalpage/2026-08-28/1225517994.PDF",
    }
    values.update(overrides)
    return values


def claim(**overrides):
    values = {"claim_id": "SRC1", "kind": "OBSERVED_FACT", "evidence_ids": [EVIDENCE_ID]}
    values.update(overrides)
    return values


def review(**overrides):
    values = {
        "claim_id": "SRC1", "verdict": "ADMIT",
        "reviewer_id": pp.ALLOWED_REVIEWER, "rationale": pp.ALLOWED_RATIONALE,
    }
    values.update(overrides)
    return values


def draft(*, observations=None, claims=None, reviews=None, status="SOURCE_DRAFT_READY", **overrides):
    values = {
        "status": status,
        "observations": observations if observations is not None else [observation()],
        "claims": claims if claims is not None else [claim()],
        "reviews": reviews if reviews is not None else [review()],
        "document_id": "600760-2026H1-cninfo-1225517994",
        "source_sha256": "d53ee98c091fdcbb8df3ebcc3f8d9bef87f61b374615dc3165dadb594f637d99",
        "canonical_sha256": "620d3a30f73423527dd662e21ebf3367b546dfa6795c6fcf618f35ebf0008aa5",
        "source_url": "https://static.cninfo.com.cn/finalpage/2026-08-28/1225517994.PDF",
    }
    values.update(overrides)
    return values


def decide(data, *, as_of=AS_OF, verify_evidence=None):
    return pp.decide_publication(
        data, document(),
        expected_statement_kind="consolidated_income_statement",
        expected_row_label="其中：营业收入",
        as_of=as_of,
        verify_evidence=verify_evidence,
    )


def test_valid_observed_fact_is_published_facts_only():
    result = decide(draft())

    assert result["status"] == "PUBLICATION_APPROVED"
    assert result["may_publish"] is True
    assert result["research_publication"] == pp.FACTS_ONLY
    assert result["published_claim_ids"] == ["SRC1"]
    assert result["publication_label"] == "仅展示已核对的披露事实 · 不含财务趋势判断"
    assert result["financial_semantic_review"] == "NOT_PERFORMED"


def test_withheld_capabilities_never_include_comparisons_as_published():
    kinds = {item["kind"] for item in decide(draft())["withheld_capabilities"]}

    assert {"PERIOD_COMPARISON", "CROSS_ENTITY_COMPARISON",
            "ANALYST_INFERENCE", "FORWARD_VIEW"} <= kinds


@pytest.mark.parametrize("changed,reason", [
    ({"verdict": "REJECT"}, "REVIEW_NOT_ADMIT"),
    ({"verdict": "UNCERTAIN"}, "REVIEW_NOT_ADMIT"),
    ({"reviewer_id": "some-other-reviewer"}, "REVIEWER_NOT_ALLOWLISTED"),
    ({"rationale": "LOOKS_FINE"}, "REVIEW_RATIONALE_NOT_LITERAL_SCOPE"),
])
def test_review_conditions_are_reverified(changed, reason):
    result = decide(draft(reviews=[review(**changed)]))

    assert result["may_publish"] is False
    assert result["research_publication"] == pp.BLOCKED
    assert result["reason"] == reason
    assert result["published_claim_ids"] == []


def test_missing_review_withholds_even_though_label_is_untouched():
    result = decide(draft(reviews=[]))

    assert result["may_publish"] is False
    assert result["published_claim_ids"] == []


def test_draft_level_identity_must_match_manifest():
    result = decide(draft(source_sha256="0" * 64))

    assert result["may_publish"] is False
    assert result["reason"] == "SOURCE_IDENTITY_MISMATCH"


@pytest.mark.parametrize("changed,reason", [
    ({"document_id": "OTHER-DOCUMENT"}, "SOURCE_IDENTITY_MISMATCH"),
    ({"source_sha256": "0" * 64}, "SOURCE_IDENTITY_MISMATCH"),
    ({"canonical_sha256": "0" * 64}, "SOURCE_IDENTITY_MISMATCH"),
    ({"source_url": "https://example.test/other.pdf"}, "SOURCE_IDENTITY_MISMATCH"),
    ({"row_label": "其中：营业成本"}, "SELECTION_MISMATCH"),
    ({"column_header": "2025 年半年度"}, "SELECTION_MISMATCH"),
    ({"statement_context": "2025 年1—6 月 单位：元 币种：人民币"}, "PERIOD_LINKAGE_MISMATCH"),
    ({"statement_context": "2026 年1—6 月 单位：元"}, "UNIT_CONTEXT_MISMATCH"),
    ({"value_verbatim": "约 61.9 亿元"}, "VALUE_FORMAT_INVALID"),
    ({"page_number": 0}, "PAGE_INVALID"),
    ({"source_text_span_status": "PROVEN"}, "SPAN_SCOPE_MISMATCH"),
    ({"review_scope": "ACCOUNTING_REVIEWED"}, "SPAN_SCOPE_MISMATCH"),
])
def test_source_and_linkage_conditions_are_reverified(changed, reason):
    result = decide(draft(observations=[observation(**changed)]))

    assert result["may_publish"] is False
    assert result["reason"] == reason


def test_evidence_span_callback_can_still_withhold():
    result = decide(draft(), verify_evidence=lambda evidence_id: False)

    assert result["may_publish"] is False
    assert result["reason"] == "EVIDENCE_SPAN_NOT_VERIFIED"


def test_pit_before_available_day_withholds():
    result = decide(draft(), as_of=datetime(
        2026, 8, 28, 23, 59, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert result["may_publish"] is False
    assert result["reason"] == "PIT_UNAVAILABLE"


def test_duplicate_evidence_cannot_be_counted_twice():
    data = draft(
        observations=[observation(), observation(claim_id="SRC2")],
        claims=[claim(), claim(claim_id="SRC2")],
        reviews=[review(), review(claim_id="SRC2")],
    )
    result = decide(data)

    assert result["may_publish"] is False
    assert result["reason"] == "DUPLICATE_EVIDENCE_ID"


def test_comparative_claim_is_withheld_while_fact_stays_published():
    data = draft(
        observations=[observation(), observation(claim_id="CMP1")],
        claims=[
            claim(),
            {"claim_id": "CMP1", "kind": "ANALYST_INFERENCE", "evidence_ids": []},
        ],
        reviews=[review()],
    )
    result = decide(data)

    assert result["published_claim_ids"] == ["SRC1"]
    assert result["withheld"] == [{
        "claim_id": "CMP1", "kind": "ANALYST_INFERENCE",
        "status": "NOT_PUBLISHED", "reason": "NON_FACT_CLAIM_NOT_PUBLISHABLE",
    }]


def test_only_comparative_claims_means_no_publication():
    data = draft(
        observations=[observation(claim_id="CMP1")],
        claims=[{"claim_id": "CMP1", "kind": "PERIOD_COMPARISON", "evidence_ids": []}],
        reviews=[],
    )
    result = decide(data)

    assert result["may_publish"] is False
    assert result["reason"] == "NO_PUBLISHABLE_FACT"
    assert result["research_publication"] == pp.BLOCKED


def test_unready_draft_is_never_approved():
    result = decide(draft(status="WITHHELD"))

    assert result["may_publish"] is False
    assert result["reason"] == "SOURCE_DRAFT_NOT_READY"
