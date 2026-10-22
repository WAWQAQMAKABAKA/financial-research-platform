"""Tests for evaluation bookkeeping, not tests that force the gate to pass."""
from datetime import datetime
from pathlib import Path
import json
import tempfile
import unittest

import run_semantic_baseline as baseline


class OfflineEvaluationInvariants(unittest.TestCase):
    def test_source_corpus_is_synthetic_and_separate(self):
        meta, cases = baseline._load_cases()
        self.assertEqual(len(meta["corpus_sha256"]), 64)
        self.assertGreaterEqual(len(cases), 12)
        self.assertTrue(all("expected" in case and "rationale" in case for case in cases))
        self.assertTrue(all("source_url" not in case for case in cases))

    def test_baseline_records_misses_instead_of_faking_success(self):
        result = baseline.evaluate_synthetic()
        by_id = {r["id"]: r for r in result["cases"]}
        self.assertEqual(by_id["S13"]["expected"], "REJECT")
        self.assertEqual(by_id["S14"]["expected"], "REJECT")
        # Never rewrite expected labels to match a future Reviewer improvement.
        # The evaluator must faithfully disclose whatever the implementation did.
        self.assertTrue(all(row["match"] == (row["actual"] == row["expected"])
                            for row in result["cases"]))
        self.assertEqual(result["mismatched_case_ids"],
                         [row["id"] for row in result["cases"] if not row["match"]])
        self.assertEqual(result["research_publication"], "BLOCKED")
        self.assertEqual(result["unexpected_financial_admissions"], 0)

    def test_pit_calendar_edges_are_not_semantic_admission(self):
        result = baseline.evaluate_synthetic()
        by_id = {r["id"]: r for r in result["cases"]}
        self.assertEqual(by_id["P01"]["actual"], "BLOCK")
        self.assertEqual(by_id["P02"]["actual"], "PIT_AVAILABLE")
        self.assertTrue(by_id["P01"]["match"] and by_id["P02"]["match"])
        self.assertEqual(result["research_publication"], "BLOCKED")

    def test_corpus_integrity_failure_is_not_a_pass(self):
        payload = json.loads(baseline.CORPUS.read_text())
        payload["cases"][0]["id"] = payload["cases"][1]["id"]
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/"bad.json"
            p.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError,"DUPLICATE_OR_EMPTY"):
                baseline._load_cases(p)


if __name__ == "__main__":
    unittest.main()
