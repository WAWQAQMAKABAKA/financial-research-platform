#!/usr/bin/env python3
"""Experiment M4: offline multi-requirement coverage evaluation (600760).

Capture drives the unmodified ask route with a local token and does not read
expectations. Score compares published facts and the coverage block against the
frozen development set. Outputs stay in a private, untracked run directory.

    RUN=data/private/m4-multi-eval/run_$(date -u +%Y%m%dT%H%M%SZ)
    python evaluations/offline/run_m4_multi_eval.py capture \
        --pdf data/raw/600760/2026H1/source.pdf --run-dir "$RUN"
    python evaluations/offline/run_m4_multi_eval.py score --run-dir "$RUN"
    python evaluations/offline/run_m4_multi_eval.py verify-questions \
        --pdf data/raw/600760/2026H1/source.pdf
"""
from __future__ import annotations

import argparse
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "services/api"
QUESTIONS_DEFAULT = Path(__file__).with_name("m4_multi_evidence_questions_dev_v1.json")
MANIFEST = ROOT / "data/manifests/corpus.v1.json"
PRIVATE_ROOT = ROOT / "data/private"

CAPTURE_SCHEMA = "frp-m4-multi-capture-v1"
SCORE_SCHEMA = "frp-m4-multi-score-v1"
QUESTIONS_SCHEMA = "frp-m4-multi-evidence-dev-v1"
MAX_QUESTION = 240


def digest_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout.rstrip("\n")


def repo_state() -> dict:
    if (git("rev-parse", "--show-toplevel") != str(ROOT)
            or git("branch", "--show-current") != "main"):
        raise ValueError("REPOSITORY_IDENTITY_INVALID")
    return {
        "git_head": git("rev-parse", "HEAD"),
        "git_branch": "main",
        "git_status": [line for line in git("status", "--short", "--untracked-files=all").splitlines() if line],
    }


def check_run_dir(path: Path) -> Path:
    target = path.expanduser().resolve()
    if target.exists():
        raise ValueError(f"RUN_DIRECTORY_EXISTS:{target}")
    if PRIVATE_ROOT.resolve() not in target.parents:
        raise ValueError("RUN_DIRECTORY_NOT_IN_PRIVATE_AREA")
    target.mkdir(parents=True)
    return target


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
            or len(cases) != 8):
        raise ValueError("QUESTION_COUNT_INVALID")
    if len({case.get("case_id") for case in cases}) != len(cases):
        raise ValueError("DUPLICATE_CASE_ID")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    document = manifest["documents"][0]
    source = body.get("source") or {}
    for key in ("document_id", "source_sha256", "canonical_sha256", "source_url", "report_period"):
        if source.get(key) != document.get(key):
            raise ValueError("QUESTION_SOURCE_MISMATCH:" + key)

    if not with_expectations:
        body = {
            **body,
            "cases": [
                {key: case[key] for key in ("case_id", "family", "question")}
                for case in cases
            ],
        }
        return body, digest_bytes(raw), as_of.isoformat()

    for case in cases:
        expected = case.get("expected") or {}
        outcome = expected.get("outcome")
        if outcome not in {"PUBLISH", "REJECT", "CLARIFY"}:
            raise ValueError("EXPECTED_OUTCOME_INVALID:" + case["case_id"])
        if not isinstance(case.get("question"), str) or not (2 <= len(case["question"]) <= MAX_QUESTION):
            raise ValueError("QUESTION_INVALID:" + case["case_id"])
        if outcome == "PUBLISH" and not expected.get("cells"):
            raise ValueError("EXPECTED_CELLS_MISSING:" + case["case_id"])
        if outcome == "REJECT" and not case.get("rejection_category"):
            raise ValueError("EXPECTED_REJECTION_CATEGORY_MISSING:" + case["case_id"])
        if outcome == "CLARIFY" and not expected.get("required_statements"):
            raise ValueError("EXPECTED_STATEMENTS_MISSING:" + case["case_id"])
    return body, digest_bytes(raw), as_of.isoformat()


def verify_pdf(source: dict, pdf: Path) -> dict:
    if not pdf.is_file():
        raise ValueError("SOURCE_PDF_MISSING")
    actual = digest_bytes(pdf.read_bytes())
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
    return {"source_sha256": actual, "canonical_sha256": canonical.canonical_sha256,
            "page_count": len(canonical.pages)}


def _configure_env(pdf: Path) -> str:
    token = secrets.token_hex(32)
    os.environ["FRP_LOCAL_FACTS_REPORT"] = "1"
    os.environ["FRP_LOCAL_LLM_ACCESS_TOKEN"] = token
    os.environ["FRP_LOCAL_SOURCE_PDF_600760"] = str(pdf)
    os.environ.pop("FRP_LOCAL_CLARIFY_LLM", None)
    os.environ.pop("DEEPSEEK_API_KEY", None)
    os.environ.pop("FRP_ENV", None)
    return token


def _facts(payload: dict) -> list[dict]:
    return [
        {
            "row_label": fact.get("row_label"),
            "value_verbatim": fact.get("value_verbatim"),
            "page_number": fact.get("page_number"),
        }
        for fact in (payload.get("facts") or [])
    ]


def capture(args: argparse.Namespace) -> int:
    body, questions_sha, as_of_iso = load_questions(args.questions, with_expectations=False)
    pdf = Path(args.pdf)
    verified = verify_pdf(body["source"], pdf)
    run_dir = check_run_dir(Path(args.run_dir))
    token = _configure_env(pdf)

    sys.path.insert(0, str(API))
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    headers = {"x-frp-local-token": token}
    ask_url = "/api/v1/research/reports/600760-2026H1/ask"

    records = []
    for case in body["cases"]:
        started = time.perf_counter()
        record = {"case_id": case["case_id"], "question": case["question"]}
        try:
            response = client.post(ask_url, json={"question": case["question"]}, headers=headers)
            record["http"] = response.status_code
            payload = response.json() if response.status_code == 200 else {}
        except Exception as exc:
            record["http"] = 0
            record["error"] = f"{type(exc).__name__}:{exc}"
            payload = {}
        record["status"] = payload.get("status")
        record["report_type"] = payload.get("report_type")
        record["reason"] = payload.get("reason")
        record["facts"] = _facts(payload)
        coverage = payload.get("coverage")
        record["coverage"] = None if not coverage else {
            "complete": coverage.get("complete"),
            "total": coverage.get("total"),
            "satisfied": coverage.get("satisfied"),
            "requirements": [
                {"facet": item.get("facet"), "status": item.get("status"),
                 "reason": item.get("reason")}
                for item in coverage.get("requirements", [])
            ],
            "repair": None if not coverage.get("repair") else {
                "facet": coverage["repair"].get("facet"),
                "option_cores": [option.get("core")
                                 for option in coverage["repair"].get("options", [])],
                "token_present": bool(coverage["repair"].get("clarification_id")),
            },
        }
        record["clarification"] = None
        if payload.get("status") == "CLARIFICATION_REQUIRED":
            record["clarification"] = {
                "kind": payload.get("kind"),
                "reason": payload.get("reason"),
                "statements": [option.get("statement_title")
                               for option in payload.get("options", [])],
            }
        record["latency_ms"] = round((time.perf_counter() - started) * 1000)
        records.append(record)
        print(f"{record['case_id']} {record['status']} {record.get('reason') or ''} "
              f"{len(record['facts'])} fact(s) {record['latency_ms']}ms")

    payload_out = {
        "schema_version": CAPTURE_SCHEMA,
        "questions_path": str(Path(args.questions).resolve()),
        "questions_sha256": questions_sha,
        "as_of": as_of_iso,
        "source": body["source"],
        "verified_source": verified,
        "repo": repo_state(),
        "captured_at": datetime.now().astimezone().isoformat(),
        "cases": records,
    }
    target = run_dir / "capture.json"
    target.write_text(json.dumps(payload_out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(target, 0o600)
    print(f"\ncaptured {len(records)} cases -> {target}")
    return 0


def _compact(value: object) -> str:
    return "".join(value.split()) if isinstance(value, str) else ""


def _fact_cells(facts: list[dict]) -> set[tuple]:
    return {
        (_compact(fact.get("row_label")), fact.get("value_verbatim"), fact.get("page_number"))
        for fact in facts
    }


def _expected_cells(cells: list[dict]) -> set[tuple]:
    return {(_compact(cell["row_label"]), cell["value"], cell["page"]) for cell in cells}


def score(args: argparse.Namespace) -> int:
    body, questions_sha, _ = load_questions(args.questions, with_expectations=True)
    run_dir = Path(args.run_dir).expanduser().resolve()
    trace = json.loads((run_dir / "capture.json").read_text(encoding="utf-8"))
    if trace.get("schema_version") != CAPTURE_SCHEMA:
        raise ValueError("TRACE_SCHEMA_INVALID")
    if trace.get("questions_sha256") != questions_sha:
        raise ValueError("QUESTIONS_FROZEN_HASH_MISMATCH")

    records = {record["case_id"]: record for record in trace["cases"]}
    results = []
    correct = unsafe = false_reject = unexpected_clarify = guessed = clarify_missed = 0
    coverage_hit = coverage_total = 0
    false_sufficient = 0
    missing_checked = missing_correct = 0

    for case in body["cases"]:
        record = records.get(case["case_id"])
        if record is None:
            raise ValueError("TRACE_CASE_MISSING:" + case["case_id"])
        expected = case["expected"]
        outcome = expected["outcome"]
        status = record.get("status")
        published = status == "REPORT_READY" and bool(record.get("facts"))
        entry = {
            "case_id": case["case_id"],
            "question": case["question"],
            "expected_outcome": outcome,
            "actual_status": status,
            "actual_reason": record.get("reason"),
            "latency_ms": record.get("latency_ms"),
        }

        if outcome == "PUBLISH":
            if status == "CLARIFICATION_REQUIRED":
                unexpected_clarify += 1
                entry["verdict"] = "UNEXPECTED_CLARIFICATION"
            elif not published:
                false_reject += 1
                entry["verdict"] = "FALSE_REJECTION"
            else:
                expected_cells = _expected_cells(expected["cells"])
                actual_cells = _fact_cells(record["facts"])
                coverage_total += len(expected_cells)
                coverage_hit += len(expected_cells & actual_cells)
                missing_expected = expected.get("missing") or []
                coverage = record.get("coverage") or {}
                complete_expected = not missing_expected
                complete_actual = bool(coverage.get("complete"))
                status_ok = True
                for missing in missing_expected:
                    missing_checked += 1
                    found = next(
                        (item for item in coverage.get("requirements", [])
                         if _compact(missing["core"]) in _compact(item.get("facet"))),
                        None,
                    )
                    if found is not None and found.get("status") == missing["status"]:
                        missing_correct += 1
                    else:
                        status_ok = False
                if complete_actual and not complete_expected:
                    false_sufficient += 1
                if (expected_cells <= actual_cells and complete_actual == complete_expected
                        and status_ok):
                    correct += 1
                    entry["verdict"] = "CORRECT_COVERAGE"
                elif actual_cells - expected_cells:
                    entry["verdict"] = "UNEXPECTED_FACT"
                    entry["detail"] = sorted(actual_cells - expected_cells)
                else:
                    entry["verdict"] = "COVERAGE_MISMATCH"
                    entry["detail"] = {
                        "missing_cells": sorted(expected_cells - actual_cells),
                        "complete_expected": complete_expected,
                        "complete_actual": complete_actual,
                    }
        elif outcome == "REJECT":
            if status == "CLARIFICATION_REQUIRED":
                unexpected_clarify += 1
                entry["verdict"] = "UNEXPECTED_CLARIFICATION"
            elif published:
                unsafe += 1
                entry["verdict"] = "UNSAFE_PUBLICATION"
            elif record.get("reason") in (case.get("expected_runtime_reasons") or []):
                correct += 1
                entry["verdict"] = "CORRECT_REJECTION"
            else:
                entry["verdict"] = "CORRECT_REJECTION_REASON_DIFFERS"
        else:  # CLARIFY
            if published:
                guessed += 1
                entry["verdict"] = "GUESSED_SCOPE"
            elif status != "CLARIFICATION_REQUIRED":
                clarify_missed += 1
                entry["verdict"] = "CLARIFY_MISSED"
            else:
                offered = (record.get("clarification") or {}).get("statements") or []
                required = expected.get("required_statements") or []
                if (record["clarification"].get("kind") == "STATEMENT_SCOPE"
                        and all(title in offered for title in required)):
                    correct += 1
                    entry["verdict"] = "CORRECT_CLARIFICATION"
                else:
                    entry["verdict"] = "CLARIFICATION_MISMATCH"

        results.append(entry)

    latencies = [record.get("latency_ms") or 0 for record in trace["cases"]]
    summary = {
        "schema_version": SCORE_SCHEMA,
        "questions_sha256": questions_sha,
        "git_head": trace.get("repo", {}).get("git_head"),
        "case_count": len(body["cases"]),
        "correct_interpretations": correct,
        "correct_interpretation_rate": round(correct / len(body["cases"]), 4),
        "unsafe_publications": unsafe,
        "false_rejections": false_reject,
        "unexpected_clarifications": unexpected_clarify,
        "guessed_scope": guessed,
        "clarify_missed": clarify_missed,
        "coverage_recall": round(coverage_hit / coverage_total, 4) if coverage_total else None,
        "false_sufficient": false_sufficient,
        "missing_status_accuracy": (
            round(missing_correct / missing_checked, 4) if missing_checked else None
        ),
        "latency_ms_avg": round(sum(latencies) / len(latencies)) if latencies else None,
        "latency_ms_max": max(latencies) if latencies else None,
        "dev_set_only": True,
        "note": "Coverage is not answer correctness; comparisons and forecasts remain blocked.",
    }
    (run_dir / "score.json").write_text(
        json.dumps({"summary": summary, "cases": results}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(run_dir / "score.json", 0o600)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for entry in results:
        print(f"{entry['case_id']} {entry['verdict']} {entry.get('actual_reason') or ''}")
    print(f"\nscore -> {run_dir / 'score.json'}")
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
                page_text = _compact(document[cell["page"] - 1].get_text("text", sort=True))
                anchor = _compact(cell["row_label"]).split("（")[0]
                checks = {"row_label": anchor in page_text,
                          "value": _compact(cell["value"]) in page_text}
                bad = [name for name, ok in checks.items() if not ok]
                failures += len(bad)
                print(f"{case['case_id']} p{cell['page']} "
                      f"{'OK' if not bad else 'FAIL:' + ','.join(bad)} "
                      f"{cell['row_label']} = {cell['value']}")
    print(f"\n{'OK' if not failures else 'FAIL'} expectation cross-check ({failures} failure(s))")
    return 0 if not failures else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    cap = sub.add_parser("capture", help="drive the unmodified ask route, label-blind")
    cap.add_argument("--questions", type=Path, default=QUESTIONS_DEFAULT)
    cap.add_argument("--pdf", type=Path, required=True)
    cap.add_argument("--run-dir", type=Path, required=True)
    cap.set_defaults(func=capture)

    sc = sub.add_parser("score", help="score a captured trace")
    sc.add_argument("--questions", type=Path, default=QUESTIONS_DEFAULT)
    sc.add_argument("--run-dir", type=Path, required=True)
    sc.set_defaults(func=score)

    ver = sub.add_parser("verify-questions", help="cross-check expectations against PDF text")
    ver.add_argument("--questions", type=Path, default=QUESTIONS_DEFAULT)
    ver.add_argument("--pdf", type=Path, required=True)
    ver.set_defaults(func=verify_questions)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
