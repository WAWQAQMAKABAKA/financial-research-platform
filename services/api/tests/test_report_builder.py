"""M1 facts-only report builder against the real authorized 600760 disclosure."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import shutil

import pytest

from app.evidence.corpus_manifest import (
    CorpusDocumentMissing, CorpusHashMismatch, load_corpus_manifest,
)
from app.modules.financial_report_analyst import report_builder as rb
from app.modules.financial_report_analyst import source_workspace as ws

AS_OF = datetime(2026, 11, 2, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
REPORT_KEY = "600760-2026H1"
PDF = Path(__file__).resolve().parents[3] / "data/raw/600760/2026H1/source.pdf"


def require_pdf() -> Path:
    if not PDF.is_file():
        pytest.skip("authorized 600760 PDF not provisioned locally")
    return PDF


@pytest.fixture(scope="module")
def report():
    # One full-document extraction shared by the read-only assertions below.
    return rb.build_report(REPORT_KEY, require_pdf(), as_of=AS_OF)


def test_only_the_manifest_document_is_report_capable():
    assert rb.supported_report_keys() == (REPORT_KEY,)
    assert ws.REPORTS[REPORT_KEY].authorization == ws.AUTHORIZATION_MANIFEST
    assert ws.REPORTS["600276-2026H1"].authorization == ws.AUTHORIZATION_LEGACY


def test_report_ready_with_verified_fact(report):
    assert report["status"] == "REPORT_READY"
    assert report["report_type"] == "FACTS_ONLY_DISCLOSURE_REPORT"
    assert report["report_storage"] == "NOT_PERSISTED"
    assert report["issuer"] == {"name": "中航沈飞", "ticker": "600760", "report_period": "2026H1"}
    assert len(report["facts"]) == 1

    fact = report["facts"][0]
    assert fact["kind"] == "OBSERVED_FACT"
    assert fact["row_label"] == "其中：营业收入"
    assert fact["column_header"].replace(" ", "") == "2026年半年度"
    assert fact["statement_title"] == "合并利润表"
    assert fact["value_verbatim"] == "6,191,107,217.36"
    assert fact["page_number"] == 46
    assert fact["citation"]["page_number"] == 46
    assert fact["citation"]["document_id"] == "600760-2026H1-cninfo-1225517994"
    assert len(fact["citation"]["cell_bbox_pt"]) == 4


def test_report_identity_comes_from_the_manifest(report):
    document = load_corpus_manifest().require_report_key(REPORT_KEY)

    assert report["source"]["document_id"] == document.document_id
    assert report["source"]["source_sha256"] == document.source_sha256
    assert report["source"]["canonical_sha256"] == document.canonical_sha256
    assert report["source"]["source_url"] == document.source_url
    assert report["source"]["published_on"] == document.published_on.isoformat()
    assert report["source"]["page_count"] == document.page_count


def test_publication_is_facts_only_and_semantics_stay_unreviewed(report):
    publication = report["publication"]

    assert publication["may_publish"] is True
    assert publication["research_publication"] == "FACTS_ONLY"
    assert publication["publication_label"] == "仅展示已核对的披露事实 · 不含财务趋势判断"
    assert publication["financial_semantic_review"] == "NOT_PERFORMED"
    assert publication["published_claim_ids"] == ["SRC1"]
    assert publication["withheld"] == []


def test_no_inferential_or_comparative_content_is_published(report):
    assert all(fact["kind"] == "OBSERVED_FACT" for fact in report["facts"])
    kinds = {item["kind"] for item in report["publication"]["withheld_capabilities"]}
    assert {"PERIOD_COMPARISON", "CROSS_ENTITY_COMPARISON", "ANALYST_INFERENCE"} <= kinds


def test_claim_level_review_accompanies_the_fact(report):
    assert len(report["reviews"]) == 1
    assert report["reviews"][0]["claim_id"] == report["facts"][0]["claim_id"]
    assert report["reviews"][0]["verdict"] == "ADMIT"
    assert report["reviews"][0]["reviewer_id"] == "native-pdf-cell-literal-reviewer-v1"
    assert report["reviews"][0]["rationale"] == "LITERAL_CELL_AND_HEADING_SOURCE_CHECK_ONLY"


def test_report_id_is_stable_across_calls(report):
    assert len(report["report_id"]) == 64
    second = rb.build_report(REPORT_KEY, require_pdf(), as_of=AS_OF)
    assert second["report_id"] == report["report_id"]


def test_altered_document_fails_closed(tmp_path):
    source = require_pdf()
    altered = tmp_path / "altered.pdf"
    shutil.copyfile(source, altered)
    body = bytearray(altered.read_bytes())
    body[1024] ^= 0xFF
    altered.write_bytes(body)

    with pytest.raises(CorpusHashMismatch):
        rb.build_report(REPORT_KEY, altered, as_of=AS_OF)


def test_absent_document_fails_closed(tmp_path):
    require_pdf()
    with pytest.raises(CorpusDocumentMissing):
        rb.build_report(REPORT_KEY, tmp_path / "absent.pdf", as_of=AS_OF)


def test_unauthorized_legacy_report_is_refused():
    require_pdf()
    with pytest.raises(ws.UnknownReportError, match="REPORT_NOT_AUTHORIZED_IN_CORPUS"):
        rb.build_report("600276-2026H1", require_pdf(), as_of=AS_OF)


def test_pit_before_available_day_yields_no_facts():
    report = rb.build_report(
        REPORT_KEY, require_pdf(),
        as_of=datetime(2026, 8, 28, 23, 59, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    assert report["status"] == "REPORT_WITHHELD"
    assert report["reason"] == "PIT_UNAVAILABLE"
    assert report["facts"] == []


def test_policy_refusal_carries_no_facts(monkeypatch):
    require_pdf()
    monkeypatch.setattr(ws, "build_source_workspace", lambda *a, **k: {
        "status": "SOURCE_DRAFT_READY", "observations": [], "claims": [], "reviews": [],
    })
    monkeypatch.setattr(rb.publication_policy, "decide_publication", lambda *a, **k: {
        "status": "PUBLICATION_WITHHELD", "may_publish": False,
        "research_publication": "BLOCKED", "reason": "REVIEW_NOT_ADMIT",
        "published_claim_ids": [], "withheld": [], "withheld_capabilities": [],
        "financial_semantic_review": "NOT_PERFORMED",
    })

    report = rb.build_report(REPORT_KEY, require_pdf(), as_of=AS_OF)

    assert report["status"] == "REPORT_WITHHELD"
    assert report["facts"] == []
    assert report["publication"]["may_publish"] is False


def test_unresolved_draft_yields_no_facts(monkeypatch):
    require_pdf()
    monkeypatch.setattr(ws, "build_source_workspace", lambda *a, **k: {
        "status": "WITHHELD", "reason": "LITERAL_REVIEW_NOT_PASSED",
        "observations": [], "claims": [], "reviews": [],
    })

    report = rb.build_report(REPORT_KEY, require_pdf(), as_of=AS_OF)

    assert report["status"] == "REPORT_WITHHELD"
    assert report["reason"] == "LITERAL_REVIEW_NOT_PASSED"
    assert report["facts"] == []
