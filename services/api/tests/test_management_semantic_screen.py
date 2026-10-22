"""M1.9B synthetic contradiction tests; no protected GT or provider."""
from datetime import date, datetime
from hashlib import sha256
from zoneinfo import ZoneInfo

import pytest

from app.evidence.contracts import SourceDocument
from app.modules.financial_report_analyst.management_semantic_screen import (
    screen_management_narrative,
)

DOC = SourceDocument(
    document_id="SYNTHETIC-26",
    ticker="SYN",
    report_period="2026H1",
    source_url="https://example.invalid/synthetic.pdf",
    published_on=date(2026, 8, 20),
    source_sha256="a" * 64,
    canonical_sha256="b" * 64,
)

AS_OF = datetime(2026, 8, 21, tzinfo=ZoneInfo("Asia/Shanghai"))

PASSAGE = (
    "2026年上半年公司创新药销售收入1.23亿元，"
    "同比增长4.56%，占药品销售收入的比重达7.89%。"
)


def packet(passage=PASSAGE):
    page = 20
    eid = sha256("|".join((
        DOC.document_id, DOC.canonical_sha256, str(page),
        "management-innovation-sales-v1", passage,
    )).encode()).hexdigest()

    return {
        "status": "SOURCE_PASSAGE_REVIEWED",
        "review_scope": "NATIVE_PDF_TEXT_AND_WORD_LOCATION_ONLY",
        "source_kind": "MANAGEMENT_DISCUSSION_PASSAGE",
        "document_id": DOC.document_id,
        "source_sha256": DOC.source_sha256,
        "canonical_sha256": DOC.canonical_sha256,
        "source_url": DOC.source_url,
        "financial_semantic_review": "NOT_PERFORMED",
        "research_publication": "BLOCKED",
        "source_page": page,
        "passage_whitespace_normalized": passage,
        "evidence_id": eid,
    }


def judge(text, management=None, *, as_of=AS_OF, evidence_id=None):
    m = packet() if management is None else management
    return screen_management_narrative(
        claim_id="SYN-C1",
        narrative=text,
        evidence_id=m["evidence_id"] if evidence_id is None else evidence_id,
        management=m,
        document=DOC,
        as_of=as_of,
    )


@pytest.mark.parametrize("text,reason", [
    (
        "Innovative-drug sales were 7.89% of total consolidated company revenue.",
        "SOURCE_SHARE_DENOMINATOR_SUBSTITUTED",
    ),
    (
        "Innovative-drug sales accounted for 7.89% of overall company revenue.",
        "SOURCE_SHARE_DENOMINATOR_SUBSTITUTED",
    ),
    (
        "Total consolidated company revenue grew 4.56% year over year.",
        "SOURCE_GROWTH_METRIC_SUBSTITUTED",
    ),
    (
        "Company-wide revenue increased 4.56% year-on-year.",
        "SOURCE_GROWTH_METRIC_SUBSTITUTED",
    ),
    (
        "Innovative-drug sales represented 9.99% of drug sales revenue.",
        "SOURCE_SHARE_PERCENTAGE_MISMATCH",
    ),
    (
        "Innovative-drug sales fell 4.56% year over year.",
        "SOURCE_GROWTH_DIRECTION_MISMATCH",
    ),
])
def test_explicit_substitutions_rejected(text, reason):
    out = judge(text)
    assert out.verdict.value == "REJECT"
    assert out.reason == reason
    assert out.financial_semantic_review == "NOT_QUALIFIED"
    assert out.research_publication == "BLOCKED"


@pytest.mark.parametrize("text", [
    "Innovative-drug sales were 7.89% of drug sales revenue.",
    "Innovative-drug sales grew 4.56% year over year.",
    "Innovative-drug sales were 7.89% of total consolidated company revenue?",
    "It is incorrect to say innovative-drug sales were 7.89% of total company revenue.",
    "Total consolidated company revenue grew 99% year over year.",
    "This supports a future valuation uplift.",
])
def test_uncertain_cases_not_falsely_rejected(text):
    assert judge(text).verdict.value == "UNCERTAIN"


def test_tampered_evidence_never_admitted():
    m = packet()
    m["passage_whitespace_normalized"] = PASSAGE.replace("7.89", "8.89")

    text = "Innovative-drug sales were 7.89% of total company revenue."

    assert judge(text, m).verdict.value == "UNCERTAIN"
    assert judge(text, evidence_id="forged").verdict.value == "UNCERTAIN"


def test_pit_and_unqualified_source_fail_closed():
    m = packet()
    m["status"] = "UNVERIFIED"

    text = "Innovative-drug sales were 7.89% of total company revenue."

    assert judge(text, m).verdict.value == "UNCERTAIN"

    before = datetime(
        2026, 8, 20, 23, 59,
        tzinfo=ZoneInfo("Asia/Shanghai"),
    )

    assert judge(
        text, as_of=before,
    ).reason == "SOURCE_OR_PIT_UNAVAILABLE"


def test_unrecognized_source_sentence_abstains():
    other = PASSAGE.replace("公司创新药销售收入", "公司其他业务收入")
    m = packet(other)

    assert judge(
        "Innovative-drug sales were 7.89% of total company revenue.",
        m,
    ).verdict.value == "UNCERTAIN"
