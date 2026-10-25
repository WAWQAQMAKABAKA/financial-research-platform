"""Synthetic scoring integrity tests, not model-quality assertions."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.modules.financial_report_analyst.question_intent import (
    QuestionIntentProposal,
)
from run_question_intent_evaluation import (
    evaluate,
    load_predictions,
)


CASES = [
    {
        "id": "T1",
        "family": "direct_disclosure",
        "question": "What was the revenue?",
        "reference_intent": {
            "operation": "LOOKUP",
            "denominator": None,
        },
    },
    {
        "id": "T2",
        "family": "denominator_semantics",
        "question": "What portion of drug sales?",
        "reference_intent": {
            "operation": "RATIO",
            "denominator": "drug_sales_revenue",
        },
    },
    {
        "id": "T3",
        "family": "ambiguity",
        "question": "What was the share?",
        "reference_intent": {
            "operation": "RATIO",
            "denominator": None,
        },
    },
]


def prediction(case_id, question, operation, **kwargs):
    return {
        "case_id": case_id,
        "proposal": {
            "question": question,
            "operation_candidate": operation,
            **kwargs,
        },
    }


class QuestionIntentScoringIntegrity(unittest.TestCase):
    def test_no_predictions_never_claims_accuracy(self):
        result = evaluate(CASES, None)

        self.assertEqual(
            result["status"],
            "NO_MODEL_PREDICTIONS",
        )
        self.assertEqual(
            result["operation_accuracy"],
            "NOT_MEASURED",
        )

    def test_wrong_denominator_and_partial_coverage(self):
        candidates = {
            "T1": QuestionIntentProposal.model_validate(
                prediction(
                    "T1",
                    CASES[0]["question"],
                    "LOOKUP",
                )["proposal"]
            ),
            "T2": QuestionIntentProposal.model_validate(
                prediction(
                    "T2",
                    CASES[1]["question"],
                    "RATIO",
                    denominator_candidate="consolidated_revenue",
                )["proposal"]
            ),
        }

        result = evaluate(CASES, candidates)

        self.assertEqual(
            result["operation_accuracy"],
            {"correct": 2, "evaluated": 2},
        )
        self.assertEqual(
            result["denominator_accuracy"],
            {"correct": 0, "labelled": 1},
        )
        self.assertEqual(
            result["missing_prediction_ids"],
            ["T3"],
        )
        self.assertEqual(
            result["evidence_recall"],
            "NOT_MEASURED",
        )

    def test_ambiguity_is_reported_separately(self):
        item = QuestionIntentProposal.model_validate(
            prediction(
                "T3",
                CASES[2]["question"],
                "RATIO",
                unresolved=["Missing denominator"],
            )["proposal"]
        )

        result = evaluate(CASES, {"T3": item})

        self.assertEqual(
            result["ambiguity_flag_rate"],
            {"flagged": 1, "evaluated": 1},
        )

    def test_duplicate_or_wrong_question_fails(self):
        p = prediction(
            "T1",
            CASES[0]["question"],
            "LOOKUP",
        )

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "pred.jsonl"

            path.write_text(
                json.dumps(p) + "\n"
                + json.dumps(p) + "\n"
            )

            with self.assertRaisesRegex(
                ValueError,
                "DUPLICATE",
            ):
                load_predictions(path, CASES)

            p["proposal"]["question"] = (
                "Different customer question"
            )

            path.write_text(json.dumps(p) + "\n")

            with self.assertRaisesRegex(
                ValueError,
                "IDENTITY",
            ):
                load_predictions(path, CASES)

    def test_forged_publication_rejected(self):
        p = prediction(
            "T1",
            CASES[0]["question"],
            "LOOKUP",
            research_publication="PUBLISHED",
        )

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "pred.jsonl"
            path.write_text(json.dumps(p) + "\n")

            with self.assertRaises(Exception):
                load_predictions(path, CASES)


if __name__ == "__main__":
    unittest.main()
