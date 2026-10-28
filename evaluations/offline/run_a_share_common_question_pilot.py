#!/usr/bin/env python3
"""M130-B4A strictly offline cross-issuer DEVELOPMENT capture and blind review template.

No reference labels/answers are loaded by capture. No models, networks, GT,
trading, financial answer generation, report publication or app storage.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = Path(__file__).with_name("a_share_common_questions_dev_v1.json")
CACHE = Path.home() / ".cache/frp-a-share-source-pilot"
MANIFEST = CACHE / "m130-b1/source_manifest.json"
HENGRUI_PDF = Path.home() / ".cache/frp-cn-table-pilot/sources/600276/2026H1/source.pdf"
ORIGIN = "https://github.com/WAWQAQMAKABAKA/financial-research-platform.git"
SCHEMA = "frp-m130-b4-a-share-common-questions-dev-v1"
TRACE_SCHEMA = "frp-m130-b4-label-blind-capture-v1"
FIELDS = (
    "case_id", "ticker", "document_id", "source_sha256", "source_url",
    "question", "answerability", "relevant_pdf_pages", "contrast_pdf_pages",
    "evidence_note", "reviewer", "reviewed_at",
)


def digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def load_questions(path: Path = QUESTIONS) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    obj = json.loads(raw)
    if not isinstance(obj, dict) or (
        obj.get("schema_version") != SCHEMA
        or obj.get("corpus_type") != "AUTHOR_CURATED_CROSS_ISSUER_DEVELOPMENT_NOT_INDEPENDENT_HOLDOUT"
        or obj.get("scope") != "SSE_SZSE_A_SHARES_2026H1"
        or obj.get("question_count") != 30
        or obj.get("source_count") != 3
        or obj.get("financial_answer_ground_truth") != "NONE"
        or obj.get("evidence_page_annotations") != "NONE"
        or obj.get("answerability_labels") != "NONE"
        or obj.get("research_publication") != "BLOCKED"
    ):
        raise ValueError("QUESTION_MANIFEST_PROVENANCE_INVALID")
    instant = datetime.fromisoformat(obj["as_of"])
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("QUESTION_AS_OF_NAIVE")
    sources = obj.get("sources")
    cases = obj.get("cases")
    if (not isinstance(sources, list) or len(sources) != 3
            or not isinstance(cases, list) or len(cases) != 30):
        raise ValueError("SOURCE_OR_CASE_COUNT_INVALID")
    by_ticker = {item["ticker"]: item for item in sources}
    if len(by_ticker) != 3 or set(by_ticker) != {"600276", "600519", "000651"}:
        raise ValueError("SOURCE_TICKER_SET_INVALID")
    for source in sources:
        if (source.get("report_key") != source["ticker"] + "-" + source["report_period"]
                or source.get("report_period") != "2026H1"
                or not re.fullmatch("[0-9a-f]{64}", source.get("source_sha256", ""))
                or not re.fullmatch("[0-9a-f]{64}", source.get("canonical_sha256", ""))
                or type(source.get("pdf_pages")) is not int or source["pdf_pages"] < 1):
            raise ValueError("SOURCE_BINDING_INVALID")
    seen: set[str] = set()
    counts = {key: 0 for key in by_ticker}
    for row in cases:
        if (not isinstance(row, dict) or set(row) != {"case_id", "ticker", "family", "question"}
                or row["ticker"] not in by_ticker
                or not re.fullmatch(r"A\d{6}-\d{2}", row["case_id"])
                or not row["case_id"].startswith("A" + row["ticker"] + "-")
                or row["case_id"] in seen
                or not isinstance(row["family"], str) or not row["family"]
                or not isinstance(row["question"], str) or not row["question"].strip()
                or len(row["question"]) > 240
                or len(row["question"].encode("utf-8")) > 800):
            raise ValueError("CASE_ID_OR_QUESTION_INVALID")
        seen.add(row["case_id"])
        counts[row["ticker"]] += 1
    if set(counts.values()) != {10}:
        raise ValueError("QUESTION_ALLOCATION_INVALID")
    return obj, digest(raw)


def git(*args: str) -> str:
    p = subprocess.run(("git", *args), cwd=ROOT, capture_output=True, text=True, timeout=15)
    if p.returncode:
        raise ValueError("LOCAL_GIT_PREFLIGHT_FAILED:" + " ".join(args))
    return p.stdout.rstrip("\n")


def repo_state() -> dict[str, str]:
    if (git("rev-parse", "--show-toplevel") != str(ROOT)
            or git("branch", "--show-current") != "main"
            or git("remote", "get-url", "origin") != ORIGIN):
        raise ValueError("REPOSITORY_IDENTITY_INVALID")
    changed = set(git("status", "--short", "--untracked-files=all").splitlines())
    expected_new = {
        "?? evaluations/offline/" + name for name in (
            "M130_B4_COMMON_QUESTION_PILOT.md",
            "a_share_common_questions_dev_v1.json",
            "run_a_share_common_question_pilot.py",
            "test_a_share_common_question_pilot.py",
        )
    }
    if changed not in (set(), expected_new):
        raise ValueError("REPOSITORY_NOT_CLEAN_OR_EXPECTED_B4_ONLY")
    return {"git_head": git("rev-parse", "HEAD"), "git_branch": "main",
            "working_tree_state": "CLEAN" if not changed else "B4_NEW_FILES_ONLY"}


def check_output(path: Path) -> Path:
    if path.is_symlink() or path.exists():
        raise ValueError("PRIVATE_OUTPUT_ALREADY_EXISTS")
    target = path.expanduser().resolve()
    home_cache = (Path.home() / ".cache").resolve()
    if home_cache not in target.parents or ROOT == target or ROOT in target.parents:
        raise ValueError("PRIVATE_OUTPUT_MUST_BE_IN_USER_CACHE_OUTSIDE_REPO")
    if not target.parent.is_dir():
        raise ValueError("PRIVATE_OUTPUT_PARENT_MISSING")
    return target


def exclusive_write(path: Path, data: bytes) -> None:
    target = check_output(path)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)


def review_rows(questions: dict[str, Any]) -> list[dict[str, str]]:
    sources = {s["ticker"]: s for s in questions["sources"]}
    return [{
        "case_id": c["case_id"], "ticker": c["ticker"],
        "document_id": sources[c["ticker"]]["document_id"],
        "source_sha256": sources[c["ticker"]]["source_sha256"],
        "source_url": sources[c["ticker"]]["source_url"],
        "question": c["question"], "answerability": "", "relevant_pdf_pages": "",
        "contrast_pdf_pages": "", "evidence_note": "", "reviewer": "", "reviewed_at": "",
    } for c in questions["cases"]]


def make_template(questions: dict[str, Any]) -> bytes:
    import io
    f = io.StringIO(newline="")
    writer = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(review_rows(questions))
    return f.getvalue().encode("utf-8-sig")


def qualified_documents(questions: dict[str, Any], h_pdf: Path, instant: datetime):
    # Live dependency only used in label-blind capture. No reference labels loaded.
    from app.evidence.contracts import SourceDocument
    from app.evidence.pdf_canonicalizer import canonicalize_pdf
    from app.modules.financial_report_analyst import revenue_scope

    raw = MANIFEST.read_bytes()
    private = json.loads(raw)
    if (private.get("schema_version") != "frp-m130-b1-a-share-source-qualification-v1"
            or private.get("scope") != "MAINLAND_A_SHARES_SSE_AND_SZSE_ONLY"
            or private.get("reference_answers") != "NONE"
            or private.get("evidence_annotations") != "NONE"
            or private.get("report_count") != 2):
        raise ValueError("PRIVATE_SOURCE_MANIFEST_INVALID")
    indexed = {r["ticker"]: r for r in private["reports"]}
    if set(indexed) != {"600519", "000651"}:
        raise ValueError("PRIVATE_SOURCE_SET_INVALID")
    results = {}
    for meta in questions["sources"]:
        ticker = meta["ticker"]
        if ticker == "600276":
            source = revenue_scope.SOURCE
            path = h_pdf.expanduser().resolve()
            if any(getattr(source, name) != meta[name] for name in (
                "ticker", "report_period", "document_id", "source_url",
                "source_sha256", "canonical_sha256"
            )) or source.published_on.isoformat() != meta["published_on"]:
                raise ValueError("HENGRUI_SOURCE_CONTRACT_INVALID")
        else:
            record = indexed[ticker]
            for field in ("ticker", "document_id", "source_url", "report_period",
                          "published_on", "source_sha256", "canonical_sha256", "pdf_pages"):
                if record.get(field) != meta[field]:
                    raise ValueError("PRIVATE_SOURCE_BINDING_CHANGED:" + ticker + ":" + field)
            path = (MANIFEST.parent / record["filename"]).resolve()
            if MANIFEST.parent.resolve() not in path.parents:
                raise ValueError("PRIVATE_SOURCE_PATH_ESCAPE")
            source = SourceDocument(
                document_id=meta["document_id"], ticker=ticker, report_period="2026H1",
                source_url=meta["source_url"], published_on=date.fromisoformat(meta["published_on"]),
                source_sha256=meta["source_sha256"], canonical_sha256=meta["canonical_sha256"],
            )
        if not path.is_file() or path.is_symlink() or digest(path.read_bytes()) != source.source_sha256:
            raise ValueError("ORIGINAL_PDF_MISSING_OR_HASH_INVALID:" + ticker)
        source.require_available(instant)
        document = canonicalize_pdf(
            document_id=source.document_id, pdf_path=path,
            expected_source_sha256=source.source_sha256,
        )
        if (document.canonical_sha256 != source.canonical_sha256
                or len(document.pages) != meta["pdf_pages"]):
            raise ValueError("CANONICAL_SOURCE_MISMATCH:" + ticker)
        results[ticker] = (source, document)
    return results, digest(raw)


def capture(questions: dict[str, Any], manifest_sha: str, h_pdf: Path) -> dict[str, Any]:
    from app.modules.financial_report_analyst import canonical_retrieval

    as_of = datetime.fromisoformat(questions["as_of"])
    documents, private_sha = qualified_documents(questions, h_pdf, as_of)
    out = []
    for case in questions["cases"]:
        source, doc = documents[case["ticker"]]
        pkt = canonical_retrieval.retrieve_from_canonical(source, doc, case["question"], as_of=as_of)
        if (pkt.get("question") != case["question"]
                or pkt.get("status") not in ("RETRIEVAL_CANDIDATES_READY", "WITHHELD")
                or pkt.get("report_key") != f"{source.ticker}-{source.report_period}"
                or pkt.get("document_id") != source.document_id
                or pkt.get("source_sha256") != source.source_sha256
                or pkt.get("canonical_sha256") != source.canonical_sha256
                or pkt.get("source_url") != source.source_url
                or pkt.get("as_of") != as_of.isoformat()
                or pkt.get("research_publication") != "BLOCKED"
                or pkt.get("financial_semantic_review") != "NOT_PERFORMED"
                or pkt.get("report_storage") != "NOT_PERSISTED"
                or pkt.get("retrieval_review") != "CANDIDATES_NOT_RELEVANCE_QUALIFIED"):
            raise ValueError("RETRIEVAL_BOUNDARY_OR_SOURCE_MISMATCH:" + case["case_id"])
        hits = pkt.get("evidence")
        if not isinstance(hits, list) or len(hits) > 5:
            raise ValueError("RETRIEVAL_HIT_COUNT_INVALID:" + case["case_id"])
        if (pkt["status"] == "WITHHELD") != (len(hits) == 0):
            raise ValueError("RETRIEVAL_STATUS_HITS_INVALID:" + case["case_id"])
        seen = set()
        records = []
        for rank, item in enumerate(hits, 1):
            page = item.get("source_page")
            start, end = item.get("canonical_start"), item.get("canonical_end")
            excerpt, eid = item.get("source_excerpt"), item.get("evidence_id")
            if (type(page) is not int or page not in range(1, len(doc.pages) + 1)
                    or type(start) is not int or type(end) is not int
                    or not doc.pages[page - 1].content_start <= start < end <= doc.pages[page - 1].content_end
                    or not isinstance(excerpt, str) or doc.canonical_text[start:end] != excerpt
                    or not isinstance(eid, str) or not re.fullmatch("[0-9a-f]{64}", eid)
                    or eid in seen
                    or item.get("review_scope") != "VERIFIED_CANONICAL_TEXT_SPAN_ONLY"):
                raise ValueError("CANONICAL_SPAN_INTEGRITY_INVALID:" + case["case_id"])
            expected_eid = digest("|".join((
                canonical_retrieval.RETRIEVER_VERSION, source.document_id,
                source.canonical_sha256, str(page), str(start), str(end), excerpt,
            )).encode("utf-8"))
            if eid != expected_eid:
                raise ValueError("EVIDENCE_ID_INVALID:" + case["case_id"])
            seen.add(eid)
            records.append({
                "rank": rank, "pdf_page": page, "evidence_id": eid,
                "canonical_start": start, "canonical_end": end,
                "excerpt_sha256": digest(excerpt.encode("utf-8")), "source_excerpt": excerpt,
            })
        out.append({
            "case_id": case["case_id"], "ticker": case["ticker"],
            "family": case["family"], "question": case["question"],
            "document_id": source.document_id, "report_key": pkt["report_key"],
            "status": pkt["status"], "retrieval_id": pkt["retrieval_id"],
            "retriever_version": pkt["retriever_version"],
            "ranking_version": pkt["ranking_version"], "hits": records,
        })
    return {
        "schema_version": TRACE_SCHEMA,
        "evaluation_kind": "LABEL_BLIND_CROSS_ISSUER_DEVELOPMENT_NOT_RECALL_OR_HOLDOUT",
        "scope": questions["scope"], "as_of": questions["as_of"],
        "question_manifest_sha256": manifest_sha,
        "private_source_manifest_sha256": private_sha,
        **repo_state(),
        "retriever_source_sha256": digest((ROOT / "services/api/app/modules/financial_report_analyst/canonical_retrieval.py").read_bytes()),
        "capture_runner_sha256": digest(Path(__file__).read_bytes()),
        "source_bindings": questions["sources"],
        "case_count": len(out), "cases": out,
        "source_page_recall_at_k": "NOT_MEASURED_NO_INDEPENDENT_PAGE_LABELS",
        "financial_answer_truthfulness": "NOT_MEASURED",
        "financial_semantic_correctness": "NOT_MEASURED",
        "independent_holdout_quality": "NOT_MEASURED",
        "research_publication": "BLOCKED", "report_storage": "NOT_PERSISTED",
    }


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    sub = cli.add_subparsers(dest="cmd", required=True)
    temp = sub.add_parser("review-template", help="Blank independent source-page review form; NO retrieval results read")
    temp.add_argument("--out", type=Path, required=True)
    cap = sub.add_parser("capture", help="Label-blind retrieval trace with verified original PDFs")
    cap.add_argument("--out", type=Path, required=True)
    cap.add_argument("--hengrui-pdf", type=Path, default=HENGRUI_PDF)
    args = cli.parse_args(argv)
    state = repo_state()
    questions, manifest_sha = load_questions()
    check_output(args.out)
    print("=== M130-B4A: OFFLINE SOURCE AND REPO PREFLIGHT ===", flush=True)
    print("PASS:", state["git_branch"], state["git_head"], state["working_tree_state"], flush=True)
    if args.cmd == "review-template":
        exclusive_write(args.out, make_template(questions))
        print("PASS: blank independent review template created for 30 questions", flush=True)
        print("LABELS: NONE; RETRIEVAL OUTPUT: NOT READ", flush=True)
    else:
        result = capture(questions, manifest_sha, args.hengrui_pdf)
        exclusive_write(args.out, (json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        print("PASS: 30 label-blind cross-issuer retrieval cases captured", flush=True)
        print("SOURCES:", len(questions["sources"]), "CASES:", len(result["cases"]), flush=True)
        print("WITHHELD:", sum(c["status"] == "WITHHELD" for c in result["cases"]), flush=True)
        print("RECALL / TRUTHFULNESS: NOT_MEASURED", flush=True)
    print("PRIVATE OUTPUT:", args.out.expanduser(), flush=True)
    print("REPOSITORY: no writes by evaluator", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError,
            subprocess.TimeoutExpired) as err:
        sys.exit("STOP: " + str(err))
