"""M121A: offline diagnostic of bounded question-to-source routing.

Author-designed development cases, NOT independent semantic ground truth.
No provider calls, PDF reads, evaluation labels in runtime, or publication.
This does not measure how well the LLM understands natural language.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from typing import Callable

CORPUS = Path(__file__).with_name("question_scope_cases_v1.json")
KINDS = {"CONSOLIDATED_REVENUE", "INNOVATIVE_SHARE_OF_DRUG_SALES"}


def load_cases(path: Path = CORPUS) -> tuple[str, list[dict]]:
    raw = path.read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict) or (
        data.get("schema_version") != "frp-question-scope-diagnostic-v1"
        or data.get("corpus_type") != "AUTHOR_DESIGNED_OFFLINE_DEVELOPMENT"
        or data.get("runtime_import_prohibited") is not True
    ):
        raise ValueError("QUESTION_SCOPE_CORPUS_IDENTITY_INVALID")
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("QUESTION_SCOPE_CASES_INVALID")
    ids: set[str] = set()
    for case in cases:
        if (not isinstance(case, dict)
            or set(case) != {"id", "family", "question", "expected_kind"}
            or not all(
                isinstance(case[k], str) and case[k].strip()
                for k in ("id", "family", "question")
            )
            or (case["expected_kind"] is not None
                and case["expected_kind"] not in KINDS)
            or case["id"] in ids):
            raise ValueError("QUESTION_SCOPE_CASE_SHAPE_INVALID")
        ids.add(case["id"])
    return sha256(raw).hexdigest(), cases


def evaluate(
    cases: list[dict],
    classify: Callable[[str], str | None],
) -> dict:
    """Measure eligibility, not financial correctness or semantic approval."""
    counts = Counter(c["family"] for c in cases)
    false_admits: list[str] = []
    false_withholds: list[str] = []
    wrong_routes: list[str] = []
    admitted = 0
    supported = 0
    by_family: dict[str, dict] = {}

    for case in cases:
        expected = case["expected_kind"]
        actual = classify(case["question"])
        if actual is not None and actual not in KINDS:
            raise ValueError("UNKNOWN_ROUTER_KIND")
        supported += expected is not None
        admitted += actual is not None
        family = case["family"]
        family_result = by_family.setdefault(
            family,
            {"cases": 0, "false_admits": 0, "false_withholds": 0,
             "wrong_routes": 0},
        )
        family_result["cases"] += 1
        if expected is None and actual is not None:
            false_admits.append(case["id"])
            family_result["false_admits"] += 1
        elif expected is not None and actual is None:
            false_withholds.append(case["id"])
            family_result["false_withholds"] += 1
        elif expected is not None and actual != expected:
            wrong_routes.append(case["id"])
            family_result["wrong_routes"] += 1

    return {
        "evaluation_kind": "AUTHOR_DESIGNED_OFFLINE_ROUTING_DIAGNOSTIC",
        "status": "ROUTING_DIAGNOSTIC_ONLY",
        "case_count": len(cases),
        "family_counts": dict(sorted(counts.items())),
        "expected_supported_cases": supported,
        "router_admitted_cases": admitted,
        "false_admit_ids": false_admits,
        "false_withhold_ids": false_withholds,
        "wrong_route_ids": wrong_routes,
        "by_family": dict(sorted(by_family.items())),
        "llm_intent_accuracy": "NOT_MEASURED",
        "retrieval_recall": "NOT_MEASURED",
        "citation_validity": "NOT_MEASURED",
        "financial_semantic_correctness": "NOT_MEASURED",
        "independent_reference_quality": "NOT_AVAILABLE",
        "research_publication": "BLOCKED",
    }


def main() -> None:
    # Import only when executed explicitly as an offline diagnostic.
    # Do not import this corpus in source routes or model prompts.
    from app.modules.financial_report_analyst import live_question_intent
    digest, cases = load_cases()
    result = evaluate(cases, live_question_intent.supported_question_kind)
    result["corpus_sha256"] = digest
    result["router_source_sha256"] = sha256(
        Path(live_question_intent.__file__).read_bytes()
    ).hexdigest()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
