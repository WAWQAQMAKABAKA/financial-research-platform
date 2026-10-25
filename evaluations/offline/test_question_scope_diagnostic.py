"""M121A diagnostic harness integrity tests; no model or original PDF."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from run_question_scope_diagnostic import evaluate, load_cases


class RoutingDiagnosticIntegrity(unittest.TestCase):
    def test_checked_in_cases_have_valid_author_designed_identity(self):
        digest, cases = load_cases()
        self.assertEqual(len(digest), 64)
        self.assertEqual(len(cases), 16)
        self.assertTrue(any(c["family"] == "multi_intent" for c in cases))
        self.assertTrue(any(c["expected_kind"] is not None for c in cases))

    def test_reports_false_admit_and_false_withhold_separately(self):
        cases = [
            {"id": "a", "family": "single", "question": "a",
             "expected_kind": "CONSOLIDATED_REVENUE"},
            {"id": "b", "family": "multi", "question": "b",
             "expected_kind": None},
            {"id": "c", "family": "single", "question": "c",
             "expected_kind": "INNOVATIVE_SHARE_OF_DRUG_SALES"},
            {"id": "d", "family": "single", "question": "d",
             "expected_kind": "CONSOLIDATED_REVENUE"},
        ]
        outcomes = {
            "a": None,
            "b": "CONSOLIDATED_REVENUE",
            "c": "CONSOLIDATED_REVENUE",
            "d": "CONSOLIDATED_REVENUE",
        }
        result = evaluate(cases, outcomes.get)
        self.assertEqual(result["expected_supported_cases"], 3)
        self.assertEqual(result["router_admitted_cases"], 3)
        self.assertEqual(result["false_admit_ids"], ["b"])
        self.assertEqual(result["false_withhold_ids"], ["a"])
        self.assertEqual(result["wrong_route_ids"], ["c"])
        self.assertEqual(result["llm_intent_accuracy"], "NOT_MEASURED")
        self.assertEqual(result["financial_semantic_correctness"], "NOT_MEASURED")
        self.assertEqual(result["research_publication"], "BLOCKED")

    def test_unknown_classifier_kind_is_not_silently_counted(self):
        cases = [{"id": "a", "family": "single", "question": "a",
                  "expected_kind": None}]
        with self.assertRaisesRegex(ValueError, "UNKNOWN_ROUTER_KIND"):
            evaluate(cases, lambda _: "MADE_UP_KIND")

    def test_forged_corpus_label_or_duplicate_id_rejected(self):
        _, cases = load_cases()
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "cases.json"
            base = {
                "schema_version": "frp-question-scope-diagnostic-v1",
                "corpus_type": "AUTHOR_DESIGNED_OFFLINE_DEVELOPMENT",
                "runtime_import_prohibited": True,
                "cases": cases[:1],
            }
            base["cases"][0]["expected_kind"] = "PUBLISHED"
            path.write_text(json.dumps(base), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "CASE_SHAPE"):
                load_cases(path)

            original = dict(cases[1])
            base["cases"] = [original, dict(original)]
            path.write_text(json.dumps(base), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "CASE_SHAPE"):
                load_cases(path)


if __name__ == "__main__":
    unittest.main()
