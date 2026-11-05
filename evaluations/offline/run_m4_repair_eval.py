#!/usr/bin/env python3
"""Experiment R: offline bounded-repair evaluation for 600760.

Capture drives the unmodified ask/resolve routes. For a partial report with a
repair suggestion it resolves every offered candidate (cap 3) and records the
result. Score checks candidate recall/order, confirmation success, and that a
missing facet without candidates stays a clean partial report.

    RUN=data/private/m4-repair-eval/run_$(date -u +%Y%m%dT%H%M%SZ)
    python evaluations/offline/run_m4_repair_eval.py capture \
        --pdf data/raw/600760/2026H1/source.pdf --run-dir "$RUN"
    python evaluations/offline/run_m4_repair_eval.py score --run-dir "$RUN"
    python evaluations/offline/run_m4_repair_eval.py verify-questions \
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
QUESTIONS_DEFAULT = Path(__file__).with_name("m4_repair_questions_dev_v1.json")
MANIFEST = ROOT / "data/manifests/corpus.v1.json"
PRIVATE_ROOT = ROOT / "data/private"

CAPTURE_SCHEMA = "frp-m4-repair-capture-v1"
SCORE_SCHEMA = "frp-m4-repair-score-v1"
QUESTIONS_SCHEMA = "frp-m4-repair-dev-v1"
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
            or len(cases) != 6):
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
        if outcome not in {"REPAIR", "PARTIAL", "COMPLETE"}:
            raise ValueError("EXPECTED_OUTCOME_INVALID:" + case["case_id"])
        if not isinstance(case.get("question"), str) or not (2 <= len(case["question"]) <= MAX_QUESTION):
            raise ValueError("QUESTION_INVALID:" + case["case_id"])
        if outcome == "REPAIR" and not expected.get("target_core"):
            raise ValueError("EXPECTED_TARGET_MISSING:" + case["case_id"])
        if outcome == "COMPLETE" and not expected.get("cells"):
            raise ValueError("EXPECTED_CELLS_MISSING:" + case["case_id"])
        if outcome == "PARTIAL" and not expected.get("missing_core"):
            raise ValueError("EXPECTED_MISSING_CORE:" + case["case_id"])
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


def _coverage(payload: dict) -> dict | None:
    coverage = payload.get("coverage")
    if not coverage:
        return None
    return {
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
            "token": coverage["repair"].get("clarification_id"),
            "options": [
                {"option_id": option.get("option_id"),
                 "core": option.get("core"),
                 "row_label": option.get("row_label")}
                for option in coverage["repair"].get("options", [])
            ],
        },
    }


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
    resolve_url = "/api/v1/research/reports/600760-2026H1/ask/resolve"

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
        record["coverage"] = _coverage(payload)
        record["resolutions"] = {}

        repair = (record["coverage"] or {}).get("repair")
        if repair and repair.get("token"):
            for option in repair["options"][:3]:
                try:
                    resolved = client.post(
                        resolve_url,
                        json={
                            "question": case["question"],
                            "clarification_id": repair["token"],
                            "option_id": option["option_id"],
                        },
                        headers=headers,
                    )
                    data = resolved.json() if resolved.status_code == 200 else {}
                    http = resolved.status_code
                except Exception as exc:
                    data = {"status": "RESOLVE_ERROR", "reason": f"{type(exc).__name__}:{exc}"}
                    http = 0
                record["resolutions"][option["option_id"]] = {
                    "core": option["core"],
                    "http": http,
                    "status": data.get("status"),
                    "reason": data.get("reason"),
                    "facts": _facts(data),
                    "coverage": _coverage(data),
                }
        record["latency_ms"] = round((time.perf_counter() - started) * 1000)
        records.append(record)
        print(f"{record['case_id']} {record['status']} {record.get('reason') or ''} "
              f"{len(record['facts'])} fact(s) repairs={len(record['resolutions'])} "
              f"{record['latency_ms']}ms")

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
        (_compact(fact.get("row_label")), fact.get("value_verbatim"),
         fact.get("page_number"))
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
    repair_cases = repair_offered = target_present = top1_hit = confirmed = 0
    no_candidate_correct = complete_control = false_repair = 0
    unsafe = 0
    latency = []

    for case in body["cases"]:
        record = records.get(case["case_id"])
        if record is None:
            raise ValueError("TRACE_CASE_MISSING:" + case["case_id"])
        expected = case["expected"]
        outcome = expected["outcome"]
        entry = {
            "case_id": case["case_id"],
            "question": case["question"],
            "expected_outcome": outcome,
            "actual_status": record.get("status"),
            "latency_ms": record.get("latency_ms"),
        }
        latency.append(record.get("latency_ms") or 0)
        coverage = record.get("coverage") or {}
        repair = coverage.get("repair")

        if outcome == "REPAIR":
            repair_cases += 1
            cores = [option["core"] for option in (repair or {}).get("options", [])]
            if not repair:
                entry["verdict"] = "REPAIR_NOT_OFFERED"
            else:
                repair_offered += 1
                if expected["target_core"] in cores:
                    target_present += 1
                if cores and cores[0] == expected["target_core"]:
                    top1_hit += 1
                target_option = next(
                    (option for option in repair["options"]
                     if option["core"] == expected["target_core"]),
                    None,
                )
                resolution = (record.get("resolutions") or {}).get(
                    (target_option or {}).get("option_id", "")
                )
                resolved_cells = _fact_cells((resolution or {}).get("facts") or [])
                base_cells = _fact_cells(record.get("facts") or [])
                expected_cells = _expected_cells([{
                    "row_label": expected["target_core"],
                    "value": expected["target_value"],
                    "page": expected["target_page"],
                }])
                matched = any(
                    value == expected["target_value"]
                    and page == expected["target_page"]
                    for _, value, page in resolved_cells
                )
                complete = bool(((resolution or {}).get("coverage") or {}).get("complete"))
                if (resolution or {}).get("status") == "REPORT_READY" and matched and complete:
                    confirmed += 1
                    entry["verdict"] = "REPAIR_CONFIRMED"
                else:
                    entry["verdict"] = "REPAIR_CONFIRMATION_FAILED"
                extra = resolved_cells - (base_cells | expected_cells)
                if extra:
                    unsafe += 1
                    entry["unexpected_facts"] = sorted(extra)
        elif outcome == "PARTIAL":
            if repair:
                false_repair += 1
                entry["verdict"] = "UNEXPECTED_REPAIR_OFFERED"
            elif (record.get("status") == "REPORT_READY"
                  and coverage.get("complete") is False):
                missing = [item for item in coverage.get("requirements", [])
                           if item["status"] != "VERIFIED"]
                if missing and _compact(expected["missing_core"]) in _compact(
                    missing[0]["facet"]
                ):
                    no_candidate_correct += 1
                    entry["verdict"] = "CORRECT_PARTIAL"
                else:
                    entry["verdict"] = "PARTIAL_MISMATCH"
            else:
                entry["verdict"] = "PARTIAL_MISMATCH"
        else:  # COMPLETE
            if repair:
                false_repair += 1
                entry["verdict"] = "UNEXPECTED_REPAIR_OFFERED"
            elif (record.get("status") == "REPORT_READY"
                  and coverage.get("complete") is True):
                expected_cells = _expected_cells(expected["cells"])
                actual_cells = _fact_cells(record.get("facts") or [])
                if expected_cells <= actual_cells and not (actual_cells - expected_cells):
                    complete_control += 1
                    entry["verdict"] = "CORRECT_COMPLETE"
                else:
                    entry["verdict"] = "COMPLETE_CELL_MISMATCH"
            else:
                entry["verdict"] = "COMPLETE_MISMATCH"

        results.append(entry)

    summary = {
        "schema_version": SCORE_SCHEMA,
        "questions_sha256": questions_sha,
        "git_head": trace.get("repo", {}).get("git_head"),
        "case_count": len(body["cases"]),
        "repair_cases": repair_cases,
        "repair_offered": repair_offered,
        "candidate_target_present": target_present,
        "candidate_recall": (
            round(target_present / repair_cases, 4) if repair_cases else None
        ),
        "candidate_top1_hit": top1_hit,
        "confirmation_success": confirmed,
        "confirmation_rate": (
            round(confirmed / repair_cases, 4) if repair_cases else None
        ),
        "correct_partial_no_candidate": no_candidate_correct,
        "correct_complete_control": complete_control,
        "unexpected_repair_offers": false_repair,
        "unsafe_publications": unsafe,
        "latency_ms_avg": round(sum(latency) / len(latency)) if latency else None,
        "latency_ms_max": max(latency) if latency else None,
        "dev_set_only": True,
        "note": "Repair candidates are lexical near-matches confirmed by the user; not semantic equivalence.",
    }
    (run_dir / "score.json").write_text(
        json.dumps({"summary": summary, "cases": results}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(run_dir / "score.json", 0o600)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for entry in results:
        print(f"{entry['case_id']} {entry['verdict']}")
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
            if expected["outcome"] == "COMPLETE":
                cells = expected["cells"]
            elif expected["outcome"] == "REPAIR":
                cells = [{"row_label": expected["target_core"],
                          "value": expected["target_value"],
                          "page": expected["target_page"]}]
            else:
                continue
            for cell in cells:
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

    cap = sub.add_parser("capture", help="drive the unmodified ask/resolve routes")
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
