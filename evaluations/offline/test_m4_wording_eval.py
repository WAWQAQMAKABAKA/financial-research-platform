"""Offline tests for the wording scorer. No PDF, no runtime."""
from pathlib import Path
import json

import pytest

import run_m4_wording_eval as ev

AS_OF = "2026-11-03T00:00:00+08:00"
SOURCE = {
    "ticker": "600760", "issuer": "中航沈飞", "report_key": "600760-2026H1",
    "document_id": "600760-2026H1-cninfo-1225517994", "report_period": "2026H1",
    "published_on": "2026-08-28", "source_url": "https://example.test/r.pdf",
    "source_sha256": "a" * 64, "canonical_sha256": "b" * 64, "pdf_pages": 207,
}
REV = {"row_label": "其中：营业收入", "value": "6,191,107,217.36", "page": 46}
PROFIT = {"row_label": "五、净利润", "value": "468,144,459.10", "page": 47}
COST = {"row_label": "其中：营业成本", "value": "5,535,215,299.31", "page": 46}
RD = {"row_label": "研发费用", "value": "59,650,843.12", "page": 47}


def question_set():
    cases = [
        {"case_id": "W-01", "family": "two", "question": "营业收入？净利润？",
         "expected": {"cells": [REV, PROFIT]}},
        {"case_id": "W-02", "family": "three", "question": "营业收入？净利润？营业成本？",
         "expected": {"cells": [REV, PROFIT, COST]}},
        {"case_id": "W-03", "family": "mixed", "question": "营业收入？净利润和营业成本？",
         "expected": {"cells": [REV, PROFIT, COST]}},
        {"case_id": "W-04", "family": "four", "question": "营业收入、净利润、营业成本、研发费用？",
         "expected": {"cells": [REV, PROFIT, COST, RD]}},
    ]
    return {
        "schema_version": ev.QUESTIONS_SCHEMA,
        "corpus_type": "AUTHOR_CURATED_DEVELOPMENT_NOT_INDEPENDENT_HOLDOUT",
        "scope": "600760_2026H1_WORDING", "as_of": AS_OF,
        "question_count": 4, "source": SOURCE, "cases": cases,
        "research_publication": "BLOCKED",
    }


def fact(cell):
    return {"row_label": cell["row_label"], "value_verbatim": cell["value"],
            "page_number": cell["page"]}


def record(case_id, cells, *, plan=None, complete=None, report_type="X"):
    coverage = None if complete is None else {
        "complete": complete, "total": len(cells), "satisfied": len(cells),
        "plan_source": plan, "requirements": [],
    }
    return {"case_id": case_id, "status": "REPORT_READY", "report_type": report_type,
            "facts": [fact(cell) for cell in cells], "coverage": coverage,
            "latency_ms": 1000}


def full_trace():
    return {
        "schema_version": ev.CAPTURE_SCHEMA, "questions_sha256": "x" * 64,
        "repo": {"git_head": "0" * 40}, "llm_enabled": True,
        "cases": [
            record("W-01", [REV, PROFIT], report_type="FACTS_ONLY_QUESTION_REPORT"),
            record("W-02", [REV, PROFIT, COST], plan="LLM_PROPOSAL_VALIDATED", complete=True),
            record("W-03", [REV, PROFIT, COST], plan="LLM_PROPOSAL_VALIDATED", complete=True),
            record("W-04", [REV, PROFIT, COST], plan="LLM_PROPOSAL_VALIDATED", complete=True),
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


def test_single_report_counts_as_cells_ok(harness):
    tmp_path, questions = harness
    summary = run_score(tmp_path, questions, full_trace())

    assert summary["cell_recall"] == 0.9167
    assert summary["no_coverage_single_reports"] == 1
    assert summary["under_decomposition"] == 1
    assert summary["over_answer"] == 0
    assert summary["llm_planned_cases"] == 3


def test_under_decomposition_is_flagged(harness):
    tmp_path, questions = harness
    trace = full_trace()
    trace["cases"][2] = record("W-03", [REV, PROFIT],
                               plan="LLM_PROPOSAL_VALIDATED", complete=True)
    summary = run_score(tmp_path, questions, trace)
    assert summary["under_decomposition"] == 2


def test_over_answer_is_unsafe(harness):
    tmp_path, questions = harness
    trace = full_trace()
    trace["cases"][1]["facts"].append(fact(RD))
    summary = run_score(tmp_path, questions, trace)
    assert summary["over_answer"] == 1
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
