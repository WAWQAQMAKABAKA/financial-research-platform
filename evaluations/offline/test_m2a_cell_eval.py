"""Offline tests for the M2a cell-level evaluation harness. No PDF, no runtime."""
from pathlib import Path
import json

import pytest

import run_m2a_cell_eval as ev

AS_OF = "2026-11-02T23:00:00+08:00"
SOURCE = {
    "ticker": "600760",
    "issuer": "中航沈飞",
    "report_key": "600760-2026H1",
    "document_id": "600760-2026H1-cninfo-1225517994",
    "report_period": "2026H1",
    "published_on": "2026-08-28",
    "source_url": "https://example.test/r.pdf",
    "source_sha256": "a" * 64,
    "canonical_sha256": "b" * 64,
    "pdf_pages": 207,
}
PUBLISH_CASES = 8
REJECT_CASES = 7


def publish_case(index: int) -> dict:
    return {
        "case_id": f"T-{index}",
        "family": "revenue",
        "question": f"合并利润表中营业收入是多少？({index})",
        "expected": {
            "outcome": "PUBLISH",
            "statement_kind": "consolidated_income_statement",
            "statement_title": "合并利润表",
            "cells": [{
                "row_label": "其中：营业收入",
                "column_header": "2026 年半年度",
                "page_number": 46,
                "value": "6,191,107,217.36",
            }],
            "selection_basis": "QUESTION_STATEMENT_TITLE",
        },
        "rejection_category": None,
        "expected_runtime_reasons": [],
    }


def reject_case(index: int) -> dict:
    return {
        "case_id": f"T-{index}",
        "family": "comparison",
        "question": f"营业收入比去年增长多少？({index})",
        "expected": {"outcome": "REJECT", "cells": [], "selection_basis": None},
        "rejection_category": "COMPARISON_NOT_PUBLISHABLE",
        "expected_runtime_reasons": [],
    }


def question_set(**overrides) -> dict:
    body = {
        "schema_version": ev.QUESTIONS_SCHEMA,
        "corpus_type": "AUTHOR_CURATED_DEVELOPMENT_NOT_INDEPENDENT_HOLDOUT",
        "scope": "600760_2026H1_INCOME_STATEMENT_AMOUNTS",
        "as_of": AS_OF,
        "question_count": PUBLISH_CASES + REJECT_CASES,
        "source": SOURCE,
        "cases": [publish_case(i) for i in range(1, PUBLISH_CASES + 1)]
                 + [reject_case(i) for i in range(PUBLISH_CASES + 1, PUBLISH_CASES + REJECT_CASES + 1)],
        "research_publication": "BLOCKED",
    }
    body.update(overrides)
    return body


def write_set(tmp_path: Path, body) -> Path:
    path = tmp_path / "questions.json"
    path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    return path


def trace(cases, questions_sha="x" * 64):
    return {
        "schema_version": ev.CAPTURE_SCHEMA,
        "questions_sha256": questions_sha,
        "repo": {"git_head": "0" * 40},
        "cases": cases,
    }


def case(case_id, *, status="REPORT_READY", reason=None, facts=None, pages=None):
    return {
        "case_id": case_id,
        "status": status,
        "reason": reason,
        "publication": "FACTS_ONLY" if facts else "BLOCKED",
        "facts": facts or [],
        "selection": {"basis": "QUESTION_STATEMENT_TITLE"},
        "retrieval_pages": pages or [],
        "latency_ms": 1000,
    }


def fact(row="其中：营业收入", value="6,191,107,217.36", page=46):
    return {
        "statement_type": "consolidated_income_statement",
        "row_label": row,
        "column_header": "2026 年半年度",
        "page_number": page,
        "value_verbatim": value,
        "citation_page": page,
    }


def all_cases(*, published=(), rejected=()):
    cases = []
    for i in range(1, PUBLISH_CASES + 1):
        cases.append(case(f"T-{i}", facts=[fact()], pages=[46]) if i in published else
                     case(f"T-{i}", status="REPORT_WITHHELD", reason="NO_ROW_MATCH"))
    for i in range(PUBLISH_CASES + 1, PUBLISH_CASES + REJECT_CASES + 1):
        cases.append(case(f"T-{i}", facts=[fact()]) if i in rejected else
                     case(f"T-{i}", status="REPORT_WITHHELD", reason="NO_ROW_MATCH"))
    return cases


@pytest.fixture
def harness(tmp_path, monkeypatch):
    monkeypatch.setattr(ev, "CACHE_ROOT", tmp_path)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"documents": [{
        "document_id": SOURCE["document_id"],
        "source_sha256": SOURCE["source_sha256"],
        "canonical_sha256": SOURCE["canonical_sha256"],
        "source_url": SOURCE["source_url"],
        "report_period": SOURCE["report_period"],
        "ticker": "600760",
        "issuer_name": "中航沈飞",
        "published_on": "2026-08-28",
        "page_count": 207,
    }]}), encoding="utf-8")
    monkeypatch.setattr(ev, "MANIFEST", manifest)
    return tmp_path, write_set(tmp_path, question_set())


def run_score(tmp_path, path, cases):
    trace_path = tmp_path / "trace.json"
    trace_path.write_text(json.dumps(trace(cases, ev.digest_bytes(path.read_bytes()))),
                          encoding="utf-8")
    out = tmp_path / "score.json"
    ev.score(type("A", (), {"questions": path, "trace": trace_path, "out": out,
                            "run_dir": None})())
    return json.loads(out.read_text())["summary"]


def test_valid_questions_load_with_expectations(harness):
    _, path = harness
    body, digest, as_of = ev.load_questions(path, with_expectations=True)

    assert len(digest) == 64
    assert as_of == AS_OF
    assert body["cases"][0]["expected"]["outcome"] == "PUBLISH"


def test_capture_loader_is_label_blind(harness):
    _, path = harness
    body, _, _ = ev.load_questions(path, with_expectations=False)

    for case in body["cases"]:
        assert set(case) == {"case_id", "family", "question"}
        assert "expected" not in case


def test_bad_schema_is_rejected(harness, tmp_path):
    with pytest.raises(ValueError, match="QUESTION_SCHEMA_INVALID"):
        ev.load_questions(write_set(tmp_path, question_set(schema_version="wrong")),
                          with_expectations=True)


def test_publication_must_remain_blocked(harness, tmp_path):
    with pytest.raises(ValueError, match="QUESTION_PUBLICATION_MUST_BE_BLOCKED"):
        ev.load_questions(write_set(tmp_path, question_set(research_publication="FACTS_ONLY")),
                          with_expectations=True)


def test_source_must_match_the_manifest(harness, tmp_path):
    body = question_set()
    body["source"] = {**body["source"], "source_sha256": "c" * 64}
    with pytest.raises(ValueError, match="QUESTION_SOURCE_MISMATCH:source_sha256"):
        ev.load_questions(write_set(tmp_path, body), with_expectations=True)


def test_reject_case_requires_a_category(harness, tmp_path):
    body = question_set()
    body["cases"][-1]["rejection_category"] = None
    with pytest.raises(ValueError, match="EXPECTED_REJECTION_CATEGORY_MISSING"):
        ev.load_questions(write_set(tmp_path, body), with_expectations=True)


def test_output_inside_repository_is_refused():
    with pytest.raises(ValueError, match="PRIVATE_OUTPUT_NOT_IN_PRIVATE_AREA"):
        ev.check_output_path(ev.ROOT / "capture.json")


def test_score_counts_exact_and_correct_rejection(harness):
    tmp_path, path = harness
    summary = run_score(tmp_path, path, all_cases(
        published=tuple(range(1, PUBLISH_CASES + 1))))

    assert summary["unsafe_publications"] == 0
    assert summary["wrong_cell_publications"] == 0
    assert summary["exact_cell_matches"] == PUBLISH_CASES
    assert summary["correct_rejections"] == REJECT_CASES
    assert summary["false_rejections"] == 0
    assert summary["retrieval_page_recall"]["@1"] == 1.0


def test_score_flags_unsafe_publication(harness):
    tmp_path, path = harness
    summary = run_score(tmp_path, path, all_cases(
        published=tuple(range(1, PUBLISH_CASES + 1)), rejected=(PUBLISH_CASES + 1,)))

    assert summary["unsafe_publications"] == 1


def test_score_flags_wrong_cell(harness):
    tmp_path, path = harness
    cases = all_cases(published=tuple(range(1, PUBLISH_CASES + 1)))
    cases[0]["facts"] = [fact(value="5,535,215,299.31", page=46)]
    summary = run_score(tmp_path, path, cases)

    assert summary["wrong_cell_publications"] == 1
    assert summary["exact_cell_matches"] == PUBLISH_CASES - 1


def test_score_refuses_a_refrozen_question_set(harness):
    tmp_path, path = harness
    trace_path = tmp_path / "trace.json"
    trace_path.write_text(json.dumps(trace(all_cases(), "f" * 64)), encoding="utf-8")

    with pytest.raises(ValueError, match="QUESTIONS_FROZEN_HASH_MISMATCH"):
        ev.score(type("A", (), {"questions": path, "trace": trace_path,
                                "out": tmp_path / "score.json", "run_dir": None})())


def test_run_dir_requires_a_new_directory(tmp_path):
    args = type("A", (), {"out": None, "run_dir": tmp_path / "run1"})
    assert ev.capture_target(args) == (tmp_path / "run1").resolve() / "capture.json"

    (tmp_path / "run1").mkdir()
    with pytest.raises(ValueError, match="RUN_DIRECTORY_EXISTS"):
        ev.capture_target(args)


def test_run_dir_and_explicit_output_are_mutually_exclusive(tmp_path):
    args = type("A", (), {"out": tmp_path / "x.json", "run_dir": tmp_path / "run"})
    with pytest.raises(ValueError, match="OUT_AND_RUN_DIR_ARE_MUTUALLY_EXCLUSIVE"):
        ev.capture_target(args)


def test_score_run_dir_requires_capture(tmp_path):
    args = type("A", (), {"trace": None, "out": None, "run_dir": tmp_path / "missing"})
    with pytest.raises(ValueError, match="RUN_DIRECTORY_MISSING"):
        ev.score_targets(args)

    (tmp_path / "run").mkdir()
    args = type("A", (), {"trace": None, "out": None, "run_dir": tmp_path / "run"})
    trace, out = ev.score_targets(args)
    assert trace.name == "capture.json" and out.name == "score.json"
