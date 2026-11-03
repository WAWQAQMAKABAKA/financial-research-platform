from datetime import date
from hashlib import sha256
from pathlib import Path
import json

import pytest

from app.evidence import corpus_manifest as cm
from app.evidence.corpus_manifest import (
    CorpusDocument, CorpusDocumentMissing, CorpusEntryMissing, CorpusHashMismatch,
    CorpusManifest, CorpusManifestInvalid, CorpusManifestMissing,
    CorpusPageCountMismatch, load_corpus_manifest,
)

VERIFIED_SOURCE_SHA = "d53ee98c091fdcbb8df3ebcc3f8d9bef87f61b374615dc3165dadb594f637d99"
VERIFIED_CANONICAL_SHA = "620d3a30f73423527dd662e21ebf3367b546dfa6795c6fcf618f35ebf0008aa5"


def document(**overrides) -> dict:
    entry = {
        "document_id": "SYNTH-2026H1", "ticker": "600000", "issuer_name": "合成测试",
        "report_period": "2026H1", "source_url": "https://example.org/r.pdf",
        "published_on": "2026-08-28", "source_sha256": "a" * 64,
        "canonical_sha256": "b" * 64, "page_count": 1,
        "pdf_path": "data/raw/600000/2026H1/source.pdf",
        "authorization_note": "synthetic", "acquisition": "make one",
    }
    entry.update(overrides)
    return entry


def manifest(*entries, **overrides) -> dict:
    payload = {
        "schema_version": "corpus.v1", "authorized_on": "2026-11-02",
        "authorization_note": "synthetic", "acquisition_note": "synthetic",
        "documents": list(entries) or [document()],
    }
    payload.update(overrides)
    return payload


def write_manifest(tmp_path: Path, payload) -> Path:
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def make_pdf(tmp_path: Path, pages: int = 1) -> Path:
    import pymupdf

    path = tmp_path / "source.pdf"
    pdf = pymupdf.open()
    for number in range(pages):
        page = pdf.new_page()
        page.insert_text((72, 72), f"Synthetic page {number + 1}")
    pdf.save(path)
    pdf.close()
    return path


# --- the tracked manifest ---------------------------------------------------

def test_tracked_manifest_declares_600760_first():
    loaded = load_corpus_manifest()

    assert isinstance(loaded, CorpusManifest)
    assert loaded.schema_version == cm.SCHEMA_VERSION
    assert loaded.document_ids[0] == "600760-2026H1-cninfo-1225517994"


def test_tracked_manifest_hash_identity_is_the_verified_one():
    entry = load_corpus_manifest().require("600760-2026H1-cninfo-1225517994")

    assert entry.ticker == "600760"
    assert entry.report_period == "2026H1"
    assert entry.issuer_name == "中航沈飞"
    assert entry.source_sha256 == VERIFIED_SOURCE_SHA
    assert entry.canonical_sha256 == VERIFIED_CANONICAL_SHA
    assert entry.page_count == 207
    assert entry.pdf_path == "data/raw/600760/2026H1/source.pdf"
    assert entry.authorization_note and entry.acquisition


def test_manifest_entry_converts_to_source_identity():
    source = load_corpus_manifest().require("600760-2026H1-cninfo-1225517994").to_source_document()

    assert source.published_on == date(2026, 8, 28)
    assert source.canonical_sha256 == VERIFIED_CANONICAL_SHA


def test_manifest_agrees_with_current_hardcoded_identity():
    from app.evidence import preview

    entry = load_corpus_manifest().require(preview.DOCUMENT_ID)
    assert entry.to_source_document() == preview.SOURCE


def test_manifest_default_path_is_tracked_location():
    assert cm.DEFAULT_MANIFEST_PATH == cm.REPO_ROOT / "data/manifests/corpus.v1.json"


# --- real document verification --------------------------------------------

def test_declared_pdf_matches_declared_source_hash():
    entry = load_corpus_manifest().require("600760-2026H1-cninfo-1225517994")
    if not entry.require_pdf().is_file():
        pytest.skip("authorized PDF not present locally")

    assert cm.sha256_file(entry.require_pdf()) == VERIFIED_SOURCE_SHA


def test_declared_pdf_reproduces_canonical_hash_and_page_count():
    entry = load_corpus_manifest().require("600760-2026H1-cninfo-1225517994")
    if not entry.require_pdf().is_file():
        pytest.skip("authorized PDF not present locally")

    assert cm.verify_document(entry, verify_canonical=True) == entry.require_pdf()


# --- fail-closed: manifest level -------------------------------------------

def test_missing_manifest_file_raises(tmp_path):
    with pytest.raises(CorpusManifestMissing):
        load_corpus_manifest(tmp_path / "absent.json")


def test_unparseable_manifest_raises(tmp_path):
    path = tmp_path / "corpus.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(CorpusManifestInvalid):
        load_corpus_manifest(path)


def test_unsupported_schema_version_raises(tmp_path):
    path = write_manifest(tmp_path, manifest(schema_version="corpus.v2"))
    with pytest.raises(CorpusManifestInvalid):
        load_corpus_manifest(path)


def test_empty_corpus_raises(tmp_path):
    path = write_manifest(tmp_path, manifest(documents=[]))
    with pytest.raises(CorpusManifestInvalid):
        load_corpus_manifest(path)


def test_duplicate_document_id_raises(tmp_path):
    path = write_manifest(tmp_path, manifest(document(), document()))
    with pytest.raises(CorpusManifestInvalid):
        load_corpus_manifest(path)


def test_malformed_hash_raises(tmp_path):
    path = write_manifest(tmp_path, manifest(document(source_sha256="not-a-hash")))
    with pytest.raises(CorpusManifestInvalid):
        load_corpus_manifest(path)


def test_absolute_pdf_path_raises(tmp_path):
    path = write_manifest(tmp_path, manifest(document(pdf_path="/etc/source.pdf")))
    with pytest.raises(CorpusManifestInvalid):
        load_corpus_manifest(path)


def test_parent_escaping_pdf_path_raises(tmp_path):
    path = write_manifest(tmp_path, manifest(document(pdf_path="../../source.pdf")))
    with pytest.raises(CorpusManifestInvalid):
        load_corpus_manifest(path)


def test_unknown_document_id_raises():
    with pytest.raises(CorpusEntryMissing):
        load_corpus_manifest().require("000000-2099H1-unknown")


# --- fail-closed: document level -------------------------------------------

def test_absent_pdf_raises(tmp_path):
    entry = CorpusDocument.model_validate(document())

    with pytest.raises(CorpusDocumentMissing):
        entry.require_pdf(tmp_path)


def test_pdf_hash_mismatch_raises(tmp_path):
    pdf = make_pdf(tmp_path)
    entry = CorpusDocument.model_validate(
        document(pdf_path="source.pdf", source_sha256="c" * 64)
    )

    with pytest.raises(CorpusHashMismatch):
        cm.verify_document(entry, tmp_path)


def test_page_count_mismatch_raises(tmp_path):
    from app.evidence.pdf_canonicalizer import canonicalize_pdf

    pdf = make_pdf(tmp_path, pages=2)
    digest = sha256(pdf.read_bytes()).hexdigest()
    canonical = canonicalize_pdf(
        document_id="SYNTH-2026H1", pdf_path=pdf, expected_source_sha256=digest
    )
    entry = CorpusDocument.model_validate(document(
        pdf_path="source.pdf", source_sha256=digest,
        canonical_sha256=canonical.canonical_sha256, page_count=9,
    ))

    with pytest.raises(CorpusPageCountMismatch):
        cm.verify_document(entry, tmp_path, verify_canonical=True)
