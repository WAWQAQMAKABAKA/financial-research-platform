"""M1.9B offline development comparison, not financial certification.

Reuses the frozen synthetic M1.9A corpus without changing its labels.
Builds a separate synthetic management packet for the bounded Reviewer.
This packet is NOT a verified real document or independent accounting truth.
"""
from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from app.evidence.contracts import SourceDocument
from app.modules.financial_report_analyst.management_semantic_screen import (
    screen_management_narrative,
)
from run_semantic_baseline import (
    _fixture,
    _load_cases,
    evaluate_synthetic,
)


def evaluate_delta() -> dict:
    before = evaluate_synthetic()
    _, cases = _load_cases()
    fixtures = _fixture()

    share_anchor = fixtures["DRUG_SHARE26"]
    growth_anchor = fixtures["DRUG_GROWTH26"]

    assert share_anchor.row_label_verbatim == "创新药占药品销售收入比重"
    assert growth_anchor.row_label_verbatim == "创新药销售收入同比增长"
    assert share_anchor.document_id == growth_anchor.document_id
    assert share_anchor.canonical_sha256 == growth_anchor.canonical_sha256

    share = share_anchor.value_verbatim.removesuffix("%")
    growth = growth_anchor.value_verbatim.removesuffix("%")
    assert share_anchor.value_verbatim.endswith("%")
    assert growth_anchor.value_verbatim.endswith("%")

    document = SourceDocument(
        document_id=share_anchor.document_id,
        ticker="SYN",
        report_period="2026H1",
        source_url="https://example.invalid/synthetic-management.pdf",
        published_on=date(2026, 8, 20),
        source_sha256="c" * 64,
        canonical_sha256=share_anchor.canonical_sha256,
    )

    passage = (
        "2026年上半年公司创新药销售收入1.23亿元，"
        f"同比增长{growth}%，"
        f"占药品销售收入的比重达{share}%。"
    )

    evidence_id = sha256("|".join((
        document.document_id,
        document.canonical_sha256,
        "1",
        "management-innovation-sales-v1",
        passage,
    )).encode()).hexdigest()

    management = {
        "status": "SOURCE_PASSAGE_REVIEWED",
        "document_id": document.document_id,
        "source_sha256": document.source_sha256,
        "canonical_sha256": document.canonical_sha256,
        "source_url": document.source_url,
        "source_page": 1,
        "source_kind": "MANAGEMENT_DISCUSSION_PASSAGE",
        "review_scope": "NATIVE_PDF_TEXT_AND_WORD_LOCATION_ONLY",
        "passage_whitespace_normalized": passage,
        "evidence_id": evidence_id,
        "financial_semantic_review": "NOT_PERFORMED",
        "research_publication": "BLOCKED",
    }

    as_of = datetime(
        2026, 8, 21,
        tzinfo=ZoneInfo("Asia/Shanghai"),
    )

    old_by_id = {row["id"]: row for row in before["cases"]}
    compared = []
    checked = []

    for case in cases:
        old = old_by_id[case["id"]]
        actual = old["actual"]
        reason = old["reason"]

        # Route by claim structure and evidence type, never by
        # expected label or case ID. Existing REJECT results stand.
        eligible = (
            case.get("engine") != "PIT"
            and case.get("structure") == "SOURCE_OBSERVATION"
            and case.get("anchors") in (
                ["DRUG_SHARE26"],
                ["DRUG_GROWTH26"],
            )
            and not case.get("mutation")
            and not case.get("source_packet_duplicate")
            and actual == "UNCERTAIN"
        )

        if eligible:
            result = screen_management_narrative(
                claim_id=case["id"],
                narrative=case["narrative"],
                evidence_id=evidence_id,
                management=management,
                document=document,
                as_of=as_of,
            )
            assert result.research_publication == "BLOCKED"
            assert result.financial_semantic_review == "NOT_QUALIFIED"

            actual = result.verdict.value
            reason = result.reason
            checked.append(case["id"])

        compared.append({
            "id": case["id"],
            "expected": case["expected"],
            "baseline": old["actual"],
            "new": actual,
            "reason": reason,
            "match": actual == case["expected"],
        })

    return {
        "evaluation_kind": "SYNTHETIC_DEVELOPMENT_ONLY",
        "corpus_sha256": before["corpus_sha256"],
        "baseline_exact_matches": before["exact_label_matches"],
        "delta_exact_matches": sum(r["match"] for r in compared),
        "bounded_case_ids": checked,
        "newly_rejected_cases": [
            r["id"] for r in compared
            if r["baseline"] == "UNCERTAIN" and r["new"] == "REJECT"
        ],
        "remaining_mismatches": [
            r["id"] for r in compared if not r["match"]
        ],
        "false_rejections_expected_uncertain": sum(
            r["expected"] == "UNCERTAIN" and r["new"] == "REJECT"
            for r in compared
        ),
        "unexpected_financial_admissions": sum(
            r["new"] not in {
                "REJECT", "UNCERTAIN", "BLOCK", "PIT_AVAILABLE"
            }
            for r in compared
        ),
        "research_publication": "BLOCKED",
        "bounded_cases": [
            r for r in compared if r["id"] in checked
        ],
        "limitation": (
            "Synthetic, development-only, same known corpus. "
            "No unseen-report or independent financial-semantic qualification."
        ),
    }


if __name__ == "__main__":
    print(json.dumps(
        evaluate_delta(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ))
