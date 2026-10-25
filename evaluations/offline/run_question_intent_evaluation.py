"""Offline development-only scoring of external question-intent proposals.

No model calls, PDF retrieval, financial-semantic approvals, or publication.
Development labels never enter runtime code.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path

from app.modules.financial_report_analyst.question_intent import (
    QuestionIntentProposal,
)

CORPUS = Path(__file__).with_name(
    "question_understanding_cases_v1.json"
)


def load_cases(path: Path = CORPUS) -> tuple[str, list[dict]]:
    raw = path.read_bytes()
    data = json.loads(raw)

    if (
        data.get("schema_version") != "frp-question-understanding-v1"
        or data.get("corpus_type")
            != "OFFLINE_DEVELOPMENT_NOT_PROTECTED_GT"
        or data.get("runtime_import_prohibited") is not True
    ):
        raise ValueError("QUESTION_CORPUS_PROVENANCE_INVALID")

    cases = data["cases"]

    if (
        not isinstance(cases, list)
        or not cases
        or len({c["id"] for c in cases}) != len(cases)
    ):
        raise ValueError("QUESTION_CASE_IDS_INVALID")

    return sha256(raw).hexdigest(), cases


def load_predictions(
    path: Path,
    cases: list[dict],
) -> dict[str, QuestionIntentProposal]:
    known = {c["id"]: c for c in cases}
    results = {}

    for line in path.read_text(
        encoding="utf-8"
    ).splitlines():
        if not line.strip():
            continue

        item = json.loads(line)

        if (
            not isinstance(item, dict)
            or set(item) != {"case_id", "proposal"}
        ):
            raise ValueError("PREDICTION_RECORD_SHAPE_INVALID")

        key = item["case_id"]

        if not isinstance(key, str) or key not in known:
            raise ValueError("UNKNOWN_QUESTION_CASE")

        if key in results:
            raise ValueError("DUPLICATE_QUESTION_PREDICTION")

        proposal = QuestionIntentProposal.model_validate(
            item["proposal"]
        )

        if proposal.question != known[key]["question"]:
            raise ValueError(
                "PREDICTION_QUESTION_IDENTITY_MISMATCH"
            )

        results[key] = proposal

    return results


def evaluate(
    cases: list[dict],
    predictions: dict[str, QuestionIntentProposal] | None,
) -> dict:
    categories = dict(sorted(
        Counter(c["family"] for c in cases).items()
    ))

    result = {
        "evaluation_kind":
            "AUTHOR_DESIGNED_OFFLINE_DEVELOPMENT",
        "case_count": len(cases),
        "categories": categories,
        "reference_quality":
            "NOT_INDEPENDENT_FINANCIAL_GT",
        "research_publication": "BLOCKED",
        "evidence_recall": "NOT_MEASURED",
        "financial_semantic_correctness": "NOT_MEASURED",
    }

    if predictions is None:
        return {
            **result,
            "status": "NO_MODEL_PREDICTIONS",
            "operation_accuracy": "NOT_MEASURED",
            "denominator_accuracy": "NOT_MEASURED",
            "ambiguity_flag_rate": "NOT_MEASURED",
        }

    op_total = op_correct = 0
    den_total = den_correct = 0
    ambiguity_total = ambiguity_flagged = 0

    missing = []
    by_family = defaultdict(
        lambda: {
            "evaluated": 0,
            "operation_correct": 0,
        }
    )

    for case in cases:
        p = predictions.get(case["id"])

        if p is None:
            missing.append(case["id"])
            continue

        family = case["family"]
        by_family[family]["evaluated"] += 1

        op_total += 1
        correct = (
            p.operation_candidate.value
            == case["reference_intent"]["operation"]
        )

        op_correct += correct
        by_family[family]["operation_correct"] += correct

        # A null development label means "not scored",
        # NOT proof that a denominator is absent.
        expected_denominator = (
            case["reference_intent"]["denominator"]
        )

        if expected_denominator is not None:
            den_total += 1
            den_correct += (
                p.denominator_candidate
                == expected_denominator
            )

        if family == "ambiguity":
            ambiguity_total += 1
            ambiguity_flagged += bool(p.unresolved)

    return {
        **result,
        "status": "DEVELOPMENT_PROPOSALS_SCORED",
        "proposals_scored": op_total,
        "missing_prediction_ids": missing,
        "operation_accuracy": {
            "correct": op_correct,
            "evaluated": op_total,
        },
        "denominator_accuracy": {
            "correct": den_correct,
            "labelled": den_total,
        },
        "ambiguity_flag_rate": {
            "flagged": ambiguity_flagged,
            "evaluated": ambiguity_total,
        },
        "operation_by_family": dict(
            sorted(by_family.items())
        ),
        "warning": (
            "Reference labels are author-designed and "
            "may need semantic adjudication. Scores "
            "do not qualify financial answers."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--predictions",
        type=Path,
        default=None,
    )
    args = parser.parse_args()

    digest, cases = load_cases()

    predictions = (
        load_predictions(args.predictions, cases)
        if args.predictions
        else None
    )

    result = evaluate(cases, predictions)
    result["corpus_sha256"] = digest

    print(json.dumps(
        result,
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
