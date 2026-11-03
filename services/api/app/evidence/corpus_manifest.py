"""Fail-closed corpus manifest: the single authorized source of document identity.

Before this module, every source identity was a ``SourceDocument(...)`` literal
duplicated across ``revenue_scope.py`` and ``preview.py``, while the PDFs those
literals described are gitignored. A fresh clone therefore declared no authorized
corpus at all and could silently carry an identity for a document it could not
read. This module makes the authorized corpus explicit, tracked, and verifiable.

Declaring a document authorizes local source evidence only. It does not perform
financial-semantic review, does not establish accounting equivalence, and does
not permit publication. Those gates remain where they are; this module only makes
source identity non-hardcoded and fail-closed.

Nothing here is imported by existing feature modules yet (M0a scope).
"""

from __future__ import annotations

from datetime import date
from hashlib import sha256
from pathlib import Path
import json
import re

from pydantic import Field, ValidationError, model_validator

from app.evidence.contracts import SourceDocument, StrictRecord

SCHEMA_VERSION = "corpus.v1"

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_MANIFEST_PATH = REPO_ROOT / "data/manifests/corpus.v1.json"

_HASH = re.compile(r"^[0-9a-f]{64}$")
_RELATIVE_PDF_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*\.pdf$")


class CorpusManifestError(Exception):
    """Base class; subclasses carry a stable machine-readable ``code``."""

    code = "CORPUS_ERROR"


class CorpusManifestMissing(CorpusManifestError):
    code = "CORPUS_MANIFEST_MISSING"


class CorpusManifestInvalid(CorpusManifestError):
    code = "CORPUS_MANIFEST_INVALID"


class CorpusEntryMissing(CorpusManifestError):
    code = "CORPUS_ENTRY_MISSING"


class CorpusDocumentMissing(CorpusManifestError):
    code = "CORPUS_DOCUMENT_MISSING"


class CorpusHashMismatch(CorpusManifestError):
    code = "CORPUS_HASH_MISMATCH"


class CorpusPageCountMismatch(CorpusManifestError):
    code = "CORPUS_PAGE_COUNT_MISMATCH"


class CorpusDocument(StrictRecord):
    """One authorized document. Hashes are the identity; prose is not."""

    document_id: str = Field(min_length=1)
    ticker: str = Field(pattern=r"^[0-9]{6}$")
    issuer_name: str = Field(min_length=1)
    report_period: str = Field(pattern=r"^[0-9]{4}H[12]$")
    source_url: str = Field(min_length=1)
    published_on: date
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_count: int = Field(ge=1)
    pdf_path: str = Field(min_length=1)
    authorization_note: str = Field(min_length=1)
    acquisition: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_pdf_path(self):
        parts = Path(self.pdf_path).parts
        if not _RELATIVE_PDF_PATH.fullmatch(self.pdf_path) or ".." in parts:
            raise ValueError("PDF_PATH_MUST_BE_RELATIVE_INSIDE_REPO")
        return self

    def to_source_document(self) -> SourceDocument:
        """The identity contract the rest of the codebase already speaks."""
        return SourceDocument(
            document_id=self.document_id,
            ticker=self.ticker,
            report_period=self.report_period,
            source_url=self.source_url,
            published_on=self.published_on,
            source_sha256=self.source_sha256,
            canonical_sha256=self.canonical_sha256,
        )

    def require_pdf(self, repo_root: Path | None = None) -> Path:
        root = REPO_ROOT if repo_root is None else Path(repo_root).resolve()
        path = (root / self.pdf_path).resolve()
        if root != path and root not in path.parents:
            raise CorpusManifestInvalid(
                f"PDF_PATH_ESCAPES_REPO:{self.document_id}:{self.pdf_path}"
            )
        if not path.is_file():
            raise CorpusDocumentMissing(f"{self.document_id}:{path}")
        return path


class CorpusManifest(StrictRecord):
    schema_version: str = Field(min_length=1)
    authorized_on: date
    authorization_note: str = Field(min_length=1)
    acquisition_note: str = Field(min_length=1)
    documents: tuple[CorpusDocument, ...]

    @model_validator(mode="after")
    def validate_manifest(self):
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("UNSUPPORTED_SCHEMA_VERSION")
        if not self.documents:
            raise ValueError("CORPUS_EMPTY")
        ids = [document.document_id for document in self.documents]
        if len(set(ids)) != len(ids):
            raise ValueError("DUPLICATE_DOCUMENT_ID")
        return self

    @property
    def document_ids(self) -> tuple[str, ...]:
        return tuple(document.document_id for document in self.documents)

    def require(self, document_id: str) -> CorpusDocument:
        for document in self.documents:
            if document.document_id == document_id:
                return document
        raise CorpusEntryMissing(f"{document_id}:{','.join(self.document_ids)}")


def load_corpus_manifest(path: Path | None = None) -> CorpusManifest:
    """Load and validate the tracked manifest. Never returns a partial corpus."""
    source = DEFAULT_MANIFEST_PATH if path is None else Path(path)
    if not source.is_file():
        raise CorpusManifestMissing(str(source))
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CorpusManifestInvalid(f"{source}:{exc}") from exc
    try:
        return CorpusManifest.model_validate(payload)
    except ValidationError as exc:
        raise CorpusManifestInvalid(f"{source}:{exc}") from exc


def sha256_file(path: Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_document(
    document: CorpusDocument,
    repo_root: Path | None = None,
    *,
    verify_canonical: bool = False,
) -> Path:
    """Check the declared PDF really is the declared document.

    Cheap path (default) verifies presence and the raw source bytes. Setting
    ``verify_canonical`` additionally re-derives the canonical text hash and page
    count, which is the expensive but authoritative check.
    """
    path = document.require_pdf(repo_root)

    actual = sha256_file(path)
    if actual != document.source_sha256:
        raise CorpusHashMismatch(
            f"SOURCE:{document.document_id}:expected={document.source_sha256}:actual={actual}"
        )

    if not verify_canonical:
        return path

    # Local import: the canonicalizer pulls PyMuPDF, which identity loading
    # should not require just to read the manifest.
    from app.evidence.pdf_canonicalizer import canonicalize_pdf

    canonical = canonicalize_pdf(
        document_id=document.document_id,
        pdf_path=path,
        expected_source_sha256=document.source_sha256,
    )
    if canonical.canonical_sha256 != document.canonical_sha256:
        raise CorpusHashMismatch(
            f"CANONICAL:{document.document_id}:"
            f"expected={document.canonical_sha256}:actual={canonical.canonical_sha256}"
        )
    if len(canonical.pages) != document.page_count:
        raise CorpusPageCountMismatch(
            f"{document.document_id}:expected={document.page_count}:"
            f"actual={len(canonical.pages)}"
        )
    return path
