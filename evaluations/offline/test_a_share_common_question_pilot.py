"""M130-B4A offline-only guard tests; no network, benchmark labels or PDF requirement."""
from __future__ import annotations

import csv
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_a_share_common_question_pilot as pilot


class CommonQuestionPilotContracts(unittest.TestCase):
    def setUp(self):
        self.obj, self.manifest_sha = pilot.load_questions()

    def test_question_manifest_is_30_across_three_a_share_sources(self):
        self.assertEqual(len(self.obj["cases"]), 30)
        self.assertEqual(len(self.obj["sources"]), 3)
        self.assertEqual(len(set(c["case_id"] for c in self.obj["cases"])), 30)
        self.assertEqual({c["ticker"] for c in self.obj["cases"]}, {"600276", "600519", "000651"})
        self.assertEqual(self.obj["financial_answer_ground_truth"], "NONE")
        self.assertEqual(self.obj["evidence_page_annotations"], "NONE")
        self.assertEqual(self.obj["answerability_labels"], "NONE")
        self.assertEqual(len(self.manifest_sha), 64)

    def test_not_holdout_and_no_premature_claims(self):
        self.assertIn("DEVELOPMENT_NOT_INDEPENDENT_HOLDOUT", self.obj["corpus_type"])
        self.assertEqual(self.obj["research_publication"], "BLOCKED")
        self.assertFalse(any("answer" in c or "relevant_pages" in c for c in self.obj["cases"]))

    def test_duplicate_id_rejected(self):
        bad = json.loads(json.dumps(self.obj))
        bad["cases"][1]["case_id"] = bad["cases"][0]["case_id"]
        self._expect_bad(bad)

    def test_modified_source_hash_rejected(self):
        bad = json.loads(json.dumps(self.obj))
        bad["sources"][0]["source_sha256"] = "not-sha"
        self._expect_bad(bad)

    def test_missing_case_rejected(self):
        bad = json.loads(json.dumps(self.obj))
        bad["cases"].pop()
        self._expect_bad(bad)

    def test_naive_asof_rejected(self):
        bad = json.loads(json.dumps(self.obj))
        bad["as_of"] = "2026-10-27T16:00:00"
        self._expect_bad(bad)

    def test_review_form_has_no_retrieval_hints_or_labels(self):
        raw = pilot.make_template(self.obj)
        form = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        self.assertEqual(len(form), 30)
        self.assertEqual(set(form[0]), set(pilot.FIELDS))
        self.assertNotIn("retrieved_pages", pilot.FIELDS)
        self.assertNotIn("model_answer", pilot.FIELDS)
        for row in form:
            for field in ("answerability", "relevant_pdf_pages", "contrast_pdf_pages",
                          "evidence_note", "reviewer", "reviewed_at"):
                self.assertEqual(row[field], "")
            self.assertEqual(len(row["source_sha256"]), 64)

    def test_output_inside_repo_rejected(self):
        with self.assertRaisesRegex(ValueError, "PRIVATE_OUTPUT_MUST_BE"):
            pilot.check_output(pilot.ROOT / "should_not_write.json")

    def test_existing_output_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path.home() / ".cache") as td:
            path = Path(td) / "existing.csv"
            path.write_text("unchanged", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "ALREADY_EXISTS"):
                pilot.exclusive_write(path, b"overwrite")
            self.assertEqual(path.read_text(encoding="utf-8"), "unchanged")

    def test_reference_annotations_are_not_accessible_from_capture(self):
        import inspect
        source = inspect.getsource(pilot.capture)
        self.assertNotIn("relevant_pdf_pages", source)
        self.assertNotIn("review_rows(", source)
        self.assertNotIn("score(", source)

    def _expect_bad(self, obj):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "cases.json"
            path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(ValueError):
                pilot.load_questions(path)


if __name__ == "__main__":
    unittest.main()
