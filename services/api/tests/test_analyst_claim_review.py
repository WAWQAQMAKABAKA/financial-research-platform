"""M1.10A synthetic proposal/review boundary tests, no network or GT."""
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.evidence.contracts import SourceDocument
from app.modules.financial_report_analyst import analyst_claim_review as module

SOURCE = SourceDocument(
    document_id="SYNTHETIC-M110", ticker="SYN", report_period="2026H1",
    source_url="https://example.invalid/source.pdf",
    published_on=date(2026, 8, 20),
    source_sha256="a" * 64,
    canonical_sha256="b" * 64,
)
WHEN = datetime(2026, 8, 21, tzinfo=ZoneInfo("Asia/Shanghai"))
PASSAGE = (
    "2026年上半年公司创新药销售收入1.23亿元，"
    "同比增长4.56%，占药品销售收入的比重达7.89%。"
)


def setup_source(monkeypatch):
    evidence_id = sha256("|".join((
        SOURCE.document_id, SOURCE.canonical_sha256, "20",
        "management-innovation-sales-v1", PASSAGE,
    )).encode()).hexdigest()
    packet = {
        "status": "SOURCE_PASSAGE_REVIEWED",
        "review_scope": "NATIVE_PDF_TEXT_AND_WORD_LOCATION_ONLY",
        "source_kind": "MANAGEMENT_DISCUSSION_PASSAGE",
        "document_id": SOURCE.document_id,
        "source_sha256": SOURCE.source_sha256,
        "canonical_sha256": SOURCE.canonical_sha256,
        "source_url": SOURCE.source_url,
        "source_page": 20,
        "passage_whitespace_normalized": PASSAGE,
        "evidence_id": evidence_id,
        "financial_semantic_review": "NOT_PERFORMED",
        "research_publication": "BLOCKED",
    }
    monkeypatch.setattr(module.revenue_scope, "SOURCE", SOURCE)

    def locate(path, *, as_of):
        assert path == Path("/offline-synthetic.pdf")
        SOURCE.require_available(as_of)
        return packet

    monkeypatch.setattr(module.management_evidence, "locate_management_excerpt", locate)
    return packet


@pytest.mark.parametrize("draft,verdict,reason", [
    ("Innovative-drug sales accounted for 7.89% of overall company revenue.",
     "REJECT", "SOURCE_SHARE_DENOMINATOR_SUBSTITUTED"),
    ("Company-wide revenue increased 4.56% year-on-year.",
     "REJECT", "SOURCE_GROWTH_METRIC_SUBSTITUTED"),
    ("Innovative-drug sales accounted for 7.89% of total drug sales.",
     "UNCERTAIN", "SOURCE_SHARE_NOT_FINANCIALLY_QUALIFIED"),
    ("Management expects innovative-drug sales to accelerate.",
     "UNCERTAIN", "NARRATIVE_NOT_WITHIN_BOUNDED_GRAMMAR"),
    ("Company-wide revenue increased 99% year-on-year.",
     "UNCERTAIN", "GROWTH_PERCENTAGE_NOT_SOURCE_MATCHED"),
])
def test_free_text_no_expected_verdict_table(monkeypatch, draft, verdict, reason):
    source = setup_source(monkeypatch)
    result = module.review_analyst_draft(
        Path("/offline-synthetic.pdf"), draft, as_of=WHEN,
    )
    assert result["claim"]["text"] == draft
    assert result["claim"]["evidence_ids"] == [source["evidence_id"]]
    assert result["review"]["verdict"] == verdict
    assert result["review"]["reason"] == reason
    assert result["review"]["compared_evidence_ids"] == [source["evidence_id"]]
    assert result["review"]["claim_id"] == result["claim"]["claim_id"]
    assert result["research_publication"] == "BLOCKED"
    assert result["financial_semantic_review"] == "NOT_QUALIFIED"
    assert result["draft_origin"] == "MANUAL_ANALYST_DRAFT"
    assert result["source_sha256"] == SOURCE.source_sha256


def test_proposal_cannot_supply_source_evidence(monkeypatch):
    setup_source(monkeypatch)
    with pytest.raises(TypeError):
        module.review_analyst_draft(
            Path("/offline-synthetic.pdf"),
            "Example text", as_of=WHEN, evidence_id="forged",
        )


def test_bad_evidence_packet_withheld(monkeypatch):
    packet = setup_source(monkeypatch)
    packet["evidence_id"] = "f" * 64
    with pytest.raises(ValueError, match="REVIEW_SOURCE_BINDING_FAILED"):
        module.review_analyst_draft(
            Path("/offline-synthetic.pdf"),
            "Innovative-drug sales were 7.89% of total company revenue.",
            as_of=WHEN,
        )


def test_prepublication_pit_blocked(monkeypatch):
    setup_source(monkeypatch)
    early = datetime(2026, 8, 20, 23, 59, tzinfo=ZoneInfo("Asia/Shanghai"))
    with pytest.raises(ValueError, match="PIT_UNAVAILABLE"):
        module.review_analyst_draft(
            Path("/offline-synthetic.pdf"), "a source observation",
            as_of=early,
        )


def test_overlong_and_empty_proposals_rejected(monkeypatch):
    setup_source(monkeypatch)
    for draft in ("", " ", "a" * 401, "界" * 401):
        with pytest.raises(ValueError, match="INVALID_ANALYST_CANDIDATE"):
            module.review_analyst_draft(
                Path("/offline-synthetic.pdf"), draft, as_of=WHEN,
            )
