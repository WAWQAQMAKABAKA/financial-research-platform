"""M126: synthetic terminology recall and fail-closed model boundary."""
from datetime import datetime
from hashlib import sha256
from zoneinfo import ZoneInfo

import pytest

from app.evidence.pdf_canonicalizer import CanonicalDocument, CanonicalPage
from app.modules.financial_report_analyst import (
    canonical_retrieval, retrieval_analyst, terminology_candidates,
)
from test_canonical_retrieval import synthetic_document

WHEN = datetime(2026, 10, 25, 12, tzinfo=ZoneInfo("Asia/Shanghai"))


def _doc(*bodies):
    source, old = synthetic_document()
    pages = []
    parts = []
    offset = 0
    for n, body in enumerate(bodies, 1):
        marker = f"=== PAGE {n} ===\n"
        pages.append(CanonicalPage(n, offset, offset+len(marker),
                                   offset+len(marker)+len(body)))
        parts.append(marker+body+"\n")
        offset += len(marker)+len(body)+1
    text = "".join(parts)
    # SourceDocument is a frozen Pydantic model, not a dataclass.
    # Reconstruct and validate the synthetic source identity with the new hash.
    source = type(source).model_validate({
        **source.model_dump(mode="python"),
        "canonical_sha256": sha256(text.encode()).hexdigest(),
    })
    document = CanonicalDocument(
        document_id=source.document_id, source_sha256=source.source_sha256,
        canonical_sha256=source.canonical_sha256,
        canonical_text=text, pages=tuple(pages),
    )
    return source, document


def test_registry_has_25_provenance_bearing_symmetric_distinctions():
    rows = terminology_candidates._records()
    assert len(rows) == 25
    assert len({x["id"] for x in rows}) == 25
    assert all(x["origin"] for x in rows)


def test_natural_rd_question_keeps_three_distinct_candidates():
    probe = terminology_candidates.candidate_probe("研发花了多少钱？")
    assert probe["status"] == "ACTIVATED"
    assert {x["concept_id"] for x in probe["candidates"]} == {
        "rd_investment", "expensed_rd_investment", "rd_expense",
    }
    assert probe["distinct_concepts_warning"] == "NON_EQUIVALENT_CANDIDATES"


def test_cash_flow_term_expansion_does_not_decide_statement_scope():
    probe = terminology_candidates.candidate_probe("经营现金流在哪里？")
    assert {x["concept_id"] for x in probe["candidates"]} == {
        "operating_cashflow_net",
    }
    assert probe["review"] == "RETRIEVAL_CUES_ONLY_NOT_FINANCIAL_EQUIVALENCE"


def test_licensing_potential_does_not_equal_recognized_revenue():
    a = terminology_candidates.candidate_probe("授权协议总额是多少？")
    b = terminology_candidates.candidate_probe("海外许可收入是多少？")
    assert [c["concept_id"] for c in a["candidates"]] == ["licensing_potential_deal_value"]
    assert [c["concept_id"] for c in b["candidates"]] == ["licensing_recognized_revenue"]
    assert "licensing_recognized_revenue" in a["candidates"][0]["not_equivalent_to"]


def test_expanded_terms_rank_canonical_source_span():
    source, doc = _doc(
        "管理层讨论研发投入和费用化研发投入，仍需核对。\n",
        "利润表列示研发费用，不等同于研发投入。\n",
        "企业还披露了其他与研究无关的内容。\n",
    )
    out = canonical_retrieval.retrieve_from_canonical(
        source, doc, "研发花了多少钱？", as_of=WHEN,
    )
    assert out["terminology_probe"]["status"] == "ACTIVATED"
    assert out["evidence"][0]["source_page"] == 1
    assert out["research_publication"] == "BLOCKED"
    assert out["financial_semantic_review"] == "NOT_PERFORMED"
    for hit in out["evidence"]:
        assert doc.canonical_text[hit["canonical_start"]:hit["canonical_end"]] == hit["source_excerpt"]


def test_exact_query_preserves_m124_retrieval_identity():
    source, doc = _doc("公司披露研发投入与营业收入。\n", "第二页研发费用。\n")
    query = "研发投入是多少？"
    out = canonical_retrieval.retrieve_from_canonical(source, doc, query, as_of=WHEN)
    assert out["terminology_probe"]["status"] == "NO_TRIGGER"
    identity = "|".join((canonical_retrieval.RETRIEVER_VERSION,
        source.document_id, source.canonical_sha256, WHEN.date().isoformat(), query))
    assert out["retrieval_id"] == sha256(identity.encode()).hexdigest()


def test_preferred_surface_does_not_trigger_shorter_embedded_alias():
    probe = terminology_candidates.candidate_probe("创新药销售收入和研发投入有哪些披露？")
    assert probe["status"] == "NO_TRIGGER"


def test_alias_expanded_packet_cannot_enter_analyst_model_path():
    source, doc = _doc("公司研发投入增加。\n", "公司另披露研发费用。\n")
    question = "研发花了多少钱？"
    packet = canonical_retrieval.retrieve_from_canonical(source, doc, question, as_of=WHEN)
    with pytest.raises(ValueError, match="RETRIEVAL_PACKET_NOT_QUALIFIED"):
        retrieval_analyst._validated_evidence(source, packet, question, WHEN)


def test_no_trigger_retains_old_retrieval_status():
    source, doc = synthetic_document()
    packet = canonical_retrieval.retrieve_from_canonical(
        source, doc, "创新药销售收入和研发有什么进展？", as_of=WHEN,
    )
    assert packet["terminology_probe"]["status"] == "NO_TRIGGER"
    assert packet["retrieval_review"] == "CANDIDATES_NOT_RELEVANCE_QUALIFIED"


# M127 tests are synthetic, offline and concern ranking—not financial answers.
def test_quantitative_cue_is_bounded_and_requires_real_amount_token():
    probe = terminology_candidates.candidate_probe("海外许可收入是多少？")
    assert canonical_retrieval._amount_proximity_bonus(
        "海外许可收入是多少？", "对外许可合作报告期确认收入25.00亿元。", probe,
    ) == 15.0
    assert canonical_retrieval._amount_proximity_bonus(
        "海外许可收入是多少？", "对外许可业务的会计政策说明。", probe,
    ) == 0.0
    assert canonical_retrieval._amount_proximity_bonus(
        "海外许可收入在哪里？", "对外许可合作报告期确认收入25.00亿元。", probe,
    ) == 0.0
    # Section numbers alone must never count as financial values.
    assert canonical_retrieval._amount_proximity_bonus(
        "海外许可收入是多少？", "第2节：对外许可业务的政策说明。", probe,
    ) == 0.0


def test_amount_near_expanded_concept_beats_generic_policy_excerpt():
    source, doc = _doc(
        "本年度许可收入政策遵循履约义务的规定。公司提供一般性会计政策说明。\n",
        "管理层说明：对外许可合作业务报告期确认收入25.00亿元。\n",
        "海外合作风险尚需评估。\n",
    )
    out = canonical_retrieval.retrieve_from_canonical(
        source, doc, "海外许可收入是多少？", as_of=WHEN,
    )
    assert out["terminology_probe"]["status"] == "ACTIVATED"
    assert out["ranking_version"] == canonical_retrieval.RANKING_VERSION
    assert out["evidence"][0]["source_page"] == 2
    assert out["research_publication"] == "BLOCKED"
    assert out["financial_semantic_review"] == "NOT_PERFORMED"


def test_expanded_retrieval_prioritizes_page_diversity_without_discarding_spans():
    repeat = "公司对外许可合作业务确认收入25.00亿元。\n"
    source, doc = _doc(
        repeat * 38,
        "另一页披露对外许可合作收入26.00亿元。\n",
        "第三页披露对外许可合作收入27.00亿元。\n",
    )
    out = canonical_retrieval.retrieve_from_canonical(
        source, doc, "海外许可收入是多少？", as_of=WHEN,
    )
    assert {hit["source_page"] for hit in out["evidence"][:3]} == {1, 2, 3}
    for hit in out["evidence"]:
        assert doc.canonical_text[hit["canonical_start"]:hit["canonical_end"]] == hit["source_excerpt"]
    assert out["research_publication"] == "BLOCKED"


def test_m127_identity_versioned_for_expansion_but_not_legacy_query():
    source, doc = _doc(
        "对外许可合作业务确认收入25.00亿元。\n",
        "第二页披露对外许可合作收入26.00亿元。\n",
    )
    question = "海外许可收入是多少？"
    out = canonical_retrieval.retrieve_from_canonical(source, doc, question, as_of=WHEN)
    assert out["ranking_version"] == canonical_retrieval.RANKING_VERSION
    identity = "|".join((canonical_retrieval.RETRIEVER_VERSION,
        source.document_id, source.canonical_sha256, WHEN.date().isoformat(), question,
        terminology_candidates.VERSION, terminology_candidates.REGISTRY_SHA256,
        canonical_retrieval.RANKING_VERSION))
    assert out["retrieval_id"] == sha256(identity.encode()).hexdigest()
    legacy = canonical_retrieval.retrieve_from_canonical(
        source, doc, "对外许可合作收入", as_of=WHEN,
    )
    assert legacy["terminology_probe"]["status"] == "NO_TRIGGER"
    assert legacy["ranking_version"] == "frp-legacy-lexical-v1"
    old_identity = "|".join((canonical_retrieval.RETRIEVER_VERSION,
        source.document_id, source.canonical_sha256, WHEN.date().isoformat(),
        "对外许可合作收入"))
    assert legacy["retrieval_id"] == sha256(old_identity.encode()).hexdigest()


def test_multiple_cashflow_pages_survive_diversification():
    source, doc = _doc(
        "合并现金流量表\n经营活动产生的现金流量净额 123.45元\n",
        "母公司现金流量表\n经营活动产生的现金流量净额 67.89元\n",
    )
    out = canonical_retrieval.retrieve_from_canonical(
        source, doc, "经营现金流在哪里？", as_of=WHEN,
    )
    assert out["terminology_probe"]["status"] == "ACTIVATED"
    assert {hit["source_page"] for hit in out["evidence"]} == {1, 2}
    assert out["research_publication"] == "BLOCKED"
