"""M125 offline, fabricated evidence only; no external calls or benchmark GT."""
from hashlib import sha256

import pytest

from app.modules.financial_report_analyst.answer_coverage import (
    BASIS, REVIEW, VERSION, _facets, build_coverage_probe,
)

E1, E2 = "1" * 64, "2" * 64
RID, DID = "a" * 64, "b" * 64


def sample():
    evidence = [
        {"evidence_id": E1, "source_excerpt": "创新药销售收入为12.5单位。研发投入为2.3单位。"},
        {"evidence_id": E2, "source_excerpt": "临床试验进入新阶段，产品销售增长。"},
    ]
    claims = [{
        "claim_id": "C1", "evidence_id": E1,
        "text": "创新药销售收入为12.5单位。",
        "source_quote": "创新药销售收入为12.5单位。",
        "review": {"verdict": "UNCERTAIN"},
    }]
    return evidence, claims


def probe(q="创新药销售收入和研发投入有哪些披露？"):
    evidence, claims = sample()
    return build_coverage_probe(
        question=q, retrieval_id=RID, draft_id=DID,
        evidence=evidence, claims=claims,
    )


def test_question_facets_are_generic_conjunction_split_not_predefined_topics():
    assert _facets("创新药销售收入和研发投入有哪些披露？") == (
        ["创新药销售收入", "研发投入"], "SURFACE_CONJUNCTION_SPLIT",
    )
    assert _facets("供货量以及存货周转有哪些披露？")[0] == ["供货量", "存货周转"]


def test_draft_and_source_overlap_are_distinct_and_never_called_coverage():
    out = probe()
    assert out["coverage_version"] == VERSION
    assert out["basis"] == BASIS
    assert out["review"] == REVIEW
    a, b = out["facets"]
    assert a == {"question_phrase": "创新药销售收入",
                 "literal_status": "PHRASE_VISIBLE_IN_SOURCE_AND_DRAFT",
                 "source_evidence_ids": [E1], "draft_claim_ids": ["C1"]}
    assert b == {"question_phrase": "研发投入",
                 "literal_status": "PHRASE_VISIBLE_IN_SOURCE_ONLY",
                 "source_evidence_ids": [E1], "draft_claim_ids": []}
    assert "not proof" in out["limitations"]


def test_facet_absence_is_never_claimed_factual_absence():
    out = probe("创新药销售收入和研发进展有哪些披露？")
    assert out["facets"][1]["literal_status"] == "PHRASE_NOT_LOCATED_LEXICALLY"
    assert out["review"] == "COVERAGE_NOT_SEMANTICALLY_QUALIFIED"


def test_evidence_quote_not_in_source_fails_closed():
    evidence, claims = sample()
    claims[0]["source_quote"] = "根本不存在的引文"
    with pytest.raises(ValueError, match="COVERAGE_CLAIM_BINDING_INVALID"):
        build_coverage_probe(question="销售和研发", retrieval_id=RID,
                             draft_id=DID, evidence=evidence, claims=claims)


def test_missing_evidence_id_or_uncertain_review_fails_closed():
    evidence, claims = sample()
    claims[0]["evidence_id"] = "f" * 64
    with pytest.raises(ValueError, match="COVERAGE_CLAIM_BINDING_INVALID"):
        build_coverage_probe(question="销售和研发", retrieval_id=RID,
                             draft_id=DID, evidence=evidence, claims=claims)
    evidence, claims = sample()
    claims[0]["review"]["verdict"] = "ADMIT"
    with pytest.raises(ValueError, match="COVERAGE_CLAIM_BINDING_INVALID"):
        build_coverage_probe(question="销售和研发", retrieval_id=RID,
                             draft_id=DID, evidence=evidence, claims=claims)


def test_extra_long_question_is_rejected_without_leak():
    evidence, claims = sample()
    with pytest.raises(ValueError, match="COVERAGE_INPUT_INVALID"):
        build_coverage_probe(question="甲" * 241, retrieval_id=RID,
                             draft_id=DID, evidence=evidence, claims=claims)


def test_many_facets_fallback_and_stable_identity():
    out = probe("经营和销售与研发以及财务、管理有哪些披露？")
    assert out["segmentation"] == "FALLBACK_SINGLE_QUESTION_PHRASE"
    assert len(out["facets"]) == 1
    assert out["coverage_id"] == probe("经营和销售与研发以及财务、管理有哪些披露？")["coverage_id"]
    assert len(out["coverage_id"]) == 64


def test_unknown_paraphrase_cannot_be_certified_as_covered():
    out = probe("收入变化")
    assert out["facets"][0]["literal_status"] == "PHRASE_NOT_LOCATED_LEXICALLY"
    assert out["facets"][0]["draft_claim_ids"] == []


def test_integrated_model_draft_adds_probe_without_extra_model_calls():
    # Reuse M124 synthetic mock provider; verify a full preview response.
    from test_retrieval_analyst import packet, model_response, mock_client, draft

    source, retrieved = packet()
    calls = []
    with mock_client(model_response(retrieved), calls) as client:
        result = draft(source, retrieved, client)
    assert len(calls) == 1
    assert result["status"] == "UNPUBLISHED_ANALYST_PREVIEW"
    assert result["coverage_probe"]["review"] == REVIEW
    assert result["coverage_probe"]["coverage_version"] == VERSION
    assert result["research_publication"] == "BLOCKED"
    assert result["financial_semantic_review"] == "NOT_PERFORMED"
    assert result["claim_level_review"] == "UNCERTAIN_SEMANTICS_NOT_REVIEWED"
    assert result["coverage_probe"]["coverage_id"] == sha256("|".join((
        VERSION, result["retrieval_id"], result["draft_id"], result["question"],
    )).encode()).hexdigest()
