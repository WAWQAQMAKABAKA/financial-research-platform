"""Offline tests for the Experiment A scorer. No PDF, no runtime."""
from pathlib import Path
import json

import pytest

import run_m3_clarification_eval as ev

AS_OF = "2026-11-03T00:00:00+08:00"
SOURCE = {
    "ticker": "600760", "issuer": "中航沈飞", "report_key": "600760-2026H1",
    "document_id": "600760-2026H1-cninfo-1225517994", "report_period": "2026H1",
    "published_on": "2026-08-28", "source_url": "https://example.test/r.pdf",
    "source_sha256": "a" * 64, "canonical_sha256": "b" * 64, "pdf_pages": 207,
}


def publish_case(i):
    return {
        "case_id": f"T-{i}", "family": "revenue",
        "question": f"合并利润表中营业收入是多少？({i})",
        "expected": {"outcome": "PUBLISH", "cells": [{
            "row_label": "其中：营业收入", "column_header": "2026 年半年度",
            "page_number": 46, "value": "6,191,107,217.36"}]},
        "rejection_category": None, "expected_runtime_reasons": [],
    }


def reject_case(i):
    return {
        "case_id": f"T-{i}", "family": "comparison",
        "question": f"营业收入比去年增长多少？({i})",
        "expected": {"outcome": "REJECT", "cells": []},
        "rejection_category": "COMPARISON_NOT_PUBLISHABLE",
        "expected_runtime_reasons": ["COMPARISON_NOT_PUBLISHABLE"],
    }


def clarify_case(i):
    return {
        "case_id": f"T-{i}", "family": "ambiguous_profit",
        "question": f"净利是多少？({i})",
        "expected": {
            "outcome": "CLARIFY",
            "required_option_cores": ["净利润", "归属于母公司股东的净利润"],
            "resolutions": {
                "净利润": {"row_label": "五、净利润", "column_header": "2026 年半年度",
                          "page_number": 47, "value": "468,144,459.10"},
                "归属于母公司股东的净利润": {
                    "row_label": "1.归属于母公司股东的净利润", "column_header": "2026 年半年度",
                    "page_number": 47, "value": "473,065,863.24"},
            },
        },
        "rejection_category": "METRIC_IDENTITY_AMBIGUOUS",
        "expected_runtime_reasons": ["METRIC_IDENTITY_AMBIGUOUS"],
    }


def question_set(**overrides):
    cases = ([publish_case(i) for i in range(1, 7)]
             + [reject_case(i) for i in range(7, 11)]
             + [clarify_case(11), clarify_case(12)])
    body = {
        "schema_version": ev.QUESTIONS_SCHEMA,
        "corpus_type": "AUTHOR_CURATED_DEVELOPMENT_NOT_INDEPENDENT_HOLDOUT",
        "scope": "600760_2026H1_CLARIFICATION",
        "as_of": AS_OF,
        "question_count": len(cases),
        "source": SOURCE,
        "cases": cases,
        "research_publication": "BLOCKED",
    }
    body.update(overrides)
    return body


def fact(row="其中：营业收入", value="6,191,107,217.36", page=46):
    return {"row_label": row, "column_header": "2026 年半年度",
            "page_number": page, "value_verbatim": value, "statement_type": "consolidated_income_statement"}


def record(case_id, status, *, reason=None, facts=None, options=None, resolutions=None):
    return {
        "case_id": case_id, "status": status, "reason": reason,
        "facts": facts or [], "latency_ms": 1000,
        "clarification": None if options is None else {
            "reason": "METRIC_IDENTITY_AMBIGUOUS", "option_basis": "NEAR_MATCH",
            "options": options, "interpretation_status": "NOT_PERFORMED",
            "research_publication": "BLOCKED",
        },
        "resolutions": resolutions or {},
    }


def option(core, row_label):
    return {"option_id": f"{core}-id", "core": core, "row_label": row_label,
            "statement_title": "合并利润表"}


def full_trace():
    cases = []
    for i in range(1, 7):
        cases.append(record(f"T-{i}", "REPORT_READY", facts=[fact()]))
    for i in range(7, 11):
        cases.append(record(f"T-{i}", "REPORT_WITHHELD", reason="COMPARISON_NOT_PUBLISHABLE"))
    for i in (11, 12):
        options = [
            option("净利润", "五、净利润"),
            option("归属于母公司股东的净利润", "1.归属于母公司股东的净利润"),
        ]
        resolutions = {
            "净利润-id": {"core": "净利润", "status": "REPORT_READY", "reason": None,
                          "facts": [fact(row="五、净利润", value="468,144,459.10", page=47)]},
            "归属于母公司股东的净利润-id": {
                "core": "归属于母公司股东的净利润", "status": "REPORT_READY", "reason": None,
                "facts": [fact(row="1.归属于母公司股东的净利润", value="473,065,863.24", page=47)]},
        }
        cases.append(record(f"T-{i}", "CLARIFICATION_REQUIRED",
                            reason="METRIC_IDENTITY_AMBIGUOUS",
                            options=options, resolutions=resolutions))
    return {"schema_version": ev.CAPTURE_SCHEMA, "questions_sha256": "x" * 64,
            "repo": {"git_head": "0" * 40}, "cases": cases}


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
    questions = tmp_path / "questions.json"
    questions.write_text(json.dumps(question_set()), encoding="utf-8")
    return tmp_path, questions


def run_score(tmp_path, questions, trace):
    sha = ev.digest_bytes(questions.read_bytes())
    trace["questions_sha256"] = sha
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "capture.json").write_text(json.dumps(trace), encoding="utf-8")
    ev.score(type("A", (), {"questions": questions, "run_dir": run_dir})())
    return json.loads((run_dir / "score.json").read_text())["summary"]


def test_all_correct(harness):
    tmp_path, questions = harness
    summary = run_score(tmp_path, questions, full_trace())

    assert summary["correct_interpretations"] == 12
    assert summary["unsafe_publications"] == 0
    assert summary["unnecessary_clarifications"] == 0
    assert summary["guessed_when_should_clarify"] == 0
    assert summary["clarification_option_recall"] == 1.0
    assert summary["resolution_correct_rate"] == 1.0
    assert summary["option_binding_accuracy"] == 1.0


def test_unsafe_publication_is_flagged(harness):
    tmp_path, questions = harness
    trace = full_trace()
    trace["cases"][6]["status"] = "REPORT_READY"
    trace["cases"][6]["facts"] = [fact()]
    summary = run_score(tmp_path, questions, trace)
    assert summary["unsafe_publications"] == 1


def test_guessed_when_should_clarify(harness):
    tmp_path, questions = harness
    trace = full_trace()
    trace["cases"][10]["status"] = "REPORT_READY"
    trace["cases"][10]["facts"] = [fact(row="五、净利润", value="468,144,459.10", page=47)]
    summary = run_score(tmp_path, questions, trace)
    assert summary["guessed_when_should_clarify"] == 1


def test_unnecessary_clarification(harness):
    tmp_path, questions = harness
    trace = full_trace()
    trace["cases"][0]["status"] = "CLARIFICATION_REQUIRED"
    trace["cases"][0]["facts"] = []
    summary = run_score(tmp_path, questions, trace)
    assert summary["unnecessary_clarifications"] == 1


def test_missing_expected_option_lowers_recall(harness):
    tmp_path, questions = harness
    trace = full_trace()
    trace["cases"][10]["clarification"]["options"] = [option("净利润", "五、净利润")]
    trace["cases"][10]["resolutions"] = {
        "净利润-id": trace["cases"][10]["resolutions"]["净利润-id"],
    }
    summary = run_score(tmp_path, questions, trace)
    assert summary["clarification_option_recall"] == 0.75
    assert summary["correct_interpretations"] == 11


def test_frozen_hash_mismatch_is_rejected(harness):
    tmp_path, questions = harness
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    trace = full_trace()
    trace["questions_sha256"] = "f" * 64
    (run_dir / "capture.json").write_text(json.dumps(trace), encoding="utf-8")

    with pytest.raises(ValueError, match="QUESTIONS_FROZEN_HASH_MISMATCH"):
        ev.score(type("A", (), {"questions": questions, "run_dir": run_dir})())
