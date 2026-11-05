"""Offline tests for the repair scorer. No PDF, no runtime."""
from pathlib import Path
import json

import pytest

import run_m4_repair_eval as ev

AS_OF = "2026-11-03T00:00:00+08:00"
SOURCE = {
    "ticker": "600760", "issuer": "中航沈飞", "report_key": "600760-2026H1",
    "document_id": "600760-2026H1-cninfo-1225517994", "report_period": "2026H1",
    "published_on": "2026-08-28", "source_url": "https://example.test/r.pdf",
    "source_sha256": "a" * 64, "canonical_sha256": "b" * 64, "pdf_pages": 207,
}
RD = "59,650,843.12"


def repair_case(i, facet="研发投入", target="研发费用"):
    return {
        "case_id": f"R-{i}", "family": "repair_expected",
        "question": f"营业收入和{facet}分别是多少？",
        "expected": {"outcome": "REPAIR", "target_core": target,
                     "target_value": RD, "target_page": 47},
        "rejection_category": None, "expected_runtime_reasons": [],
    }


def partial_case(i, core):
    return {
        "case_id": f"R-{i}", "family": "no_candidate",
        "question": f"营业收入和{core}分别是多少？",
        "expected": {"outcome": "PARTIAL", "missing_core": core},
        "rejection_category": None, "expected_runtime_reasons": [],
    }


def complete_case(i, second, value):
    return {
        "case_id": f"R-{i}", "family": "complete_control",
        "question": f"营业收入和{second}分别是多少？",
        "expected": {"outcome": "COMPLETE", "cells": [
            {"row_label": "其中：营业收入", "value": "6,191,107,217.36", "page": 46},
            {"row_label": second, "value": value, "page": 47},
        ]},
        "rejection_category": None, "expected_runtime_reasons": [],
    }


def question_set():
    cases = [
        repair_case(1), repair_case(2, "研发支出"),
        partial_case(3, "研究费用"), partial_case(4, "员工人数"),
        complete_case(5, "其中：利息费用", "1,738,474.95"),
        complete_case(6, "五、净利润", "468,144,459.10"),
    ]
    return {
        "schema_version": ev.QUESTIONS_SCHEMA,
        "corpus_type": "AUTHOR_CURATED_DEVELOPMENT_NOT_INDEPENDENT_HOLDOUT",
        "scope": "600760_2026H1_REPAIR", "as_of": AS_OF,
        "question_count": len(cases), "source": SOURCE, "cases": cases,
        "research_publication": "BLOCKED",
    }


def fact(row, value, page):
    return {"row_label": row, "value_verbatim": value, "page_number": page}


REVENUE = fact("其中：营业收入", "6,191,107,217.36", 46)


def coverage(complete, requirements, repair=None):
    return {"complete": complete, "total": len(requirements),
            "satisfied": sum(1 for r in requirements if r["status"] == "VERIFIED"),
            "requirements": requirements, "repair": repair}


def repair_block(core="研发费用", option_id="opt-1"):
    return {"facet": core, "token": "token", "options": [
        {"option_id": option_id, "core": core, "row_label": core},
    ]}


def record(case_id, *, facts=(), coverage_value=None, resolutions=None,
           status="REPORT_READY", reason=None):
    return {"case_id": case_id, "status": status, "reason": reason,
            "facts": list(facts), "coverage": coverage_value,
            "resolutions": resolutions or {}, "latency_ms": 1000}


def full_trace():
    rd = fact("研发费用", RD, 47)
    return {
        "schema_version": ev.CAPTURE_SCHEMA, "questions_sha256": "x" * 64,
        "repo": {"git_head": "0" * 40},
        "cases": [
            record("R-1", facts=[REVENUE],
                   coverage_value=coverage(False, [
                       {"facet": "营业收入", "status": "VERIFIED"},
                       {"facet": "研发投入", "status": "NO_ROW_MATCH"}],
                       repair_block()),
                   resolutions={"opt-1": {"core": "研发费用", "status": "REPORT_READY",
                                          "reason": None, "facts": [REVENUE, rd],
                                          "coverage": coverage(True, [
                                              {"facet": "营业收入", "status": "VERIFIED"},
                                              {"facet": "研发投入", "status": "VERIFIED"}])}}),
            record("R-2", facts=[REVENUE],
                   coverage_value=coverage(False, [
                       {"facet": "营业收入", "status": "VERIFIED"},
                       {"facet": "研发支出", "status": "NO_ROW_MATCH"}],
                       repair_block()),
                   resolutions={"opt-1": {"core": "研发费用", "status": "REPORT_READY",
                                          "reason": None, "facts": [REVENUE, rd],
                                          "coverage": coverage(True, [])}}),
            record("R-3", facts=[REVENUE],
                   coverage_value=coverage(False, [
                       {"facet": "营业收入", "status": "VERIFIED"},
                       {"facet": "研究费用", "status": "NO_ROW_MATCH"}])),
            record("R-4", facts=[REVENUE],
                   coverage_value=coverage(False, [
                       {"facet": "营业收入", "status": "VERIFIED"},
                       {"facet": "员工人数", "status": "NO_ROW_MATCH"}])),
            record("R-5", facts=[REVENUE, fact("其中：利息费用", "1,738,474.95", 47)],
                   coverage_value=coverage(True, [])),
            record("R-6", facts=[REVENUE, fact("五、净利润", "468,144,459.10", 47)],
                   coverage_value=coverage(True, [])),
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

    assert summary["repair_offered"] == 2
    assert summary["candidate_recall"] == 1.0
    assert summary["candidate_top1_hit"] == 2
    assert summary["confirmation_success"] == 2
    assert summary["correct_partial_no_candidate"] == 2
    assert summary["correct_complete_control"] == 2
    assert summary["unexpected_repair_offers"] == 0
    assert summary["unsafe_publications"] == 0


def test_missing_repair_is_flagged(harness):
    tmp_path, questions = harness
    trace = full_trace()
    trace["cases"][0]["coverage"]["repair"] = None
    summary = run_score(tmp_path, questions, trace)
    assert summary["repair_offered"] == 1
    assert summary["confirmation_success"] == 1


def test_unexpected_repair_on_no_candidate(harness):
    tmp_path, questions = harness
    trace = full_trace()
    trace["cases"][2]["coverage"]["repair"] = repair_block("研发费用")
    summary = run_score(tmp_path, questions, trace)
    assert summary["unexpected_repair_offers"] == 1


def test_unexpected_fact_after_repair_is_unsafe(harness):
    tmp_path, questions = harness
    trace = full_trace()
    trace["cases"][0]["resolutions"]["opt-1"]["facts"].append(
        fact("其中：营业成本", "5,535,215,299.31", 46)
    )
    summary = run_score(tmp_path, questions, trace)
    assert summary["unsafe_publications"] == 1


def test_frozen_hash_mismatch(harness):
    tmp_path, questions = harness
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    trace = full_trace()
    trace["questions_sha256"] = "f" * 64
    (run_dir / "capture.json").write_text(json.dumps(trace), encoding="utf-8")

    with pytest.raises(ValueError, match="QUESTIONS_FROZEN_HASH_MISMATCH"):
        ev.score(type("A", (), {"questions": questions, "run_dir": run_dir})())
