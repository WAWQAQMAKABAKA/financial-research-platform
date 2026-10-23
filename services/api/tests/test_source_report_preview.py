"""M112 synthetic report-contract tests. No benchmark GT, model or network."""
from datetime import date, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.evidence.contracts import SourceDocument
from app.modules.financial_report_analyst import source_report_preview as report

WHEN = datetime(2026, 10, 23, 12, tzinfo=ZoneInfo("Asia/Shanghai"))
PDF = Path("/offline-synthetic-report.pdf")
PASSAGE = (
    "2026年上半年公司创新药销售收入1.23亿元，"
    "同比增长4.56%，占药品销售收入的比重达7.89%。"
)


@pytest.fixture
def synthetic(monkeypatch):
    source = SourceDocument(
        document_id="SYNTHETIC-M112",
        ticker="SYN",
        report_period="2026H1",
        source_url="https://example.invalid/offline.pdf",
        published_on=date(2026, 8, 20),
        source_sha256="a" * 64,
        canonical_sha256="b" * 64,
    )
    monkeypatch.setattr(report.revenue_scope, "SOURCE", source)

    draft_id = sha256((
        source.document_id + "|" + source.canonical_sha256
        + "|revenue-scope-preview-v1"
    ).encode()).hexdigest()

    observations = []
    claims = []
    reviews = []

    for i, selection in enumerate(report.revenue_scope.SELECTIONS):
        claim_id = f"REV{i+1}"
        evidence_id = str(i + 1) * 64
        title = "合并利润表" if i == 0 else "母公司利润表"
        value = f"{i+1},234.56"
        row = selection["row_label"]
        column = selection["column_header"]

        observations.append({
            "claim_id": claim_id,
            "evidence_id": evidence_id,
            "statement_title": title,
            "statement_type_candidate": selection["section_kind"],
            "row_label": row,
            "column_header": column,
            "value_verbatim": value,
            "statement_context": "2026 年 1—6 月 单位：元 币种：人民币",
            "page_number": i + 10,
            "source_text_span_status": "NOT_PROVEN_FROM_TABLE_GEOMETRY",
            "review_scope": "LITERAL_CELL_LOCATION_ONLY",
        })
        claims.append({
            "claim_id": claim_id,
            "kind": "OBSERVED_FACT",
            "evidence_ids": [evidence_id],
            "text": (
                f'In the source section "{title}", '
                f'the row "{row}" under "{column}" reads "{value}".'
            ),
        })
        reviews.append({
            "claim_id": claim_id,
            "verdict": "ADMIT",
            "reviewer_id": "native-pdf-cell-literal-reviewer-v1",
            "rationale": "LITERAL_CELL_AND_HEADING_SOURCE_CHECK_ONLY",
        })

    draft = {
        "status": "SOURCE_DRAFT_READY",
        "report_id": draft_id,
        "document_id": source.document_id,
        "source_sha256": source.source_sha256,
        "canonical_sha256": source.canonical_sha256,
        "source_url": source.source_url,
        "research_publication": "BLOCKED",
        "financial_semantic_review": "NOT_PERFORMED",
        "observations": observations,
        "claims": claims,
        "reviews": reviews,
    }

    management_id = sha256("|".join((
        source.document_id,
        source.canonical_sha256,
        "20",
        "management-innovation-sales-v1",
        PASSAGE,
    )).encode()).hexdigest()

    management = {
        "status": "SOURCE_PASSAGE_REVIEWED",
        "document_id": source.document_id,
        "source_sha256": source.source_sha256,
        "canonical_sha256": source.canonical_sha256,
        "source_url": source.source_url,
        "source_kind": "MANAGEMENT_DISCUSSION_PASSAGE",
        "review_scope": "NATIVE_PDF_TEXT_AND_WORD_LOCATION_ONLY",
        "source_page": 20,
        "passage_whitespace_normalized": PASSAGE,
        "evidence_id": management_id,
        "financial_semantic_review": "NOT_PERFORMED",
        "research_publication": "BLOCKED",
    }

    def source_builder(src, path, *, as_of):
        assert src is source
        assert path == PDF
        source.require_available(as_of)
        return draft

    def management_locator(path, *, as_of):
        assert path == PDF
        source.require_available(as_of)
        return management

    monkeypatch.setattr(
        report.revenue_scope, "build_source_draft", source_builder,
    )
    monkeypatch.setattr(
        report.management_evidence,
        "locate_management_excerpt",
        management_locator,
    )

    return draft, management


def build():
    return report.build_source_report(PDF, as_of=WHEN)


def test_report_identity_and_claim_graph(synthetic):
    packet = build()
    assert packet["status"] == "LOCAL_SOURCE_REPORT_READY"
    assert packet["research_publication"] == "BLOCKED"
    assert packet["financial_semantic_review"] == "NOT_PERFORMED"
    assert packet["report_storage"] == "NOT_PERSISTED"
    assert packet["analyst_interpretation"]["status"] == "WITHHELD"
    assert [x["claim_id"] for x in packet["observations"]] == [
        "REV1", "REV2",
    ]
    assert packet["management_statement"]["claim_id"] == "M1"
    assert packet["management_statement"]["text"] == PASSAGE
    assert len({
        *(x["evidence_id"] for x in packet["observations"]),
        packet["management_statement"]["evidence_id"],
    }) == 3


def test_report_identity_stable_within_day(synthetic):
    first = build()
    later = report.build_source_report(
        PDF, as_of=WHEN + timedelta(hours=1),
    )
    assert first["report_identity"] == later["report_identity"]
    assert first["source_draft_id"] == later["source_draft_id"]


def test_report_identity_changes_with_as_of_date(synthetic):
    first = build()
    later = report.build_source_report(
        PDF, as_of=WHEN + timedelta(days=1),
    )
    assert first["report_identity"] != later["report_identity"]


def test_unqualified_source_is_rejected(synthetic):
    draft, _ = synthetic
    draft["status"] = "WITHHELD"
    with pytest.raises(ValueError, match="SOURCE_DRAFT_NOT_QUALIFIED"):
        build()


def test_forged_source_claim_binding_is_rejected(synthetic):
    draft, _ = synthetic
    draft["claims"][0]["evidence_ids"] = ["f" * 64]
    with pytest.raises(ValueError, match="SOURCE_OBSERVATION_BINDING_INVALID"):
        build()


def test_changed_literal_claim_text_is_rejected(synthetic):
    draft, _ = synthetic
    draft["claims"][0]["text"] = "An invented financial conclusion"
    with pytest.raises(ValueError, match="SOURCE_CLAIM_TEXT_MISMATCH"):
        build()


def test_fake_literal_reviewer_is_rejected(synthetic):
    draft, _ = synthetic
    draft["reviews"][0]["rationale"] = "FINANCIAL_SEMANTICS_APPROVED"
    with pytest.raises(ValueError, match="SOURCE_OBSERVATION_BINDING_INVALID"):
        build()


def test_forged_management_evidence_is_rejected(synthetic):
    _, management = synthetic
    management["evidence_id"] = "f" * 64
    with pytest.raises(ValueError, match="MANAGEMENT_EVIDENCE_BINDING_INVALID"):
        build()


def test_management_source_identity_mismatch_is_rejected(synthetic):
    _, management = synthetic
    management["source_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="MANAGEMENT_SOURCE_NOT_QUALIFIED"):
        build()


def test_management_text_outside_bounded_source_is_rejected(synthetic):
    _, management = synthetic
    management["passage_whitespace_normalized"] = (
        "Management predicts future earnings."
    )
    with pytest.raises(ValueError, match="MANAGEMENT_SOURCE_NOT_QUALIFIED"):
        build()


def test_prepublication_pit_is_rejected(synthetic):
    before_available = datetime(
        2026, 8, 20, 23, 59,
        tzinfo=ZoneInfo("Asia/Shanghai"),
    )
    with pytest.raises(ValueError, match="PIT_UNAVAILABLE"):
        report.build_source_report(PDF, as_of=before_available)
