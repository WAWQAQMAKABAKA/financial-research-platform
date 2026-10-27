"""M130-A: STRICTLY OFFLINE, label-blind retrieval capture + separate page-level scoring.

Capture uses the already verified local PDF and production retrieval interface, but
never reads reference labels. Score reads author-curated DEVELOPMENT references;
those are NOT ground truth for financial answers, not OOS, and not runtime inputs.
No LLM, network, benchmark GT, trading data, or publication pathways.
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
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = Path(__file__).with_name("rag_questions_dev_v1.json")
REFERENCES = Path(__file__).with_name("rag_page_references_dev_v1.json")
CAPTURE_SCHEMA = "frp-m130-retrieval-trace-v1"
SCORE_SCHEMA = "frp-m130-retrieval-score-v1"
KS = (1, 3, 5)


def _digest(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    data = path.read_bytes()
    obj = json.loads(data)
    if not isinstance(obj, dict):
        raise ValueError("EVAL_JSON_OBJECT_REQUIRED")
    return obj, _digest(data)


def load_questions(path: Path = QUESTIONS) -> tuple[dict[str, Any], str]:
    payload, digest = _read_json(path)
    if (payload.get("schema_version") != "frp-m130-rag-questions-dev-v1"
            or payload.get("corpus_type") != "AUTHOR_CURATED_DEVELOPMENT_NOT_PROTECTED_GT"):
        raise ValueError("QUESTION_MANIFEST_PROVENANCE_INVALID")
    source = payload.get("source_binding")
    if (not isinstance(source, dict)
            or set(source) != {"report_key", "document_id", "source_sha256", "canonical_sha256"}
            or any(not isinstance(source.get(key), str) or not source[key]
                   for key in source)
            or any(len(source[key]) != 64 or any(c not in "0123456789abcdef" for c in source[key])
                   for key in ("source_sha256", "canonical_sha256"))):
        raise ValueError("QUESTION_SOURCE_BINDING_INVALID")
    instant = datetime.fromisoformat(payload.get("as_of", ""))
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("QUESTION_AS_OF_NAIVE")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases or len(cases) > 100:
        raise ValueError("QUESTION_CASES_INVALID")
    seen: set[str] = set()
    for case in cases:
        if (not isinstance(case, dict)
                or set(case) != {"case_id", "family", "question"}
                or not isinstance(case["case_id"], str) or not case["case_id"]
                or case["case_id"] in seen
                or not isinstance(case["family"], str) or not case["family"]
                or not isinstance(case["question"], str) or not case["question"].strip()
                or len(case["question"]) > 240
                or len(case["question"].encode("utf-8")) > 800):
            raise ValueError("QUESTION_CASE_INVALID_OR_DUPLICATE")
        seen.add(case["case_id"])
    return payload, digest


def load_references(path: Path = REFERENCES) -> tuple[dict[str, Any], str]:
    payload, digest = _read_json(path)
    if (payload.get("schema_version") != "frp-m130-page-references-dev-v1"
            or payload.get("corpus_type") != "AUTHOR_CURATED_DEVELOPMENT_NOT_INDEPENDENT_GT"
            or payload.get("annotation_scope") != "SOURCE_PAGE_RELEVANCE_ONLY_NOT_FINANCIAL_ANSWER_TRUTH"):
        raise ValueError("REFERENCE_PROVENANCE_INVALID")
    rows = payload.get("references")
    if not isinstance(rows, list) or not rows:
        raise ValueError("REFERENCE_ROWS_INVALID")
    seen: set[str] = set()
    for row in rows:
        if (not isinstance(row, dict)
                or set(row) != {"case_id", "relevant_pages", "contrast_pages", "note"}
                or not isinstance(row["case_id"], str) or not row["case_id"]
                or row["case_id"] in seen
                or not isinstance(row["note"], str) or not row["note"].strip()):
            raise ValueError("REFERENCE_ROW_INVALID_OR_DUPLICATE")
        for field in ("relevant_pages", "contrast_pages"):
            values = row[field]
            if (not isinstance(values, list)
                    or (field == "relevant_pages" and not values)
                    or len(values) != len(set(values))
                    or any(type(value) is not int or value < 1 or value > 182 for value in values)):
                raise ValueError("REFERENCE_PAGES_INVALID")
        if set(row["relevant_pages"]) & set(row["contrast_pages"]):
            raise ValueError("REFERENCE_CONTRAST_OVERLAP")
        seen.add(row["case_id"])
    return payload, digest


def _git_state() -> dict[str, Any]:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    return {
        "git_head": git("rev-parse", "HEAD"),
        "git_branch": git("branch", "--show-current"),
        "tracked_diff_sha256": _digest(subprocess.check_output(
            ["git", "diff", "--binary", "HEAD", "--"], cwd=ROOT,
        )),
    }


def capture(pdf: Path, manifest: dict[str, Any], manifest_sha: str) -> dict[str, Any]:
    # Production modules are imported only into this LABEL-BLIND capture branch.
    from app.evidence.pdf_canonicalizer import canonicalize_pdf
    from app.modules.financial_report_analyst import canonical_retrieval, revenue_scope

    source = revenue_scope.SOURCE
    binding = manifest["source_binding"]
    for key, actual in (
        ("document_id", source.document_id),
        ("source_sha256", source.source_sha256),
        ("canonical_sha256", source.canonical_sha256),
        ("report_key", "600276-2026H1"),
    ):
        if binding[key] != actual:
            raise ValueError("CAPTURE_SOURCE_MANIFEST_MISMATCH:" + key)
    instant = datetime.fromisoformat(manifest["as_of"])
    source.require_available(instant)
    if not pdf.is_file() or _digest(pdf.read_bytes()) != source.source_sha256:
        raise ValueError("CAPTURE_ORIGINAL_PDF_INVALID")
    document = canonicalize_pdf(
        document_id=source.document_id,
        pdf_path=pdf,
        expected_source_sha256=source.source_sha256,
    )
    if document.canonical_sha256 != source.canonical_sha256:
        raise ValueError("CAPTURE_CANONICAL_PDF_INVALID")

    output_cases = []
    for case in manifest["cases"]:
        packet = canonical_retrieval.retrieve_from_canonical(
            source, document, case["question"], as_of=instant,
        )
        if (packet["question"] != case["question"]
                or packet["document_id"] != source.document_id
                or packet["source_sha256"] != source.source_sha256
                or packet["canonical_sha256"] != source.canonical_sha256
                or packet["as_of"] != instant.isoformat()
                or packet["status"] not in ("RETRIEVAL_CANDIDATES_READY", "WITHHELD")
                or packet["research_publication"] != "BLOCKED"
                or packet["financial_semantic_review"] != "NOT_PERFORMED"
                or packet["report_storage"] != "NOT_PERSISTED"):
            raise ValueError("CAPTURE_RETRIEVAL_CONTRACT_INVALID")
        hits = []
        for index, hit in enumerate(packet["evidence"], 1):
            excerpt = hit["source_excerpt"]
            if (hit["review_scope"] != "VERIFIED_CANONICAL_TEXT_SPAN_ONLY"
                    or document.canonical_text[
                        hit["canonical_start"]:hit["canonical_end"]
                    ] != excerpt):
                raise ValueError("CAPTURE_CANONICAL_SPAN_INVALID")
            hits.append({
                "rank": index,
                "evidence_id": hit["evidence_id"],
                "source_page": hit["source_page"],
                "canonical_start": hit["canonical_start"],
                "canonical_end": hit["canonical_end"],
                "source_excerpt": excerpt,
                "excerpt_sha256": _digest(excerpt.encode("utf-8")),
            })
        output_cases.append({
            "case_id": case["case_id"],
            "family": case["family"],
            "question": case["question"],
            "status": packet["status"],
            "retrieval_id": packet["retrieval_id"],
            "retriever_version": packet["retriever_version"],
            "ranking_version": packet["ranking_version"],
            "evidence": hits,
        })
    return {
        "schema_version": CAPTURE_SCHEMA,
        "evaluation_kind": "LABEL_BLIND_OFFLINE_RETRIEVAL_CAPTURE_DEVELOPMENT",
        "question_manifest_sha256": manifest_sha,
        "as_of": manifest["as_of"],
        "source_document_id": source.document_id,
        "source_sha256": source.source_sha256,
        "canonical_sha256": source.canonical_sha256,
        "source_url": source.source_url,
        **_git_state(),
        "retriever_source_sha256": _digest((ROOT / "services/api/app/modules/financial_report_analyst/canonical_retrieval.py").read_bytes()),
        "capture_runner_sha256": _digest(Path(__file__).read_bytes()),
        "research_publication": "BLOCKED",
        "financial_semantic_review": "NOT_PERFORMED",
        "report_storage": "NOT_PERSISTED",
        "cases": output_cases,
    }


def score(
    trace: dict[str, Any], questions: dict[str, Any],
    question_sha: str, references: dict[str, Any], reference_sha: str,
) -> dict[str, Any]:
    if (trace.get("schema_version") != CAPTURE_SCHEMA
            or trace.get("evaluation_kind") != "LABEL_BLIND_OFFLINE_RETRIEVAL_CAPTURE_DEVELOPMENT"
            or trace.get("question_manifest_sha256") != question_sha
            or trace.get("source_document_id") != questions["source_binding"]["document_id"]
            or trace.get("source_sha256") != questions["source_binding"]["source_sha256"]
            or trace.get("canonical_sha256") != questions["source_binding"]["canonical_sha256"]
            or trace.get("as_of") != questions["as_of"]
            or trace.get("research_publication") != "BLOCKED"
            or trace.get("financial_semantic_review") != "NOT_PERFORMED"
            or trace.get("report_storage") != "NOT_PERSISTED"
            or references.get("source_document_id") != trace["source_document_id"]):
        raise ValueError("SCORE_TRACE_PROVENANCE_INVALID")

    cases = trace.get("cases")
    expected = questions["cases"]
    if (not isinstance(cases, list) or len(cases) != len(expected)
            or not isinstance(trace.get("git_head"), str)
            or len(trace["git_head"]) != 40):
        raise ValueError("SCORE_TRACE_CASE_COUNT_OR_HEAD_INVALID")
    annotation_by_id = {item["case_id"]: item for item in references["references"]}
    ids = {item["case_id"] for item in expected}
    if not set(annotation_by_id) <= ids:
        raise ValueError("SCORE_UNKNOWN_ANNOTATION")

    scored = []
    for case, manifest_case in zip(cases, expected):
        if (not isinstance(case, dict)
                or case.get("case_id") != manifest_case["case_id"]
                or case.get("question") != manifest_case["question"]
                or case.get("family") != manifest_case["family"]
                or case.get("status") not in ("RETRIEVAL_CANDIDATES_READY", "WITHHELD")
                or not isinstance(case.get("evidence"), list)
                or len(case["evidence"]) > 5):
            raise ValueError("SCORE_TRACE_CASE_INVALID")
        hits = case["evidence"]
        seen_ids = set()
        for i, hit in enumerate(hits, 1):
            if (not isinstance(hit, dict) or hit.get("rank") != i
                    or type(hit.get("source_page")) is not int
                    or not 1 <= hit["source_page"] <= 182
                    or not isinstance(hit.get("evidence_id"), str)
                    or len(hit["evidence_id"]) != 64
                    or hit["evidence_id"] in seen_ids
                    or not isinstance(hit.get("source_excerpt"), str)
                    or hit.get("excerpt_sha256") != _digest(hit["source_excerpt"].encode("utf-8"))
                    or type(hit.get("canonical_start")) is not int
                    or type(hit.get("canonical_end")) is not int
                    or hit["canonical_end"] <= hit["canonical_start"]):
                raise ValueError("SCORE_EVIDENCE_TRACE_INVALID")
            seen_ids.add(hit["evidence_id"])
        if (case["status"] == "WITHHELD" and hits) or (case["status"] == "RETRIEVAL_CANDIDATES_READY" and not hits):
            raise ValueError("SCORE_TRACE_STATUS_MISMATCH")
        label = annotation_by_id.get(case["case_id"])
        row = {
            "case_id": case["case_id"],
            "family": case["family"],
            "retrieval_id": case.get("retrieval_id"),
            "ranking_version": case.get("ranking_version"),
            "source_pages_in_rank_order": [hit["source_page"] for hit in hits],
            "annotation_status": "AUTHOR_CURATED_DEVELOPMENT" if label else "NOT_ANNOTATED",
        }
        if label is None:
            row.update({"source_page_recall_at_k": "NOT_MEASURED", "first_relevant_page_rank": None})
        else:
            positives = set(label["relevant_pages"])
            recalls = {
                str(k): round(len(positives & {h["source_page"] for h in hits[:k]}) / len(positives), 6)
                for k in KS
            }
            found_rank = next((i for i, hit in enumerate(hits, 1)
                               if hit["source_page"] in positives), None)
            row.update({
                "annotated_relevant_pages": sorted(positives),
                "related_but_different_pages": label["contrast_pages"],
                "source_page_recall_at_k": recalls,
                "first_relevant_page_rank": found_rank,
                "reciprocal_first_relevant_rank": round(1 / found_rank, 6) if found_rank else 0.0,
            })
        scored.append(row)

    labeled = [item for item in scored if item["annotation_status"] == "AUTHOR_CURATED_DEVELOPMENT"]
    if not labeled:
        raise ValueError("SCORE_NO_ANNOTATED_CASES")
    return {
        "schema_version": SCORE_SCHEMA,
        "evaluation_kind": "AUTHOR_CURATED_IN_SAMPLE_PAGE_RELEVANCE_DIAGNOSTIC_NOT_GENERAL_RAG_QUALITY",
        "trace_sha256": _digest(json.dumps(trace, ensure_ascii=False, sort_keys=True).encode("utf-8")),
        "question_manifest_sha256": question_sha,
        "reference_manifest_sha256": reference_sha,
        "source_document_id": trace["source_document_id"],
        "source_sha256": trace["source_sha256"],
        "canonical_sha256": trace["canonical_sha256"],
        "as_of": trace["as_of"],
        "git_head": trace["git_head"],
        "retriever_source_sha256": trace.get("retriever_source_sha256"),
        "total_questions": len(scored),
        "author_curated_page_labeled_questions": len(labeled),
        "unannotated_questions_not_scored": len(scored) - len(labeled),
        "macro_annotated_source_page_recall_at_k": {
            str(k): round(sum(row["source_page_recall_at_k"][str(k)] for row in labeled) / len(labeled), 6)
            for k in KS
        },
        "mean_reciprocal_first_relevant_page_rank": round(sum(
            row["reciprocal_first_relevant_rank"] for row in labeled
        ) / len(labeled), 6),
        "answer_truthfulness": "NOT_MEASURED",
        "answer_correctness": "NOT_MEASURED",
        "financial_semantic_correctness": "NOT_MEASURED",
        "claim_citation_support": "NOT_MEASURED",
        "answer_coverage": "NOT_MEASURED",
        "abstention_quality": "NOT_MEASURED",
        "independent_holdout_quality": "NOT_MEASURED",
        "interpretation": (
            "Page recall is over explicitly author-curated source pages from previously inspected "
            "development examples, not exhaustive evidence spans. It is NOT general retrieval recall, "
            "financial truthfulness, answer accuracy, or independent out-of-sample qualification. "
            "Page 22 may be repeated in separate chunks; distinct page hits count once."
        ),
        "research_publication": "BLOCKED",
        "cases": scored,
    }


def _write_private_new(path: Path, payload: dict[str, Any]) -> None:
    out = path.expanduser().resolve()
    if out == ROOT or ROOT in out.parents:
        raise ValueError("EVALUATION_OUTPUT_INSIDE_REPOSITORY_PROHIBITED")
    # Do not clobber another experiment or follow a symlink from a previous run.
    if path.is_symlink() or path.exists():
        raise ValueError("EVALUATION_OUTPUT_ALREADY_EXISTS")
    if not out.parent.is_dir():
        raise ValueError("EVALUATION_OUTPUT_PARENT_MISSING")
    body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("capture", help="Label-blind retrieval capture; needs verified local PDF")
    c.add_argument("--pdf", type=Path, required=True)
    c.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("score", help="Offline author-curated page-level diagnostic; no PDF/model")
    s.add_argument("--trace", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    questions, question_sha = load_questions()
    if args.command == "capture":
        result = capture(args.pdf.expanduser(), questions, question_sha)
    else:
        # References are never loaded or imported in capture.
        trace, _ = _read_json(args.trace.expanduser())
        references, reference_sha = load_references()
        result = score(trace, questions, question_sha, references, reference_sha)
    _write_private_new(args.out, result)
    print("PASS:", args.command, "completed; private output:", args.out.expanduser())
    if args.command == "score":
        print("Labeled development questions:", result["author_curated_page_labeled_questions"])
        print("Unannotated / not measured:", result["unannotated_questions_not_scored"])
        print("Macro source-page recall@k:", result["macro_annotated_source_page_recall_at_k"])
        print("Answer truthfulness:", result["answer_truthfulness"])
        print("Independent holdout:", result["independent_holdout_quality"])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        sys.exit("STOP: " + str(exc))
