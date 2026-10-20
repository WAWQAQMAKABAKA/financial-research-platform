from dataclasses import replace
from datetime import date, datetime
from hashlib import sha256
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.evidence import preview
from app.evidence.contracts import EvidenceSpan, SourceDocument
from app.evidence.pdf_canonicalizer import CanonicalDocument, CanonicalPage


def fixture():
    marker = "=== PAGE 1 ===\n"
    body = "Revenue row: 100\n"
    text = marker + body
    h = sha256(text.encode()).hexdigest()
    source = SourceDocument(
        document_id="SYNTHETIC", ticker="TEST", report_period="2026H1",
        source_url="https://example.org/report.pdf", published_on=date(2026, 8, 28),
        source_sha256="a" * 64, canonical_sha256=h,
    )
    canonical = CanonicalDocument(
        document_id="SYNTHETIC", source_sha256="a" * 64,
        canonical_sha256=h, canonical_text=text,
        pages=(CanonicalPage(page_number=1, marker_start=0,
            content_start=len(marker), content_end=len(text) - 1),),
    )
    span = EvidenceSpan(
        evidence_id="E1", document_id="SYNTHETIC", canonical_sha256=h,
        page_number=1, canonical_start=len(marker), canonical_end=len(text) - 1,
        excerpt="Revenue row: 100",
    )
    as_of = datetime(2026, 10, 20, tzinfo=ZoneInfo("Asia/Shanghai"))
    return source, canonical, span, as_of


def test_exact_span_is_accepted():
    preview.require_exact_span(*fixture())


def test_wrong_excerpt_is_rejected():
    source, canonical, span, as_of = fixture()
    with pytest.raises(ValueError, match="EXCERPT_MISMATCH"):
        preview.require_exact_span(source, canonical,
            span.model_copy(update={"excerpt": "Revenue row: 999"}), as_of)


def test_wrong_page_is_rejected():
    source, canonical, span, as_of = fixture()
    with pytest.raises(ValueError, match="PAGE_OUT_OF_RANGE"):
        preview.require_exact_span(source, canonical,
            span.model_copy(update={"page_number": 2}), as_of)


def test_page_marker_cannot_be_cited_as_body():
    source, canonical, span, as_of = fixture()
    with pytest.raises(ValueError, match="PAGE_BOUNDARY"):
        preview.require_exact_span(source, canonical,
            span.model_copy(update={"canonical_start": 0}), as_of)


def test_source_identity_mismatch_rejected():
    source, canonical, span, as_of = fixture()
    with pytest.raises(ValueError, match="IDENTITY_MISMATCH"):
        preview.require_exact_span(source,
            replace(canonical, source_sha256="c" * 64), span, as_of)


def test_pit_unavailable_rejected():
    source, canonical, span, _ = fixture()
    as_of = datetime(2026, 8, 28, 23, 59, tzinfo=ZoneInfo("Asia/Shanghai"))
    with pytest.raises(ValueError, match="PIT_UNAVAILABLE"):
        preview.require_exact_span(source, canonical, span, as_of)


def test_endpoint_disabled_by_default(monkeypatch):
    monkeypatch.delenv("FRP_LOCAL_EVIDENCE_PREVIEW", raising=False)
    response = TestClient(app).get(
        f"/api/v1/research/evidence-preview/{preview.DOCUMENT_ID}")
    assert response.status_code == 404


def test_missing_source_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("FRP_LOCAL_EVIDENCE_PREVIEW", "1")
    monkeypatch.setattr(preview, "PDF_PATH", tmp_path / "missing.pdf")
    response = TestClient(app).get(
        f"/api/v1/research/evidence-preview/{preview.DOCUMENT_ID}")
    assert response.status_code == 503
    assert response.json()["detail"] == "SOURCE_UNAVAILABLE"


def test_unlisted_document_rejected(monkeypatch):
    monkeypatch.setenv("FRP_LOCAL_EVIDENCE_PREVIEW", "1")
    response = TestClient(app).get("/api/v1/research/evidence-preview/UNKNOWN")
    assert response.status_code == 404
