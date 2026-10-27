"""M130-A offline score bookkeeping tests. No model, PDF or financial GT."""
from copy import deepcopy
from hashlib import sha256
import unittest

import run_rag_retrieval_baseline as rag


def _hit(rank: int, page: int):
    excerpt = f"Synthetic source text page={page} rank={rank}"
    return {
        "rank": rank,
        "source_page": page,
        "evidence_id": sha256(f"{rank}|{page}".encode()).hexdigest(),
        "canonical_start": rank * 100,
        "canonical_end": rank * 100 + len(excerpt),
        "source_excerpt": excerpt,
        "excerpt_sha256": sha256(excerpt.encode()).hexdigest(),
    }


def _fixture():
    questions, qsha = rag.load_questions()
    references, rsha = rag.load_references()
    case_pages = {
        "D001": [56, 22, 57, 138, 60],
        "D002": [26, 22, 146, 60, 14],
        "D003": [22, 22, 57, 60, 60],
        "D004": [46, 150, 86, 80, 80],
        "D005": [80, 81, 82, 83, 84],
    }
    records = []
    for case in questions["cases"]:
        pages = case_pages[case["case_id"]]
        records.append({
            **case,
            "status": "RETRIEVAL_CANDIDATES_READY",
            "retrieval_id": sha256(case["question"].encode()).hexdigest(),
            "ranking_version": "synthetic-test-only",
            "evidence": [_hit(i, page) for i, page in enumerate(pages, 1)],
        })
    trace = {
        "schema_version": rag.CAPTURE_SCHEMA,
        "evaluation_kind": "LABEL_BLIND_OFFLINE_RETRIEVAL_CAPTURE_DEVELOPMENT",
        "question_manifest_sha256": qsha,
        "source_document_id": questions["source_binding"]["document_id"],
        "source_sha256": questions["source_binding"]["source_sha256"],
        "canonical_sha256": questions["source_binding"]["canonical_sha256"],
        "as_of": questions["as_of"],
        "git_head": "a" * 40,
        "research_publication": "BLOCKED",
        "financial_semantic_review": "NOT_PERFORMED",
        "report_storage": "NOT_PERSISTED",
        "cases": records,
    }
    return trace, questions, qsha, references, rsha


class OfflineRagScorerTests(unittest.TestCase):
    def test_annotated_page_recall_and_unannotated_not_measured(self):
        trace, questions, qsha, refs, rsha = _fixture()
        result = rag.score(trace, questions, qsha, refs, rsha)
        self.assertEqual(result["author_curated_page_labeled_questions"], 3)
        self.assertEqual(result["unannotated_questions_not_scored"], 2)
        rows = {row["case_id"]: row for row in result["cases"]}
        self.assertEqual(rows["D001"]["source_page_recall_at_k"],
                         {"1": 0.0, "3": 1.0, "5": 1.0})
        self.assertEqual(rows["D001"]["first_relevant_page_rank"], 2)
        self.assertEqual(rows["D002"]["source_page_recall_at_k"],
                         {"1": 0.333333, "3": 1.0, "5": 1.0})
        self.assertEqual(rows["D003"]["source_page_recall_at_k"],
                         {"1": 1.0, "3": 1.0, "5": 1.0})
        self.assertEqual(rows["D004"]["source_page_recall_at_k"], "NOT_MEASURED")
        self.assertEqual(result["answer_truthfulness"], "NOT_MEASURED")
        self.assertEqual(result["financial_semantic_correctness"], "NOT_MEASURED")
        self.assertEqual(result["independent_holdout_quality"], "NOT_MEASURED")
        self.assertEqual(result["research_publication"], "BLOCKED")

    def test_duplicate_page_does_not_inflate_recall(self):
        trace, questions, qsha, refs, rsha = _fixture()
        row = trace["cases"][1]
        row["evidence"] = [_hit(i, 26) for i in range(1, 6)]
        result = rag.score(trace, questions, qsha, refs, rsha)
        scored = result["cases"][1]
        self.assertEqual(scored["source_page_recall_at_k"]["5"], 0.333333)

    def test_wrong_source_hash_fail_closed(self):
        trace, questions, qsha, refs, rsha = _fixture()
        trace["canonical_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "PROVENANCE_INVALID"):
            rag.score(trace, questions, qsha, refs, rsha)

    def test_reordered_trace_fail_closed(self):
        trace, questions, qsha, refs, rsha = _fixture()
        trace["cases"].reverse()
        with self.assertRaisesRegex(ValueError, "TRACE_CASE_INVALID"):
            rag.score(trace, questions, qsha, refs, rsha)

    def test_tampered_excerpt_fail_closed(self):
        trace, questions, qsha, refs, rsha = _fixture()
        trace["cases"][0]["evidence"][0]["source_excerpt"] += " injection"
        with self.assertRaisesRegex(ValueError, "EVIDENCE_TRACE_INVALID"):
            rag.score(trace, questions, qsha, refs, rsha)

    def test_ambiguous_reference_does_not_become_answer_gt(self):
        questions, _ = rag.load_questions()
        refs, _ = rag.load_references()
        self.assertEqual(refs["annotation_scope"],
                         "SOURCE_PAGE_RELEVANCE_ONLY_NOT_FINANCIAL_ANSWER_TRUTH")
        self.assertTrue(any(x["family"] == "ambiguous_agreement_potential_value"
                            for x in questions["cases"]))
        self.assertEqual(len(refs["references"]), 3)

    def test_duplicate_question_ids_fail_closed(self):
        raw, _ = rag.load_questions()
        altered = deepcopy(raw)
        altered["cases"][1]["case_id"] = altered["cases"][0]["case_id"]
        from pathlib import Path
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "bad.json"
            file.write_text(json.dumps(altered), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "INVALID_OR_DUPLICATE"):
                rag.load_questions(file)


if __name__ == "__main__":
    unittest.main()
