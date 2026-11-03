"""Offline tests for the M4 coverage scorer. No PDF, no runtime."""
from pathlib import Path
import json

import pytest

import run_m4_multi_eval as ev

AS_OF = "2026-11-03T00:00:00+08:00"
SOURCE = {
    "ticker": "600760", "issuer": "中航沈飞", "report_key": "600760-2026H1",
    "document_id": "600760-2026H1-cninfo-1225517994", "report_period": "2026H1",
    "published_on": "2026-08-28", "source_url": "https://example.test/r.pdf",
    "source_sha256": "a" * 64, "canonical_sha256": "b" * 64, "pdf_pages": 207,
}


def cell(row, value, page):
    return {"row_label": row, "value": value, "page": page}


def case(i, outcome, *, cells=(), missing=(), statements=()):
    if outcome == "PUBLISH":
        expected = {"outcome": "PUBLISH", "cells": list(cells), "missing": list(missing)}
    elif outcome == "REJECT":
        expected = {"outcome": "REJECT", "cells": [], "missing": []}
    else:
        expected = {"outcome": "CLARIFY", "cells": [], "missing": [],
                    "required_statements": list(statements)}
    return {
        "case_id": f"T-{i}", "family": "multi", "question": f"问题{i}是多少？",
        "expected": expected,
        "rejection_category": "COMPARISON_NOT_PUBLISHABLE" if outcome == "REJECT" else None,
        "expected_runtime_reasons": ["COMPARISON_NOT_PUBLISHABLE"] if outcome == "REJECT" else [],
    }


def question_set():
    cases = [
        case(1, "PUBLISH", cells=[cell("营业收入", "6,191,107,217.36", 46),
                                  cell("净利润", "468,144,459.10", 47)]),
        case(2, "PUBLISH", cells=[cell("营业成本", "5,535,215,299.31", 46)]),
        case(3, "PUBLISH", cells=[cell("营业收入", "6,191,107,217.36", 46)],
             missing=[{"core": "研发投入", "status": "NO_ROW_MATCH"}]),
        case(4, "PUBLISH", cells=[cell("营业收入", "6,191,107,217.36", 46),
                                  cell("少数股东损益", "-4,921,404.14", 47)]),
        case(5, "PUBLISH", cells=[cell("营业总收入", "6,191,107,217.36", 46),
                                  cell("营业收入", "6,191,107,217.36", 46)]),
        case(6, "REJECT"), case(7, "REJECT"),
        case(8, "CLARIFY", statements=["合并利润表", "母公司利润表"]),
    ]
    return {
        "schema_version": ev.QUESTIONS_SCHEMA,
        "corpus_type": "AUTHOR_CURATED_DEVELOPMENT_NOT_INDEPENDENT_HOLDOUT",
        "scope": "600760_2026H1_MULTI_REQUIREMENT",
        "as_of": AS_OF, "question_count": len(cases),
        "source": SOURCE, "cases": cases, "research_publication": "BLOCKED",
    }


def fact(row, value, page):
    return {"row_label": row, "value_verbatim": value, "page_number": page}


def record(case_id, status, *, reason=None, facts=None, coverage=None, clarification=None):
    return {
        "case_id": case_id, "status": status, "reason": reason,
        "facts": facts or [], "coverage": coverage, "clarification": clarification,
        "latency_ms": 1000,
    }


def coverage(complete, requirements):
    return {
        "complete": complete, "total": len(requirements),
        "satisfied": sum(1 for item in requirements if item["status"] == "VERIFIED"),
        "requirements": requirements,
    }


def full_trace():
    return {
        "schema_version": ev.CAPTURE_SCHEMA, "questions_sha256": "x" * 64,
        "repo": {"git_head": "0" * 40},
        "cases": [
            record("T-1", "REPORT_READY",
                   facts=[fact("营业收入", "6,191,107,217.36", 46),
                          fact("净利润", "468,144,459.10", 47)],
                   coverage=coverage(True, [{"facet": "营业收入", "status": "VERIFIED"},
                                            {"facet": "净利润", "status": "VERIFIED"}])),
            record("T-2", "REPORT_READY",
                   facts=[fact("营业成本", "5,535,215,299.31", 46)],
                   coverage=coverage(True, [{"facet": "营业成本", "status": "VERIFIED"}])),
            record("T-3", "REPORT_READY",
                   facts=[fact("营业收入", "6,191,107,217.36", 46)],
                   coverage=coverage(False, [{"facet": "营业收入", "status": "VERIFIED"},
                                             {"facet": "研发投入", "status": "NO_ROW_MATCH"}])),
            record("T-4", "REPORT_READY",
                   facts=[fact("营业收入", "6,191,107,217.36", 46),
                          fact("少数股东损益", "-4,921,404.14", 47)],
                   coverage=coverage(True, [{"facet": "营业收入", "status": "VERIFIED"},
                                            {"facet": "少数股东损益", "status": "VERIFIED"}])),
            record("T-5", "REPORT_READY",
                   facts=[fact("营业总收入", "6,191,107,217.36", 46),
                          fact("营业收入", "6,191,107,217.36", 46)],
                   coverage=coverage(True, [{"facet": "营业总收入", "status": "VERIFIED"},
                                            {"facet": "营业收入", "status": "VERIFIED"}])),
            record("T-6", "REPORT_WITHHELD", reason="COMPARISON_NOT_PUBLISHABLE"),
            record("T-7", "REPORT_WITHHELD", reason="COMPARISON_NOT_PUBLISHABLE"),
            record("T-8", "CLARIFICATION_REQUIRED", reason="STATEMENT_SCOPE_AMBIGUOUS",
                   clarification={"kind": "STATEMENT_SCOPE",
                                  "statements": ["合并利润表", "母公司利润表"]}),
        ],
    }


@pytest.fixture
def harness(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"documents": [{
        "document_id": SOURCE["document_id"], "source_sha256": SOURCE["source_sha256"],
        "canonical_sha256": SOURCE["canonical_sha256"], "source_url": SOURCE["source_url"],
        "report_period": SOURCE["report_period"], "ticker": "600760",
        "issuer_name": "中航沈飞", "published_on": "2026-08-28", "page_count": 207,
    }]}), encoding="utf-8")
    monkeypatch.setattr(ev, "MANIFEST", manifest)
    path = tmp_path / "questions.json"
    path.write_text(json.dumps(question_set()), encoding="utf-8")
    return tmp_path, path


def run_score(tmp_path, questions, trace):
    trace["questions_sha256"] = ev.digest_bytes(questions.read_bytes())
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "capture.json").write_text(json.dumps(trace), encoding="utf-8")
    ev.score(type("A", (), {"questions": questions, "run_dir": run_dir})())
    return json.loads((run_dir / "score.json").read_text())["summary"]


def test_all_correct(harness):
    tmp_path, questions = harness
    summary = run_score(tmp_path, questions, full_trace())

    assert summary["correct_interpretations"] == 8
    assert summary["unsafe_publications"] == 0
    assert summary["false_sufficient"] == 0
    assert summary["coverage_recall"] == 1.0
    assert summary["missing_status_accuracy"] == 1.0


def test_false_sufficient_is_flagged(harness):
    tmp_path, questions = harness
    trace = full_trace()
    trace["cases"][2]["coverage"]["complete"] = True
    summary = run_score(tmp_path, questions, trace)
    assert summary["false_sufficient"] == 1


def test_unsafe_publication_is_flagged(harness):
    tmp_path, questions = harness
    trace = full_trace()
    trace["cases"][5] = record("T-6", "REPORT_READY",
                               facts=[fact("营业收入", "6,191,107,217.36", 46)])
    summary = run_score(tmp_path, questions, trace)
    assert summary["unsafe_publications"] == 1


def test_missing_status_mismatch(harness):
    tmp_path, questions = harness
    trace = full_trace()
    trace["cases"][2]["coverage"]["requirements"][1]["status"] = "SATISFIED"
    summary = run_score(tmp_path, questions, trace)
    assert summary["missing_status_accuracy"] == 0.0


def test_frozen_hash_mismatch(harness):
    tmp_path, questions = harness
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    trace = full_trace()
    trace["questions_sha256"] = "f" * 64
    (run_dir / "capture.json").write_text(json.dumps(trace), encoding="utf-8")

    with pytest.raises(ValueError, match="QUESTIONS_FROZEN_HASH_MISMATCH"):
        ev.score(type("A", (), {"questions": questions, "run_dir": run_dir})())
