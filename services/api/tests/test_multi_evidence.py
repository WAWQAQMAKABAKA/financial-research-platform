"""Strictly offline M1.8A binding regression; synthetic numbers, no provider calls."""
from hashlib import sha256
import json

import httpx
import pytest

from app.modules.financial_report_analyst import deepseek_draft, multi_evidence as multi, revenue_scope


def synthetic_draft():
    src = revenue_scope.SOURCE
    report_id = sha256((src.document_id + "|" + src.canonical_sha256
                         + "|revenue-scope-preview-v1").encode()).hexdigest()
    observations, claims, reviews = [], [], []
    for i, (selection, value) in enumerate(zip(
        revenue_scope.SELECTIONS, ("12,345.67", "89,012.34")
    )):
        cid, eid = f"REV{i+1}", f"synthetic-evidence-{i+1}"
        observations.append({
            "claim_id": cid, "evidence_id": eid,
            "statement_type_candidate": selection["section_kind"],
            "row_label": selection["row_label"],
            "column_header": selection["column_header"],
            "statement_title": revenue_scope._STATEMENT_LABELS[selection["section_kind"]],
            "source_text_span_status": "NOT_PROVEN_FROM_TABLE_GEOMETRY",
            "review_scope": "LITERAL_CELL_LOCATION_ONLY",
            "page_number": i + 10,
            "value_verbatim": value,
        })
        claims.append({"claim_id": cid, "kind": "OBSERVED_FACT", "evidence_ids": [eid]})
        reviews.append({"claim_id": cid, "verdict": "ADMIT",
                        "rationale": "LITERAL_CELL_AND_HEADING_SOURCE_CHECK_ONLY"})
    return {
        "status": "SOURCE_DRAFT_READY", "report_id": report_id,
        "document_id": src.document_id, "source_url": src.source_url,
        "question": revenue_scope.QUESTION,
        "source_sha256": src.source_sha256, "canonical_sha256": src.canonical_sha256,
        "financial_semantic_review": "NOT_PERFORMED", "research_publication": "BLOCKED",
        "observations": observations, "claims": claims, "reviews": reviews,
    }


class MockProvider:
    def __init__(self, *, change=None):
        self.calls = []
        self.change = change

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        items = kwargs["json"]["messages"][1]["content"]
        packet = json.loads(items.split("Copy source evidence into JSON claims: ", 1)[1])
        props = ("evidence_id", "statement_kind", "statement_title",
                 "row_label", "column_header", "value")
        claims = [{"claim_id": f"DS{i+1}", **{k: cell[k] for k in props}}
                  for i, cell in enumerate(packet["evidence"])]
        if self.change:
            self.change(claims)
        result = {
            "model": "deepseek-flash", "choices": [{"finish_reason": "stop",
                "message": {"content": json.dumps({"claims": claims})}}],
            "usage": {"prompt_tokens": 200, "completion_tokens": 60,
                      "total_tokens": 260},
        }
        return httpx.Response(200, json=result,
                              request=httpx.Request("POST", url))


def test_two_source_draft_claim_citations_and_no_semantics():
    provider = MockProvider()
    result = multi.draft_two_source_brief(synthetic_draft(), api_key="synthetic", client=provider)
    assert result["status"] == "LLM_MULTI_EVIDENCE_PACKET_MATCHED"
    assert [x["claim_id"] for x in result["claims"]] == ["DS1", "DS2"]
    assert [x["source_page"] for x in result["claims"]] == [10, 11]
    assert len({x["evidence_id"] for x in result["claims"]}) == 2
    assert {x["statement_kind_candidate"] for x in result["claims"]} == {
        "consolidated_income_statement", "parent_income_statement"}
    assert [x["value_verbatim"] for x in result["claims"]] == ["12,345.67", "89,012.34"]
    assert all(r["verdict"] == "LITERAL_LOCATION_MATCH_ONLY" for r in result["reviews"])
    assert result["research_publication"] == "BLOCKED"
    assert result["financial_semantic_review"] == "NOT_PERFORMED"
    assert result["usage"]["total_tokens"] == 260
    assert len(provider.calls) == 1
    assert "Bearer synthetic" == provider.calls[0][1]["headers"]["Authorization"]
    assert "not a comparison" in result["brief"]


@pytest.mark.parametrize("change", [
    lambda c: c[1].update(value="99,999.99"),
    lambda c: c[1].update(evidence_id=c[0]["evidence_id"]),
    lambda c: c.reverse(),
    lambda c: c.append(dict(c[0])),
])
def test_any_model_source_mismatch_withholds_all(change):
    provider = MockProvider(change=change)
    result = multi.draft_two_source_brief(synthetic_draft(), api_key="synthetic", client=provider)
    assert result["status"] == "WITHHELD"
    assert result["claims"] == result["reviews"] == []
    assert result["research_publication"] == "BLOCKED"
    assert len(provider.calls) == 1


@pytest.mark.parametrize("corrupt", [
    lambda d: d["observations"][0].update(evidence_id="tampered"),
    lambda d: d["reviews"][1].update(verdict="UNCERTAIN"),
    lambda d: d.update(canonical_sha256="0" * 64),
    lambda d: d["observations"][1].update(statement_type_candidate="consolidated_income_statement"),
    lambda d: d["observations"][1].update(value_verbatim="not a number"),
])
def test_unqualified_packet_never_triggers_a_paid_request(corrupt):
    draft = synthetic_draft()
    corrupt(draft)
    provider = MockProvider()
    result = multi.draft_two_source_brief(draft, api_key="synthetic", client=provider)
    assert result["status"] == "WITHHELD" and not result["claims"]
    assert not provider.calls


def test_model_provider_failure_withholds():
    provider = MockProvider()
    assert multi.draft_two_source_brief(synthetic_draft(), api_key="", client=provider)["status"] == "WITHHELD"
    assert not provider.calls
