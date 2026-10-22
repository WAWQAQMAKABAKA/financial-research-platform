"""M1.9A: READ-ONLY, strictly offline synthetic financial-association baseline.

Development labels and scoring live exclusively in evaluations/offline. This
module imports frozen production interfaces, never changes them or calls APIs.
No benchmark GT, private evaluation set, PDF reference answer, or credentials.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo

from app.evidence.contracts import SourceDocument
from app.modules.financial_report_analyst.semantic_gate import (
    AssertionStructure, CandidateMetricIdentity, SemanticClaimProposal,
    SourceValueCandidate, screen_financial_association,
)

CORPUS = Path(__file__).with_name("development_cases_v1.json")
SYNTHETIC_SHA = "a" * 64


def _identity(year: int) -> CandidateMetricIdentity:
    return CandidateMetricIdentity(
        issuer_id="SYNTHETIC-ISSUER", metric_code="revenue",
        reporting_scope="consolidated", category="all_company_sales",
        accounting_basis="synthetic_fixture_only", period_basis="H1",
        period_start=date(year, 1, 1), period_end=date(year, 6, 30), unit="SYN_CNY",
    )


def _fixture() -> dict[str, SourceValueCandidate]:
    def s(name, document, statement, row, header, value, identity=None):
        return SourceValueCandidate(
            evidence_id=f"SYN-{name}", document_id=document,
            canonical_sha256=SYNTHETIC_SHA,
            statement_kind_candidate=statement, row_label_verbatim=row,
            column_header_verbatim=header, value_verbatim=value,
            metric_identity_candidate=identity,
        )
    return {
        "CONS26": s("CONS26", "SYNTHETIC-26", "consolidated_income_statement",
                    "其中：营业收入", "2026 年半年度", "1,234.56", _identity(2026)),
        "CONS26_ALT": s("CONS26_ALT", "SYNTHETIC-26", "consolidated_income_statement",
                        "其中：营业收入", "2026 年半年度", "1,111.11", _identity(2026)),
        "PARENT26": s("PARENT26", "SYNTHETIC-26", "parent_income_statement",
                      "一、营业收入", "2026 年半年度", "950.00"),
        "CONS25": s("CONS25", "SYNTHETIC-25", "consolidated_income_statement",
                    "其中：营业收入", "2025 年半年度", "1,000.00", _identity(2025)),
        "DRUG_SHARE26": s("DRUG_SHARE26", "SYNTHETIC-26", "management_discussion",
                          "创新药占药品销售收入比重", "2026年上半年", "60.00%"),
        "DRUG_GROWTH26": s("DRUG_GROWTH26", "SYNTHETIC-26", "management_discussion",
                           "创新药销售收入同比增长", "2026年上半年", "10.00%"),
    }


def _load_cases(path: Path = CORPUS) -> tuple[dict, list[dict]]:
    raw = path.read_bytes()
    payload = json.loads(raw)
    if payload.get("schema_version") != "frp-semantic-development-v1":
        raise ValueError("UNEXPECTED_EVAL_SCHEMA")
    if payload.get("corpus_type") != "SYNTHETIC_DEVELOPMENT_ONLY_NOT_PROTECTED_GROUND_TRUTH":
        raise ValueError("EVAL_PROVENANCE_MISMATCH")
    cases = payload["cases"]
    if not isinstance(cases, list) or not cases or len({c["id"] for c in cases}) != len(cases):
        raise ValueError("DUPLICATE_OR_EMPTY_EVAL_CASES")
    return {"corpus_sha256": sha256(raw).hexdigest(), "schema_version": payload["schema_version"]}, cases


def _evaluate(case: dict, fixtures: dict[str, SourceValueCandidate]) -> tuple[str, str, bool]:
    if case.get("engine") == "PIT":
        document = SourceDocument(
            document_id="SYNTHETIC-PIT", ticker="SYN", report_period="2026H1",
            source_url="https://example.invalid/synthetic-source.pdf",
            published_on=date(2026, 8, 20),
            source_sha256="a" * 64, canonical_sha256="b" * 64,
        )
        instant = datetime.fromisoformat(case["as_of"])
        try:
            document.require_available(instant)
        except ValueError as e:
            if str(e) == "PIT_UNAVAILABLE":
                return "BLOCK", "PIT_UNAVAILABLE", True
            raise
        return "PIT_AVAILABLE", "SOURCE_DATE_GATE_ONLY", True

    originals = tuple(fixtures[k] for k in case["anchors"])
    proposal_values = list(originals)
    mutation = case.get("mutation")
    if mutation:
        field, value = mutation["field"], mutation["value"]
        allowed = {"value_verbatim", "column_header_verbatim", "statement_kind_candidate",
                   "canonical_sha256", "evidence_id", "metric_identity_candidate"}
        if field not in allowed:
            raise ValueError("UNEXPECTED_MUTATION")
        if value == "UNSUPPORTED_SYNTHETIC_IDENTITY":
            value = _identity(2026)
        proposal_values[0] = proposal_values[0].model_copy(update={field: value})
    unique_source_packet = tuple({item.evidence_id: item for item in originals}.values())
    source_candidates = unique_source_packet + ((originals[0],) if case.get("source_packet_duplicate") else ())
    proposal = SemanticClaimProposal(
        claim_id=case["id"], claim_kind="OBSERVED_FACT",
        structure=AssertionStructure(case["structure"]),
        values=tuple(proposal_values), unreviewed_text=case["narrative"],
    )
    result = screen_financial_association(proposal, source_candidates)
    if result.financial_semantic_review != "NOT_QUALIFIED" or result.research_publication != "BLOCKED":
        raise ValueError("PUBLICATION_BOUNDARY_BREACHED")
    actual = result.verdict.value
    trace = (result.compared_evidence_ids == tuple(p.evidence_id for p in proposal_values))
    return actual, result.reason, trace


def evaluate_synthetic(path: Path = CORPUS) -> dict:
    meta, cases = _load_cases(path)
    fixtures = _fixture()
    results = []
    for case in cases:
        actual, reason, trace = _evaluate(case, fixtures)
        expected = case["expected"]
        if expected not in {"REJECT", "UNCERTAIN", "BLOCK", "PIT_AVAILABLE"}:
            raise ValueError("INVALID_DEVELOPMENT_EXPECTATION")
        results.append({
            "id": case["id"], "family": case["family"],
            "expected": expected, "actual": actual, "match": actual == expected,
            "reason": reason, "trace_check": trace,
            "diagnostic_only": expected in {"REJECT", "UNCERTAIN"},
        })
    labels = Counter(r["actual"] for r in results)
    mismatches = [r for r in results if not r["match"]]
    expected_reject = [r for r in results if r["expected"] == "REJECT"]
    true_reject = sum(r["actual"] == "REJECT" for r in expected_reject)
    synthetic_screen = [r for r in results if r["diagnostic_only"]]
    return {
        **meta,
        "evaluation_kind": "SYNTHETIC_DEVELOPMENT_BASELINE_NOT_INDEPENDENT_QUALIFICATION",
        "baseline_ancestor_commit": "68112420ff674225efffda8f06958fb826d82f80",
        "total_cases": len(results),
        "screen_cases": len(synthetic_screen),
        "pit_cases": len(results) - len(synthetic_screen),
        "exact_label_matches": sum(r["match"] for r in results),
        "synthetic_expected_reject": len(expected_reject),
        "synthetic_rejected_when_expected": true_reject,
        "synthetic_reject_recall": round(true_reject / len(expected_reject), 4) if expected_reject else None,
        "missed_explicit_contradictions_as_uncertain": sum(r["expected"] == "REJECT" and r["actual"] == "UNCERTAIN" for r in results),
        "false_rejections_on_expected_uncertain": sum(r["expected"] == "UNCERTAIN" and r["actual"] == "REJECT" for r in results),
        "unexpected_financial_admissions": sum(r["actual"] not in {"REJECT", "UNCERTAIN", "BLOCK", "PIT_AVAILABLE"} for r in results),
        "semantic_screen_abstention_rate": round(labels["UNCERTAIN"] / len(synthetic_screen), 4),
        "trace_check_passes": sum(r["trace_check"] for r in results),
        "mismatched_case_ids": [r["id"] for r in mismatches],
        "observed_counts": dict(sorted(labels.items())),
        "cases": results,
        "research_publication": "BLOCKED",
        "limitation": "Unseen-document performance and free-form Analyst financial-semantic correctness are NOT measured. Some REJECT-labelled synthetic narratives cannot be parsed by the current gate; UNCERTAIN is safe abstention but misses a contradiction.",
    }


def audit_real_document(path: Path) -> dict:
    """Development-only real-source smoke, NOT an independent semantic oracle."""
    from app.modules.financial_report_analyst import revenue_scope, management_evidence
    now = datetime(2026, 10, 22, tzinfo=ZoneInfo("Asia/Shanghai"))
    draft = revenue_scope.build_source_draft(revenue_scope.SOURCE, path, as_of=now)
    if (draft.get("status") != "SOURCE_DRAFT_READY" or len(draft.get("observations", [])) != 2
        or any(r.get("verdict") != "ADMIT" or r.get("rationale") != "LITERAL_CELL_AND_HEADING_SOURCE_CHECK_ONLY"
               for r in draft.get("reviews", []))):
        raise ValueError("REAL_PDF_LITERAL_REVIEW_FAILED")
    mgmt = management_evidence.locate_management_excerpt(path, as_of=now)
    if mgmt.get("status") != "SOURCE_PASSAGE_REVIEWED":
        raise ValueError("MANAGEMENT_SOURCE_LOCATION_FAILED")
    observations = draft["observations"]
    candidates = tuple(SourceValueCandidate(
        evidence_id=o["evidence_id"], document_id=draft["document_id"],
        canonical_sha256=draft["canonical_sha256"],
        statement_kind_candidate=o["statement_type_candidate"],
        row_label_verbatim=o["row_label"],
        column_header_verbatim=o["column_header"],
        value_verbatim=o["value_verbatim"], metric_identity_candidate=None,
    ) for o in observations)
    fact = screen_financial_association(
        SemanticClaimProposal(claim_id="REAL_FACT", claim_kind="OBSERVED_FACT",
            structure=AssertionStructure.SOURCE_OBSERVATION, values=(candidates[0],)),
        candidates,
    )
    bad = screen_financial_association(
        SemanticClaimProposal(claim_id="FALSE_PERIOD", claim_kind="OBSERVED_FACT",
            structure=AssertionStructure.PERIOD_COMPARISON, values=candidates,
            unreviewed_text="The two distinct statement scopes are consecutive periods."),
        candidates,
    )
    if (fact.verdict.value != "UNCERTAIN" or bad.verdict.value != "REJECT"
        or fact.research_publication != "BLOCKED" or bad.research_publication != "BLOCKED"
        or len({c.evidence_id for c in candidates} | {mgmt["evidence_id"]}) != 3):
        raise ValueError("REAL_DOCUMENT_DEFENSIVE_SCREEN_FAILED")
    try:
        revenue_scope.SOURCE.require_available(datetime(2026, 8, 20, 23, 59, tzinfo=ZoneInfo("Asia/Shanghai")))
    except ValueError as exc:
        if str(exc) != "PIT_UNAVAILABLE":
            raise
    else:
        raise ValueError("REAL_DOCUMENT_PIT_BLOCK_FAILED")
    return {
        "development_real_pdf_diagnostic": "PASS",
        "document_id": draft["document_id"],
        "source_sha256": draft["source_sha256"],
        "canonical_sha256": draft["canonical_sha256"],
        "pages": [o["page_number"] for o in observations] + [mgmt["source_page"]],
        "literal_source_observations": 3,
        "source_fact_screen": fact.verdict.value,
        "cross_scope_false_period_comparison": bad.verdict.value,
        "pit_prepublication": "BLOCK",
        "financial_semantic_qualification": "NOT_PERFORMED",
        "research_publication": "BLOCKED",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Read-only offline development evaluation; no model/network")
    parser.add_argument("--real-pdf", type=Path, help="local original hash-pinned Hengrui PDF for optional development audit")
    parser.add_argument("--output", type=Path, help="optional local report JSON (recommended outside repository)")
    args = parser.parse_args(argv)
    try:
        repo_root = Path(__file__).resolve().parents[2]
        actual_head = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
        baseline_commit = "68112420ff674225efffda8f06958fb826d82f80"
        ancestor = subprocess.run(
            ["git", "-C", str(repo_root), "merge-base", "--is-ancestor",
             baseline_commit, actual_head],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=False,
        )
        if ancestor.returncode != 0:
            raise ValueError("EVALUATOR_BASELINE_NOT_ANCESTOR")
        result = evaluate_synthetic()
        result["evaluated_runtime_head"] = actual_head
        result["evaluated_semantic_gate_sha256"] = sha256(
            (repo_root / "services/api/app/modules/financial_report_analyst/semantic_gate.py").read_bytes()
        ).hexdigest()
        if args.real_pdf is not None:
            result["real_document"] = audit_real_document(args.real_pdf)
        body = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        print(body, end="")
        if args.output:
            if args.output.exists():
                raise FileExistsError("EVALUATION_REPORT_ALREADY_EXISTS")
            args.output.write_text(body, encoding="utf-8")
        print("M19A_BASELINE_EVALUATION_PASS")
        return 0
    except (ValueError, OSError, KeyError, TypeError, IndexError, subprocess.CalledProcessError) as exc:
        print("STOP: OFFLINE_EVALUATION_FAILED", type(exc).__name__, str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
