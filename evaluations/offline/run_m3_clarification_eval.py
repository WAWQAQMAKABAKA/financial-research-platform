#!/usr/bin/env python3
"""Experiment A: offline clarification evaluation for 600760 2026H1.

Capture drives the *unmodified* FastAPI routes (ask + resolve) with a local
token; it never reads expected outcomes. Score reads the frozen expectations and
computes interpretation, clarification and binding metrics. Outputs stay in a
private, untracked run directory.

Usage:
    RUN=data/private/m3-clarification-eval/run_$(date -u +%Y%m%dT%H%M%SZ)
    python evaluations/offline/run_m3_clarification_eval.py capture \
        --pdf data/raw/600760/2026H1/source.pdf --run-dir "$RUN"
    python evaluations/offline/run_m3_clarification_eval.py score --run-dir "$RUN"
    python evaluations/offline/run_m3_clarification_eval.py verify-questions \
        --pdf data/raw/600760/2026H1/source.pdf
"""
from __future__ import annotations

import argparse
import base64
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
QUESTIONS_DEFAULT = Path(__file__).with_name("m3_clarification_questions_dev_v1.json")
MANIFEST = ROOT / "data/manifests/corpus.v1.json"
CACHE_ROOT = Path.home() / ".cache"
PRIVATE_ROOT = ROOT / "data/private"

CAPTURE_SCHEMA = "frp-m3-clarification-capture-v1"
SCORE_SCHEMA = "frp-m3-clarification-score-v1"
QUESTIONS_SCHEMA = "frp-m3-clarification-dev-v1"
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
            or len(cases) != 12):
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
        if outcome == "CLARIFY" and not expected.get("required_option_cores"):
            raise ValueError("EXPECTED_OPTION_CORES_MISSING:" + case["case_id"])
        if outcome == "REJECT" and not case.get("rejection_category"):
            raise ValueError("EXPECTED_REJECTION_CATEGORY_MISSING:" + case["case_id"])
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
            "column_header": fact.get("column_header"),
            "page_number": fact.get("page_number"),
            "value_verbatim": fact.get("value_verbatim"),
            "statement_type": fact.get("statement_type"),
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
    resolve_url = "/api/v1/research/reports/600760-2026H1/ask/resolve"

    records = []
    for case in body["cases"]:
        started = time.perf_counter()
        record = {"case_id": case["case_id"], "question": case["question"]}
        try:
            response = client.post(ask_url, json={"question": case["question"]}, headers=headers)
            record["ask_http"] = response.status_code
            payload = response.json() if response.status_code == 200 else {}
        except Exception as exc:
            record["ask_http"] = 0
            record["ask_error"] = f"{type(exc).__name__}:{exc}"
            payload = {}
        record["status"] = payload.get("status")
        record["reason"] = payload.get("reason")
        record["facts"] = _facts(payload)
        record["intent"] = (payload.get("intent") or {}).get("value")
        record["clarification"] = None
        record["resolutions"] = {}

        if payload.get("status") == "CLARIFICATION_REQUIRED":
            options = payload.get("options") or []
            record["clarification"] = {
                "reason": payload.get("reason"),
                "option_basis": payload.get("option_basis"),
                "options": [
                    {
                        "option_id": option.get("option_id"),
                        "core": option.get("core"),
                        "row_label": option.get("row_label"),
                        "statement_title": option.get("statement_title"),
                    }
                    for option in options
                ],
                "interpretation_status": (payload.get("interpretation") or {}).get("status"),
                "research_publication": payload.get("research_publication"),
            }
            for option in options[:4]:
                try:
                    resolved = client.post(
                        resolve_url,
                        json={
                            "question": case["question"],
                            "clarification_id": payload["clarification_id"],
                            "option_id": option["option_id"],
                        },
                        headers=headers,
                    )
                    data = resolved.json() if resolved.status_code == 200 else {}
                except Exception as exc:
                    resolved = None
                    data = {"status": "RESOLVE_ERROR", "reason": f"{type(exc).__name__}:{exc}"}
                record["resolutions"][option["option_id"]] = {
                    "core": option.get("core"),
                    "http": getattr(resolved, "status_code", 0),
                    "status": data.get("status"),
                    "reason": data.get("reason"),
                    "facts": _facts(data),
                }
        record["latency_ms"] = round((time.perf_counter() - started) * 1000)
        records.append(record)
        print(f"{record['case_id']} {record['status']} {record.get('reason') or ''} "
              f"{len(record['facts'])} fact(s) {len(record['resolutions'])} resolution(s) "
              f"{record['latency_ms']}ms")

    capture_payload = {
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
    target.write_text(json.dumps(capture_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(target, 0o600)
    print(f"\ncaptured {len(records)} cases -> {target}")
    return 0


def _compact(value: object) -> str:
    return "".join(value.split()) if isinstance(value, str) else ""


def _cells(facts: list[dict]) -> set[tuple]:
    return {
        (_compact(fact.get("row_label")), _compact(fact.get("column_header")),
         fact.get("page_number"), fact.get("value_verbatim"))
        for fact in facts
    }


def _expected_cells(cells: list[dict]) -> set[tuple]:
    return {
        (_compact(cell["row_label"]), _compact(cell.get("column_header")),
         cell["page_number"], cell["value"])
        for cell in cells
    }


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
    correct = unsafe = unnecessary_clarify = guessed = false_reject = 0
    clarify_missed = unexpected_clarify = 0
    option_required = option_found = 0
    resolution_expected = resolution_correct = 0
    binding_checked = binding_correct = 0

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
                unnecessary_clarify += 1
                entry["verdict"] = "UNNECESSARY_CLARIFICATION"
            elif not published:
                false_reject += 1
                entry["verdict"] = "FALSE_REJECTION"
            else:
                expected_set = _expected_cells(expected["cells"])
                actual_set = _cells(record["facts"])
                if expected_set == actual_set:
                    correct += 1
                    entry["verdict"] = "CORRECT_PUBLISH"
                else:
                    entry["verdict"] = "WRONG_CELL"
                    entry["detail"] = {"expected": sorted(expected_set), "actual": sorted(actual_set)}
        elif outcome == "REJECT":
            if status == "CLARIFICATION_REQUIRED":
                unexpected_clarify += 1
                entry["verdict"] = "UNEXPECTED_CLARIFICATION"
            elif published:
                unsafe += 1
                entry["verdict"] = "UNSAFE_PUBLICATION"
            else:
                expected_reasons = case.get("expected_runtime_reasons") or []
                if expected_reasons and record.get("reason") not in expected_reasons:
                    entry["verdict"] = "CORRECT_REJECTION_REASON_DIFFERS"
                else:
                    correct += 1
                    entry["verdict"] = "CORRECT_REJECTION"
        else:  # CLARIFY
            if published:
                guessed += 1
                entry["verdict"] = "GUESSED_WHEN_SHOULD_CLARIFY"
            elif status != "CLARIFICATION_REQUIRED":
                clarify_missed += 1
                entry["verdict"] = "CLARIFY_MISSED_REJECTED"
            else:
                options = record["clarification"]["options"]
                cores = {option["core"] for option in options}
                required = expected["required_option_cores"]
                option_required += len(required)
                found = [core for core in required if core in cores]
                option_found += len(found)
                if len(found) == len(required):
                    correct += 1
                    entry["verdict"] = "CORRECT_CLARIFICATION"
                else:
                    entry["verdict"] = "MISSING_EXPECTED_OPTION"
                entry["options"] = sorted(cores)

                resolutions = expected.get("resolutions") or {}
                for core, expected_cell in resolutions.items():
                    option = next((o for o in options if o["core"] == core), None)
                    if option is None:
                        continue
                    resolution_expected += 1
                    resolved = record["resolutions"].get(option["option_id"]) or {}
                    facts = resolved.get("facts") or []
                    expected_page = expected_cell.get(
                        "page_number", expected_cell.get("page"))
                    matched = any(
                        _compact(fact.get("row_label")) == _compact(expected_cell["row_label"])
                        and fact.get("page_number") == expected_page
                        and fact.get("value_verbatim") == expected_cell["value"]
                        and (expected_cell.get("column_header") is None
                             or _compact(fact.get("column_header"))
                             == _compact(expected_cell["column_header"]))
                        for fact in facts
                    )
                    if resolved.get("status") == "REPORT_READY" and matched:
                        resolution_correct += 1
                    else:
                        entry.setdefault("resolution_failures", {})[core] = {
                            "status": resolved.get("status"),
                            "reason": resolved.get("reason"),
                        }

                for option in options:
                    resolved = record["resolutions"].get(option["option_id"]) or {}
                    if resolved.get("status") != "REPORT_READY":
                        continue
                    binding_checked += 1
                    rows = {_compact(fact.get("row_label")) for fact in resolved.get("facts") or []}
                    if rows == {_compact(option["row_label"])}:
                        binding_correct += 1
                    else:
                        entry.setdefault("binding_failures", []).append(option["core"])

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
        "unnecessary_clarifications": unnecessary_clarify,
        "unnecessary_clarification_rate": round(unnecessary_clarify / len(body["cases"]), 4),
        "guessed_when_should_clarify": guessed,
        "clarify_missed_rejected": clarify_missed,
        "false_rejections": false_reject,
        "unexpected_clarifications": unexpected_clarify,
        "clarification_option_recall": (
            round(option_found / option_required, 4) if option_required else None
        ),
        "resolution_correct_rate": (
            round(resolution_correct / resolution_expected, 4)
            if resolution_expected else None
        ),
        "resolution_expected": resolution_expected,
        "option_binding_accuracy": (
            round(binding_correct / binding_checked, 4) if binding_checked else None
        ),
        "option_binding_checked": binding_checked,
        "latency_ms_avg": round(sum(latencies) / len(latencies)) if latencies else None,
        "latency_ms_max": max(latencies) if latencies else None,
        "dev_set_only": True,
        "note": "Unsafe publication must be 0 on this development set only; not a general error rate.",
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
                page_text = _compact(document[cell["page_number"] - 1].get_text("text", sort=True))
                anchor = _compact(cell["row_label"]).split("（")[0]
                checks = {"row_label": anchor in page_text,
                          "value": _compact(cell["value"]) in page_text}
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

    cap = sub.add_parser("capture", help="drive the unmodified routes, label-blind")
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
