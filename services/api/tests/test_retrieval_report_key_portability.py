"""M130-B3: report identity portability without issuer-specific retrieval rules.

Synthetic source identity checks only; do not establish real-document relevance.
No model, trading, network or evaluation ground truth.
"""
from dataclasses import replace
from datetime import datetime
from hashlib import sha256
from zoneinfo import ZoneInfo

import pytest

from app.evidence.contracts import SourceDocument
from app.modules.financial_report_analyst import canonical_retrieval
from test_canonical_retrieval import synthetic_document

WHEN = datetime(2026, 10, 27, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
QUESTION = "创新药销售收入和研发有什么进展？"


@pytest.mark.parametrize("ticker,period", [
    ("600276", "2026H1"),
    ("600519", "2026H1"),
    ("000651", "2026H1"),
    ("600519", "2025FY"),
])
def test_report_key_follows_verified_source_identity(ticker, period):
    source, document = synthetic_document()
    doc_id = f"{ticker}-{period}-synthetic-test"
    source = SourceDocument.model_validate({
        **source.model_dump(mode="python"),
        "ticker": ticker,
        "report_period": period,
        "document_id": doc_id,
    })
    document = replace(document, document_id=doc_id)
    result = canonical_retrieval.retrieve_from_canonical(
        source, document, QUESTION, as_of=WHEN,
    )
    assert result["report_key"] == f"{ticker}-{period}"
    assert result["document_id"] == doc_id
    assert result["source_sha256"] == source.source_sha256
    assert result["canonical_sha256"] == source.canonical_sha256
    assert result["research_publication"] == "BLOCKED"
    assert result["financial_semantic_review"] == "NOT_PERFORMED"
    assert result["report_storage"] == "NOT_PERSISTED"
    assert result["status"] == "RETRIEVAL_CANDIDATES_READY"
    for hit in result["evidence"]:
        assert document.canonical_text[
            hit["canonical_start"]:hit["canonical_end"]
        ] == hit["source_excerpt"]
    # The retrieval/evidence identity algorithm is unchanged by this patch.
    expected_run = sha256("|".join((
        canonical_retrieval.RETRIEVER_VERSION, doc_id,
        source.canonical_sha256, WHEN.date().isoformat(), QUESTION,
    )).encode("utf-8")).hexdigest()
    assert result["retrieval_id"] == expected_run


def test_cross_bound_source_identity_still_fails_closed():
    source, document = synthetic_document()
    wrong = SourceDocument.model_validate({
        **source.model_dump(mode="python"),
        "document_id": "other-issuer-report",
    })
    with pytest.raises(ValueError, match="CANONICAL_SOURCE_BINDING_INVALID"):
        canonical_retrieval.retrieve_from_canonical(
            wrong, document, QUESTION, as_of=WHEN,
        )
