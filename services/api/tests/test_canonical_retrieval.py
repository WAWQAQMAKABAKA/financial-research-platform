"""M122 offline retrieval checks; synthetic text and mocked API, no network/model."""
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.evidence.contracts import SourceDocument
from app.evidence.pdf_canonicalizer import CanonicalPage, CanonicalDocument
from app.modules.financial_report_analyst import canonical_retrieval as retrieval
import app.main as main

WHEN = datetime(2026, 10, 25, 12, tzinfo=ZoneInfo("Asia/Shanghai"))
TOKEN = "synthetic-m122-" + "a" * 48
URL = "/api/v1/research/local-evidence-search"
QUESTION = "创新药销售收入和研发有什么进展？"


def synthetic_document():
    content = (
        "公司2026年上半年合并利润表\n营业收入 123.45 元\n",
        "管理层讨论创新药销售收入和创新药研发进展。\n创新药商业化持续推进。\n",
        "其他信息：合并现金流量表和日常经营情况。\n",
    )
    pieces = []
    pages = []
    offset = 0
    for number, body in enumerate(content, start=1):
        marker = f"=== PAGE {number} ===\n"
        pages.append(CanonicalPage(number, offset, offset + len(marker),
                                   offset + len(marker) + len(body)))
        pieces.append(marker + body + "\n")
        offset += len(marker) + len(body) + 1
    text = "".join(pieces)
    source = SourceDocument(
        document_id="synthetic-M122-report", ticker="TEST", report_period="2026H1",
        source_url="https://example.invalid/disclosure.pdf", published_on=date(2026, 8, 20),
        source_sha256="a" * 64,
        canonical_sha256=sha256(text.encode()).hexdigest(),
    )
    canonical = CanonicalDocument(
        document_id=source.document_id,
        source_sha256=source.source_sha256,
        canonical_sha256=source.canonical_sha256,
        canonical_text=text, pages=tuple(pages),
    )
    return source, canonical


def retrieve(question=QUESTION):
    source, document = synthetic_document()
    return retrieval.retrieve_from_canonical(source, document, question, as_of=WHEN)


def test_unfamiliar_query_retrieves_matching_page_without_topic_selector():
    packet = retrieve()
    assert packet["status"] == "RETRIEVAL_CANDIDATES_READY"
    assert packet["evidence"][0]["source_page"] == 2
    assert "创新药研发" in packet["evidence"][0]["source_excerpt"]
    assert packet["research_publication"] == "BLOCKED"
    assert packet["financial_semantic_review"] == "NOT_PERFORMED"
    assert packet["retrieval_review"] == "CANDIDATES_NOT_RELEVANCE_QUALIFIED"


def test_revenue_query_retrieves_separate_page():
    packet = retrieve("合并利润表营业收入是多少？")
    assert packet["evidence"][0]["source_page"] == 1


def test_each_hit_is_exact_canonical_slice_and_has_stable_identity():
    source, doc = synthetic_document()
    a = retrieve()
    b = retrieve()
    assert a["retrieval_id"] == b["retrieval_id"]
    assert a["evidence"] == b["evidence"]
    for hit in a["evidence"]:
        assert doc.canonical_text[hit["canonical_start"]:hit["canonical_end"]] == hit["source_excerpt"]
        assert len(hit["evidence_id"]) == 64
        assert source.document_id == a["document_id"]


def test_unmatched_query_is_withheld_not_unsupported_factual_claim():
    packet = retrieve("xyzirrelevant")
    assert packet["status"] == "WITHHELD"
    assert packet["reason"] == "NO_LEXICAL_MATCH_NOT_EVIDENCE_OF_ABSENCE"
    assert packet["evidence"] == []


@pytest.mark.parametrize("question", ["", " ", "x" * 241, "😃" * 201])
def test_invalid_question_rejected(question):
    with pytest.raises(ValueError, match="RETRIEVAL_QUESTION_INVALID"):
        retrieve(question)


def test_prepublication_pit_rejected():
    source, doc = synthetic_document()
    with pytest.raises(ValueError, match="PIT_UNAVAILABLE"):
        retrieval.retrieve_from_canonical(
            source, doc, QUESTION,
            as_of=datetime(2026, 8, 20, 21, tzinfo=ZoneInfo("Asia/Shanghai")),
        )


@pytest.mark.parametrize("field,replacement", [
    ("document_id", "other-report"),
    ("source_sha256", "f" * 64),
    ("canonical_sha256", "f" * 64),
    ("canonical_text", "forged"),
])
def test_mutated_source_binding_fails_closed(field, replacement):
    from dataclasses import replace
    source, doc = synthetic_document()
    forged = replace(doc, **{field: replacement})
    with pytest.raises(ValueError, match="CANONICAL_SOURCE_BINDING_INVALID"):
        retrieval.retrieve_from_canonical(source, forged, QUESTION, as_of=WHEN)


def test_bad_page_offsets_rejected():
    from dataclasses import replace
    source, doc = synthetic_document()
    forged = replace(doc, pages=(CanonicalPage(1, 0, 50, 100000),))
    with pytest.raises(ValueError, match="CANONICAL_PAGE_OFFSETS_INVALID"):
        retrieval.retrieve_from_canonical(source, forged, QUESTION, as_of=WHEN)


def enabled(monkeypatch):
    monkeypatch.setenv("FRP_LOCAL_RETRIEVAL_UI", "1")
    monkeypatch.setenv("FRP_LOCAL_LLM_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv("FRP_LOCAL_REVENUE_PDF", "/offline-synthetic.pdf")


def request(client, payload=None, token=TOKEN):
    return client.post(URL, json=payload or {
        "report_key": "600276-2026H1", "question": QUESTION,
    }, headers={"x-frp-local-token": token})


def test_backend_route_disabled_by_default(monkeypatch):
    monkeypatch.delenv("FRP_LOCAL_RETRIEVAL_UI", raising=False)
    assert request(TestClient(main.app)).status_code == 404


def test_backend_route_requires_token(monkeypatch):
    enabled(monkeypatch)
    assert request(TestClient(main.app), token="bad").status_code == 404


@pytest.mark.parametrize("payload", [
    {"report_key": "600760-2026H1", "question": QUESTION},
    {"report_key": "600276-2026H1", "question": QUESTION, "pdf_path": "/tmp/forged.pdf"},
    {"report_key": "600276-2026H1", "question": ""},
])
def test_backend_route_rejects_untrusted_inputs(monkeypatch, payload):
    enabled(monkeypatch)
    assert request(TestClient(main.app), payload).status_code == 422


def test_backend_route_owns_document_and_does_not_call_model(monkeypatch):
    enabled(monkeypatch)
    def fake_retrieve(actual_source, path, question, *, as_of):
        assert actual_source.document_id == main_source.document_id
        assert path == Path("/offline-synthetic.pdf")
        assert question == QUESTION
        assert as_of.tzinfo is not None
        return {"status":"WITHHELD", "research_publication":"BLOCKED", "financial_semantic_review":"NOT_PERFORMED", "evidence": []}
    from app.modules.financial_report_analyst import revenue_scope
    main_source = revenue_scope.SOURCE
    monkeypatch.setattr(retrieval, "retrieve_report_evidence", fake_retrieve)
    assert request(TestClient(main.app)).json()["research_publication"] == "BLOCKED"


def test_backend_route_failure_does_not_leak_source(monkeypatch):
    enabled(monkeypatch)
    def fail(*args, **kwargs):
        raise ValueError("PRIVATE_SOURCE_PATH_OR_TEXT")
    monkeypatch.setattr(retrieval, "retrieve_report_evidence", fail)
    response = request(TestClient(main.app))
    assert response.status_code == 503
    assert response.json() == {"detail": "SOURCE_UNAVAILABLE"}
    assert "PRIVATE_SOURCE_PATH_OR_TEXT" not in response.text
