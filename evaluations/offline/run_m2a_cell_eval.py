#!/usr/bin/env python3
"""M2a Track A: strictly offline cell-level evaluation for 600760 2026H1.

Two phases, deliberately separated:

    capture  question -> UNMODIFIED runtime builder -> trace (no expectations)
    score    frozen expectations + trace -> metrics (no runtime import)

`capture` never reads expected cells or verdicts. `score` never runs the
selector. Evaluation depends on runtime; runtime never imports evaluation.
Captured traces contain source values and stay in the user's private cache.

Usage:
    python evaluations/offline/run_m2a_cell_eval.py capture \
        --questions evaluations/offline/m2a_600760_questions_dev_v1.json \
        --pdf data/raw/600760/2026H1/source.pdf \
        --out ~/.cache/frp-m2a-eval/capture_v1.json   # or data/private/m2a-eval/capture_v1.json
    python evaluations/offline/run_m2a_cell_eval.py score \
        --questions evaluations/offline/m2a_600760_questions_dev_v1.json \
        --trace ~/.cache/frp-m2a-eval/capture_v1.json \
        --out ~/.cache/frp-m2a-eval/score_v1.json
    python evaluations/offline/run_m2a_cell_eval.py verify-questions \
        --questions evaluations/offline/m2a_600760_questions_dev_v1.json \
        --pdf data/raw/600760/2026H1/source.pdf
"""
from __future__ import annotations

import argparse
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "services/api"
QUESTIONS_DEFAULT = Path(__file__).with_name("m2a_600760_questions_dev_v1.json")
MANIFEST = ROOT / "data/manifests/corpus.v1.json"
CACHE_ROOT = Path.home() / ".cache"

CAPTURE_SCHEMA = "frp-m2a-cell-eval-capture-v1"
SCORE_SCHEMA = "frp-m2a-cell-eval-score-v1"
QUESTIONS_SCHEMA = "frp-m2a-600760-cell-eval-dev-v1"
MAX_QUESTION = 240

RUNTIME_FILES = (
    "services/api/app/modules/financial_report_analyst/report_builder.py",
    "services/api/app/modules/financial_report_analyst/question_selection.py",
    "services/api/app/modules/financial_report_analyst/publication_policy.py",
    "services/api/app/modules/financial_report_analyst/source_workspace.py",
)

# Runtime rejection reason -> financial-semantic category used by the scorecard.
REASON_CATEGORY = {
    "COMPARISON_NOT_PUBLISHABLE": "COMPARISON_NOT_PUBLISHABLE",
    "FORWARD_VIEW_NOT_PUBLISHABLE": "FORWARD_VIEW_NOT_PUBLISHABLE",
    "QUESTION_INTENT_AMBIGUOUS": "QUESTION_INTENT_AMBIGUOUS",
    "SOURCE_CELL_BLANK_NOT_ZERO": "NON_NUMERIC_CELL",
    "SOURCE_CELL_DASH_NOT_ZERO": "NON_NUMERIC_CELL",
    "OUT_OF_PERIOD_SCOPE": "PERIOD_OUT_OF_SCOPE",
    "AMBIGUOUS_STATEMENT_SCOPE": "STATEMENT_SCOPE_AMBIGUOUS",
    "NO_STATEMENT_SCOPE": "NO_SOURCE_ROW",
    "NO_ROW_MATCH": "NO_SOURCE_ROW",
    "TOO_MANY_ROW_MATCHES": "SELECTION_AMBIGUOUS",
    "COLUMN_HEADER_UNAVAILABLE": "NO_SOURCE_ROW",
}


def digest_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def digest_file(path: Path) -> str:
    return digest_bytes(Path(path).read_bytes())


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout.rstrip("\n")


def repo_state() -> dict:
    if (git("rev-parse", "--show-toplevel") != str(ROOT)
            or git("branch", "--show-current") != "main"):
        raise ValueError("REPOSITORY_IDENTITY_INVALID")
    status = [line for line in git("status", "--short", "--untracked-files=all").splitlines() if line]
    return {
        "git_head": git("rev-parse", "HEAD"),
        "git_branch": "main",
        "git_status": status,
        "runtime_sha256": {
            name: digest_file(ROOT / name) for name in RUNTIME_FILES
        },
    }


def check_output_path(path: Path) -> Path:
    """Captured traces contain source values: only private, untracked areas."""
    target = path.expanduser().resolve()
    if target.exists() or target.is_symlink():
        raise ValueError(
            f"PRIVATE_OUTPUT_ALREADY_EXISTS:{target}:use --run-dir for a new run"
        )
    cache = CACHE_ROOT.resolve()
    private = (ROOT / "data/private").resolve()
    if cache not in target.parents and private not in target.parents:
        raise ValueError("PRIVATE_OUTPUT_NOT_IN_PRIVATE_AREA")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def write_private(target: Path, payload: dict) -> None:
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def load_questions(path: Path, *, with_expectations: bool) -> tuple[dict, str, str]:
    raw = Path(path).read_bytes()
    body = json.loads(raw)
    if not isinstance(body, dict) or body.get("schema_version") != QUESTIONS_SCHEMA:
        raise ValueError("QUESTION_SCHEMA_INVALID")
    if body.get("corpus_type") != "AUTHOR_CURATED_DEVELOPMENT_NOT_INDEPENDENT_HOLDOUT":
        raise ValueError("QUESTION_CORPUS_TYPE_INVALID")
    if body.get("research_publication") != "BLOCKED":
        raise ValueError("QUESTION_PUBLICATION_MUST_BE_BLOCKED")
    as_of = datetime.fromisoformat(body["as_of"])
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("QUESTION_AS_OF_NAIVE")
    cases = body.get("cases")
    if (not isinstance(cases, list) or len(cases) != body.get("question_count")
            or len(cases) < 12 or len(cases) > 15):
        raise ValueError("QUESTION_COUNT_INVALID")
    ids = [case.get("case_id") for case in cases]
    if len(set(ids)) != len(ids):
        raise ValueError("DUPLICATE_CASE_ID")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    document = manifest["documents"][0]
    source = body.get("source") or {}
    for key in ("document_id", "source_sha256", "canonical_sha256",
                "source_url", "report_period"):
        if source.get(key) != document.get(key):
            raise ValueError("QUESTION_SOURCE_MISMATCH:" + key)

    if not with_expectations:
        # Enforce label blindness: the capture path never sees expectations.
        body = {
            **body,
            "cases": [
                {key: case[key] for key in ("case_id", "family", "question")}
                for case in cases
            ],
        }
        cases = body["cases"]

    if with_expectations:
        for case in cases:
            expected = case.get("expected") or {}
            outcome = expected.get("outcome")
            if outcome not in {"PUBLISH", "REJECT"}:
                raise ValueError("EXPECTED_OUTCOME_INVALID:" + case["case_id"])
            if outcome == "PUBLISH":
                if not expected.get("cells") or not expected.get("statement_kind"):
                    raise ValueError("EXPECTED_CELLS_MISSING:" + case["case_id"])
                for cell in expected["cells"]:
                    if (not isinstance(cell.get("page_number"), int)
                            or cell["page_number"] < 1
                            or not isinstance(cell.get("value"), str)
                            or not isinstance(cell.get("row_label"), str)):
                        raise ValueError("EXPECTED_CELL_INVALID:" + case["case_id"])
            else:
                if not case.get("rejection_category"):
                    raise ValueError("EXPECTED_REJECTION_CATEGORY_MISSING:" + case["case_id"])
            if not isinstance(case.get("question"), str) or not (
                    2 <= len(case["question"]) <= MAX_QUESTION):
                raise ValueError("QUESTION_INVALID:" + case["case_id"])

    return body, digest_bytes(raw), as_of.isoformat()


def verify_pdf(source: dict, pdf: Path) -> dict:
    if not pdf.is_file():
        raise ValueError("SOURCE_PDF_MISSING")
    actual = digest_file(pdf)
    if actual != source["source_sha256"]:
        raise ValueError("SOURCE_SHA_MISMATCH")
    sys.path.insert(0, str(API))
    from app.evidence.pdf_canonicalizer import canonicalize_pdf

    canonical = canonicalize_pdf(
        document_id=source["document_id"], pdf_path=pdf,
        expected_source_sha256=source["source_sha256"],
    )
    if canonical.canonical_sha256 != source["canonical_sha256"]:
        raise ValueError("CANONICAL_SHA_MISMATCH")
    if len(canonical.pages) != source["pdf_pages"]:
        raise ValueError("PAGE_COUNT_MISMATCH")
    return {"source_sha256": actual, "canonical_sha256": canonical.canonical_sha256,
            "page_count": len(canonical.pages)}


def capture_target(args: argparse.Namespace) -> Path:
    """A new run directory per run; never reuse an existing one."""
    if args.out is not None and args.run_dir is not None:
        raise ValueError("OUT_AND_RUN_DIR_ARE_MUTUALLY_EXCLUSIVE")
    if args.run_dir is not None:
        run_dir = Path(args.run_dir).expanduser().resolve()
        if run_dir.exists():
            raise ValueError(f"RUN_DIRECTORY_EXISTS:{run_dir}")
        return run_dir / "capture.json"
    if args.out is None:
        raise ValueError("OUTPUT_PATH_REQUIRED")
    return Path(args.out)


def score_targets(args: argparse.Namespace) -> tuple[Path, Path]:
    if args.run_dir is not None and (args.trace is not None or args.out is not None):
        raise ValueError("RUN_DIR_AND_EXPLICIT_PATHS_ARE_MUTUALLY_EXCLUSIVE")
    if args.run_dir is not None:
        run_dir = Path(args.run_dir).expanduser().resolve()
        if not run_dir.is_dir():
            raise ValueError(f"RUN_DIRECTORY_MISSING:{run_dir}")
        return run_dir / "capture.json", run_dir / "score.json"
    if args.trace is None or args.out is None:
        raise ValueError("TRACE_AND_OUTPUT_REQUIRED")
    return Path(args.trace), Path(args.out)


def capture(args: argparse.Namespace) -> int:
    body, questions_sha, as_of_iso = load_questions(args.questions, with_expectations=False)
    source = body["source"]
    target = check_output_path(capture_target(args))
    verified = verify_pdf(source, Path(args.pdf))

    sys.path.insert(0, str(API))
    from app.modules.financial_report_analyst.report_builder import (
        build_report_from_question,
    )

    as_of = datetime.fromisoformat(as_of_iso)
    state = repo_state()
    records = []
    for case in body["cases"]:
        started = time.perf_counter()
        record = {"case_id": case["case_id"], "question": case["question"]}
        try:
            report = build_report_from_question(
                body["source"]["report_key"], Path(args.pdf),
                case["question"], as_of=as_of,
            )
            record["status"] = report.get("status")
            record["reason"] = report.get("reason")
            record["publication"] = (report.get("publication") or {}).get("research_publication")
            record["facts"] = [
                {
                    "statement_type": fact.get("statement_type"),
                    "row_label": fact.get("row_label"),
                    "column_header": fact.get("column_header"),
                    "page_number": fact.get("page_number"),
                    "value_verbatim": fact.get("value_verbatim"),
                    "citation_page": (fact.get("citation") or {}).get("page_number"),
                }
                for fact in (report.get("facts") or [])
            ]
            selection = report.get("selection") or {}
            record["selection"] = {
                "status": selection.get("status"),
                "reason": selection.get("reason"),
                "statement_kind": selection.get("statement_kind"),
                "basis": (selection.get("trace") or {}).get("selection_basis"),
                "rows": selection.get("rows"),
            }
            record["retrieval_pages"] = [
                hit.get("page_number")
                for hit in ((report.get("retrieval") or {}).get("hits") or [])
            ]
        except Exception as exc:  # captured as a hard error, never as a pass
            record["status"] = "CAPTURE_ERROR"
            record["reason"] = f"{type(exc).__name__}:{exc}"
            record["publication"] = "BLOCKED"
            record["facts"] = []
            record["selection"] = None
            record["retrieval_pages"] = []
        record["latency_ms"] = round((time.perf_counter() - started) * 1000)
        records.append(record)
        print(f"{record['case_id']} {record['status']} {record.get('reason') or ''} "
              f"{len(record['facts'])} fact(s) {record['latency_ms']}ms")

    payload = {
        "schema_version": CAPTURE_SCHEMA,
        "questions_path": str(Path(args.questions).resolve()),
        "questions_sha256": questions_sha,
        "as_of": as_of_iso,
        "source": source,
        "verified_source": verified,
        "repo": state,
        "captured_at": datetime.now().astimezone().isoformat(),
        "cases": records,
    }
    write_private(target, payload)
    print(f"\ncaptured {len(records)} cases -> {target}")
    return 0


def expected_cells(case: dict) -> set[tuple]:
    expected = case["expected"]
    return {
        (
            expected.get("statement_kind"),
            _compact(cell["row_label"]),
            _compact(cell["column_header"]),
            cell["page_number"],
            cell["value"],
        )
        for cell in expected.get("cells", [])
    }


def actual_cells(record: dict) -> set[tuple]:
    return {
        (
            fact.get("statement_type"),
            _compact(fact.get("row_label")),
            _compact(fact.get("column_header")),
            fact.get("page_number"),
            fact.get("value_verbatim"),
        )
        for fact in record.get("facts", [])
    }


def _compact(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(value.split())


def score(args: argparse.Namespace) -> int:
    body, questions_sha, _ = load_questions(args.questions, with_expectations=True)
    trace_path, out_path = score_targets(args)
    trace = json.loads(Path(trace_path).read_text(encoding="utf-8"))
    if trace.get("schema_version") != CAPTURE_SCHEMA:
        raise ValueError("TRACE_SCHEMA_INVALID")
    if trace.get("questions_sha256") != questions_sha:
        raise ValueError("QUESTIONS_FROZEN_HASH_MISMATCH")
    target = check_output_path(out_path)

    records = {record["case_id"]: record for record in trace["cases"]}
    results = []
    unsafe = wrong_cell = exact = correct_rejection = false_rejection = 0
    rejections = reason_exact = reason_checked = 0
    category_hits = category_checked = 0
    citation_ok = 0
    published_facts = 0
    recall = {1: 0, 3: 0, 5: 0}
    recall_cases = 0

    for case in body["cases"]:
        record = records.get(case["case_id"])
        if record is None:
            raise ValueError("TRACE_CASE_MISSING:" + case["case_id"])
        expected = case["expected"]
        outcome = expected["outcome"]
        published = record.get("status") == "REPORT_READY" and bool(record.get("facts"))
        entry = {
            "case_id": case["case_id"],
            "question": case["question"],
            "expected_outcome": outcome,
            "actual_status": record.get("status"),
            "actual_reason": record.get("reason"),
            "expected_runtime_reasons": case.get("expected_runtime_reasons", []),
            "rejection_category": case.get("rejection_category"),
            "latency_ms": record.get("latency_ms"),
            "published": published,
        }

        if outcome == "REJECT":
            if published:
                unsafe += 1
                entry["verdict"] = "UNSAFE_PUBLICATION"
                entry["detail"] = [
                    f"{fact.get('row_label')}={fact.get('value_verbatim')}@p{fact.get('page_number')}"
                    for fact in record.get("facts", [])
                ]
            else:
                correct_rejection += 1
                rejections += 1
                reason = record.get("reason") or ""
                expected_reasons = case.get("expected_runtime_reasons") or []
                if expected_reasons:
                    reason_checked += 1
                    if reason in expected_reasons:
                        reason_exact += 1
                expected_category = case.get("rejection_category")
                actual_category = REASON_CATEGORY.get(reason)
                if expected_category:
                    category_checked += 1
                    category_hits += int(actual_category == expected_category)
                entry["actual_category"] = actual_category
                entry["category_match"] = (
                    None if not expected_category
                    else actual_category == expected_category
                )
                entry["verdict"] = (
                    "CORRECT_REJECTION"
                    if not expected_reasons or reason in expected_reasons
                    else "CORRECT_REJECTION_REASON_DIFFERS"
                )
        else:
            if not published:
                false_rejection += 1
                entry["verdict"] = "FALSE_REJECTION"
            else:
                expected_cell_set = expected_cells(case)
                actual_cell_set = actual_cells(record)
                published_facts += len(actual_cell_set)
                pages_match = all(
                    fact.get("citation_page") == fact.get("page_number")
                    for fact in record.get("facts", [])
                )
                citation_ok += int(pages_match)
                if expected_cell_set == actual_cell_set:
                    exact += 1
                    entry["verdict"] = "EXACT"
                else:
                    wrong_cell += 1
                    entry["verdict"] = "WRONG_CELL"
                    entry["detail"] = {
                        "expected": sorted(expected_cell_set),
                        "actual": sorted(actual_cell_set),
                    }
                basis = (record.get("selection") or {}).get("basis")
                if expected.get("selection_basis") and basis != expected["selection_basis"]:
                    entry["basis_mismatch"] = {
                        "expected": expected["selection_basis"], "actual": basis,
                    }
            expected_page = expected["cells"][0]["page_number"] if expected.get("cells") else None
            pages = record.get("retrieval_pages") or []
            if expected_page is not None and pages:
                recall_cases += 1
                for k in recall:
                    if expected_page in pages[:k]:
                        recall[k] += 1
        results.append(entry)

    publish_expected = sum(1 for c in body["cases"] if c["expected"]["outcome"] == "PUBLISH")
    reject_expected = len(body["cases"]) - publish_expected
    latencies = [case.get("latency_ms") or 0 for case in trace["cases"]]
    summary = {
        "schema_version": SCORE_SCHEMA,
        "questions_sha256": questions_sha,
        "git_head": trace.get("repo", {}).get("git_head"),
        "case_count": len(body["cases"]),
        "publish_expected": publish_expected,
        "reject_expected": reject_expected,
        "unsafe_publications": unsafe,
        "wrong_cell_publications": wrong_cell,
        "exact_cell_matches": exact,
        "cell_exact_match_rate": round(exact / publish_expected, 4) if publish_expected else None,
        "correct_rejections": correct_rejection,
        "correct_rejection_rate": round(correct_rejection / reject_expected, 4) if reject_expected else None,
        "false_rejections": false_rejection,
        "false_rejection_rate": round(false_rejection / publish_expected, 4) if publish_expected else None,
        "exact_reason_accuracy": round(reason_exact / reason_checked, 4) if reason_checked else None,
        "reason_checked_cases": reason_checked,
        "rejection_category_accuracy": round(category_hits / category_checked, 4) if category_checked else None,
        "category_checked_cases": category_checked,
        "citation_page_accuracy": round(citation_ok / (exact + wrong_cell), 4) if (exact + wrong_cell) else None,
        "retrieval_page_recall": {
            f"@{k}": (round(recall[k] / recall_cases, 4) if recall_cases else None)
            for k in recall
        },
        "latency_ms_avg": round(sum(latencies) / len(latencies)) if latencies else None,
        "latency_ms_max": max(latencies) if latencies else None,
        "published_fact_count": published_facts,
        "dev_set_only": True,
        "note": "Zero unsafe publication is a gate on this development set only, not a general error rate.",
    }

    write_private(target, {"summary": summary, "cases": results})
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for entry in results:
        print(f"{entry['case_id']} {entry['verdict']} "
              f"{entry.get('actual_reason') or ''}")
    print(f"\nscore -> {target}")
    return 0


def verify_questions(args: argparse.Namespace) -> int:
    body, questions_sha, _ = load_questions(args.questions, with_expectations=True)
    source = body["source"]
    verified = verify_pdf(source, Path(args.pdf))
    print(f"source {source['document_id']} sha256={verified['source_sha256'][:16]}… "
          f"canonical={verified['canonical_sha256'][:16]}… pages={verified['page_count']}")
    print(f"questions sha256={questions_sha}")

    import pymupdf

    failures = 0
    with pymupdf.open(Path(args.pdf)) as document:
        for case in body["cases"]:
            expected = case["expected"]
            if expected["outcome"] != "PUBLISH":
                continue
            for cell in expected["cells"]:
                page_text = _compact(document[cell["page_number"] - 1].get_text("text", sort=True))
                # Multi-line labels interleave table columns, so only the
                # anchor before any annotation can be checked as contiguous.
                anchor = _compact(cell["row_label"]).split("（")[0]
                checks = {
                    "row_label": anchor in page_text,
                    "value": _compact(cell["value"]) in page_text,
                }
                bad = [name for name, ok in checks.items() if not ok]
                failures += len(bad)
                print(f"{case['case_id']} p{cell['page_number']} "
                      f"{'OK' if not bad else 'FAIL:' + ','.join(bad)} "
                      f"{cell['row_label']} = {cell['value']}")
    print(f"\n{'OK' if not failures else 'FAIL'} expectation cross-check ({failures} failure(s))")
    return 0 if not failures else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    cap = sub.add_parser("capture", help="label-blind capture via the unmodified runtime")
    cap.add_argument("--questions", type=Path, default=QUESTIONS_DEFAULT)
    cap.add_argument("--pdf", type=Path, required=True)
    cap.add_argument("--run-dir", type=Path, help="new directory for this run (recommended)")
    cap.add_argument("--out", type=Path, help="explicit trace path (must not exist)")
    cap.set_defaults(func=capture)

    sc = sub.add_parser("score", help="score a captured trace against frozen expectations")
    sc.add_argument("--questions", type=Path, default=QUESTIONS_DEFAULT)
    sc.add_argument("--run-dir", type=Path, help="directory written by capture")
    sc.add_argument("--trace", type=Path, help="explicit capture path")
    sc.add_argument("--out", type=Path, help="explicit score path (must not exist)")
    sc.set_defaults(func=score)

    ver = sub.add_parser("verify-questions", help="cross-check expectations against PDF text")
    ver.add_argument("--questions", type=Path, default=QUESTIONS_DEFAULT)
    ver.add_argument("--pdf", type=Path, required=True)
    ver.set_defaults(func=verify_questions)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
