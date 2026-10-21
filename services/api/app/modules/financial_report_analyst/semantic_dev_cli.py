"""Offline original-PDF M1.6B defensive screen diagnostic. No LLM calls."""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.modules.financial_report_analyst import revenue_scope
from app.modules.financial_report_analyst.semantic_gate import (
    AssertionStructure, ScreenVerdict, SemanticClaimProposal,
    SourceValueCandidate, screen_financial_association,
)


def main() -> int:
    p = argparse.ArgumentParser(description="Offline source-bound financial contradiction diagnostic")
    p.add_argument("--pdf", type=Path, required=True)
    args = p.parse_args()
    try:
        source = revenue_scope.build_source_draft(
            revenue_scope.SOURCE, args.pdf, as_of=datetime.now(ZoneInfo("Asia/Shanghai"))
        )
        if source["status"] != "SOURCE_DRAFT_READY" or source["research_publication"] != "BLOCKED":
            raise ValueError("UNQUALIFIED_SOURCE_DRAFT")
        if len(source["observations"]) != 2 or len(source["reviews"]) != 2:
            raise ValueError("UNEXPECTED_SOURCE_PACKET_SIZE")
        if any(r.get("verdict") != "ADMIT" or r.get("rationale") != "LITERAL_CELL_AND_HEADING_SOURCE_CHECK_ONLY"
               for r in source["reviews"]):
            raise ValueError("LITERAL_REVIEW_NOT_PASSED")
        candidates = tuple(SourceValueCandidate(
            evidence_id=o["evidence_id"], document_id=source["document_id"],
            canonical_sha256=source["canonical_sha256"],
            statement_kind_candidate=o["statement_type_candidate"],
            row_label_verbatim=o["row_label"], column_header_verbatim=o["column_header"],
            value_verbatim=o["value_verbatim"], metric_identity_candidate=None,
        ) for o in source["observations"])
        if len({x.evidence_id for x in candidates}) != 2:
            raise ValueError("DUPLICATE_EVIDENCE")
    except (OSError, ValueError, KeyError, TypeError, IndexError) as e:
        print("STOP: ORIGINAL_SOURCE_DIAGNOSTIC_UNAVAILABLE", type(e).__name__)
        return 1

    fact = SemanticClaimProposal(claim_id="SOURCE_FACT", claim_kind="OBSERVED_FACT",
                                 structure=AssertionStructure.SOURCE_OBSERVATION,
                                 values=(candidates[0],))
    invalid_comparison = SemanticClaimProposal(
        claim_id="FALSE_PERIOD_CHANGE", claim_kind="OBSERVED_FACT",  # kind cannot bypass screen
        structure=AssertionStructure.PERIOD_COMPARISON, values=candidates,
        unreviewed_text="Treat the two source figures as a year-over-year change.",
    )
    factual = screen_financial_association(fact, candidates)
    comparison = screen_financial_association(invalid_comparison, candidates)
    print("SOURCE_DOCUMENT:", source["document_id"])
    print("SOURCE_PAGES:", ", ".join(str(x["page_number"]) for x in source["observations"]))
    print("SOURCE_FACT:", factual.verdict.value, factual.reason)
    print("INVALID_COMPARISON:", comparison.verdict.value, comparison.reason)
    print("RESEARCH_PUBLICATION: BLOCKED")
    if not (factual.verdict == ScreenVerdict.UNCERTAIN
            and comparison.verdict == ScreenVerdict.REJECT
            and comparison.reason == "COMPARISON_SOURCE_ASSOCIATION_MISMATCH:statement_kind_candidate"):
        print("STOP: SEMANTIC_CONTRADICTION_SCREEN_FAILED")
        return 1
    print("M16B_REAL_SOURCE_DEFENSIVE_SCREEN_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
