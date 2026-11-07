"""M2a question route: dev-only access control and response shape."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

TOKEN = "m1-local-dev-token-0123456789abcdef"
PDF = Path(__file__).resolve().parents[3] / "data/raw/600760/2026H1/source.pdf"
URL = "/api/v1/research/reports/600760-2026H1/ask"
QUESTION = "中航沈飞2026年半年度合并利润表中营业收入是多少？"


def authorize(monkeypatch, pdf: str | None = "auto") -> None:
    monkeypatch.setenv("FRP_LOCAL_FACTS_REPORT", "1")
    monkeypatch.setenv("FRP_LOCAL_LLM_ACCESS_TOKEN", TOKEN)
    monkeypatch.delenv("FRP_ENV", raising=False)
    monkeypatch.setenv(
        "FRP_LOCAL_SOURCE_PDF_600760",
        str(PDF) if pdf == "auto" else (pdf or ""),
    )


def ask(url: str = URL, token: str | None = TOKEN, question: str = QUESTION, **extra):
    headers = {} if token is None else {"x-frp-local-token": token}
    body = {"question": question, **extra}
    return TestClient(app).post(url, json=body, headers=headers)


def test_route_is_off_by_default(monkeypatch):
    monkeypatch.delenv("FRP_LOCAL_FACTS_REPORT", raising=False)
    assert ask().status_code == 404


def test_missing_or_wrong_token_is_refused(monkeypatch):
    authorize(monkeypatch)
    assert ask(token=None).status_code == 404
    assert ask(token="wrong-token-but-long-enough-000000").status_code == 404


def test_production_environment_is_refused(monkeypatch):
    authorize(monkeypatch)
    monkeypatch.setenv("FRP_ENV", "production")
    assert ask().status_code == 404


def test_unknown_and_legacy_reports_are_refused(monkeypatch):
    authorize(monkeypatch)
    assert ask("/api/v1/research/reports/999999-2026H1/ask").status_code == 404
    assert ask("/api/v1/research/reports/600276-2026H1/ask").status_code == 404


def test_missing_pdf_path_is_unavailable(monkeypatch):
    authorize(monkeypatch, pdf="")
    response = ask()
    assert response.status_code == 503
    assert response.json() == {"detail": "SOURCE_UNAVAILABLE"}


@pytest.mark.parametrize("question", ["", "x", "x" * 241])
def test_invalid_question_length_is_rejected(monkeypatch, question):
    authorize(monkeypatch)
    assert ask(question=question).status_code == 422


def test_extra_fields_are_rejected(monkeypatch):
    authorize(monkeypatch)
    assert ask(unexpected="value").status_code == 422


def test_authorized_question_returns_verified_facts(monkeypatch):
    if not PDF.is_file():
        pytest.skip("authorized 600760 PDF not provisioned locally")
    authorize(monkeypatch)

    response = ask()
    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "REPORT_READY"
    assert report["report_type"] == "FACTS_ONLY_QUESTION_REPORT"
    assert report["facts"][0]["value_verbatim"] == "6,191,107,217.36"
    assert report["publication"]["research_publication"] == "FACTS_ONLY"


ASK_URL = "/api/v1/research/reports/600760-2026H1/ask"
RESOLVE_URL = "/api/v1/research/reports/600760-2026H1/ask/resolve"
NET_PROFIT_QUESTION = "600760 中航沈飞 2026 年半年度合并利润表的净利是多少？"


def ask_net_profit():
    headers = {"x-frp-local-token": TOKEN}
    return TestClient(app).post(ASK_URL, json={"question": NET_PROFIT_QUESTION},
                                headers=headers)


def resolve(question, clarification_id, option_id):
    headers = {"x-frp-local-token": TOKEN}
    return TestClient(app).post(
        RESOLVE_URL,
        json={"question": question, "clarification_id": clarification_id,
              "option_id": option_id},
        headers=headers,
    )


def test_ambiguous_metric_returns_clarification(monkeypatch):
    if not PDF.is_file():
        pytest.skip("authorized 600760 PDF not provisioned locally")
    authorize(monkeypatch)
    monkeypatch.delenv("FRP_LOCAL_CLARIFY_LLM", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    response = ask_net_profit()
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "CLARIFICATION_REQUIRED"
    assert body["reason"] == "METRIC_IDENTITY_AMBIGUOUS"
    assert len(body["options"]) >= 2
    assert body["research_publication"] == "BLOCKED"
    assert body["clarification_id"]
    cores = {option["core"] for option in body["options"]}
    assert "归属于母公司股东的净利润" in cores
    assert "净利润" in cores


def test_clarification_resolve_roundtrip(monkeypatch):
    if not PDF.is_file():
        pytest.skip("authorized 600760 PDF not provisioned locally")
    authorize(monkeypatch)
    monkeypatch.delenv("FRP_LOCAL_CLARIFY_LLM", raising=False)

    clarification = ask_net_profit().json()
    attributable = next(
        option for option in clarification["options"]
        if option["core"] == "归属于母公司股东的净利润"
    )

    result = resolve(
        NET_PROFIT_QUESTION, clarification["clarification_id"],
        attributable["option_id"],
    )
    assert result.status_code == 200
    report = result.json()
    assert report["status"] == "REPORT_READY"
    assert len(report["facts"]) == 1
    assert report["facts"][0]["row_label"].startswith("1.归属于母公司股东的净利润")
    assert report["facts"][0]["value_verbatim"] == "473,065,863.24"
    assert report["selection"]["trace"]["selection_basis"] == "USER_RESOLVED_METRIC"


def test_resolve_rejects_tampered_token(monkeypatch):
    if not PDF.is_file():
        pytest.skip("authorized 600760 PDF not provisioned locally")
    authorize(monkeypatch)
    monkeypatch.delenv("FRP_LOCAL_CLARIFY_LLM", raising=False)

    clarification = ask_net_profit().json()
    option_id = clarification["options"][0]["option_id"]
    tampered = clarification["clarification_id"][:-1] + (
        "0" if clarification["clarification_id"][-1] != "0" else "1"
    )

    result = resolve(NET_PROFIT_QUESTION, tampered, option_id)
    assert result.status_code == 422


def test_resolve_rejects_unoffered_option(monkeypatch):
    if not PDF.is_file():
        pytest.skip("authorized 600760 PDF not provisioned locally")
    authorize(monkeypatch)
    monkeypatch.delenv("FRP_LOCAL_CLARIFY_LLM", raising=False)

    clarification = ask_net_profit().json()
    result = resolve(NET_PROFIT_QUESTION, clarification["clarification_id"], "f" * 64)
    assert result.status_code == 422


def test_scope_resolve_runs_the_chosen_statement(monkeypatch):
    if not PDF.is_file():
        pytest.skip("authorized 600760 PDF not provisioned locally")
    authorize(monkeypatch)
    from hashlib import sha256
    from app.evidence.corpus_manifest import load_corpus_manifest
    from app.modules.financial_report_analyst import clarification as cl

    document = load_corpus_manifest().require_report_key("600760-2026H1")
    secret = sha256(TOKEN.encode("utf-8")).hexdigest()
    ids = [
        cl.scope_option_id(document, "consolidated_income_statement"),
        cl.scope_option_id(document, "parent_income_statement"),
    ]
    token = cl.sign_clarification(
        question="营业收入是多少？", document=document, report_key="600760-2026H1",
        statement_kind=None, option_ids=ids, secret=secret, kind="STATEMENT_SCOPE",
    )

    result = resolve("营业收入是多少？", token, ids[0])
    assert result.status_code == 200
    report = result.json()
    assert report["status"] == "REPORT_READY"
    assert report["facts"][0]["value_verbatim"] == "6,191,107,217.36"
    assert report["selection"]["trace"]["selection_basis"] == "USER_RESOLVED_STATEMENT_SCOPE"


def test_dual_statement_question_is_still_rejected(monkeypatch):
    if not PDF.is_file():
        pytest.skip("authorized 600760 PDF not provisioned locally")
    authorize(monkeypatch)
    headers = {"x-frp-local-token": TOKEN}

    response = TestClient(app).post(
        ASK_URL,
        json={"question": "600760 中航沈飞 2026 年半年度合并利润表和母公司利润表的营业收入各是多少？"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "REPORT_WITHHELD"
    assert body["reason"] == "AMBIGUOUS_STATEMENT_SCOPE"


def test_ask_offers_scope_choice_and_resolve_publishes(monkeypatch):
    if not PDF.is_file():
        pytest.skip("authorized 600760 PDF not provisioned locally")
    authorize(monkeypatch)
    headers = {"x-frp-local-token": TOKEN}

    asked = TestClient(app).post(
        ASK_URL, json={"question": "利润总额是多少？"}, headers=headers,
    )
    assert asked.status_code == 200
    clarification = asked.json()
    assert clarification["status"] == "CLARIFICATION_REQUIRED"
    assert clarification["kind"] == "STATEMENT_SCOPE"
    assert [o["statement_title"] for o in clarification["options"]] == [
        "合并利润表", "母公司利润表"
    ]
    consolidated = clarification["options"][0]

    resolved = resolve("利润总额是多少？", clarification["clarification_id"],
                       consolidated["option_id"])
    assert resolved.status_code == 200
    report = resolved.json()
    assert report["status"] == "REPORT_READY"
    assert report["facts"][0]["value_verbatim"] == "565,393,924.81"
    assert report["selection"]["trace"]["selection_basis"] == "USER_RESOLVED_STATEMENT_SCOPE"


def test_multi_fact_question_returns_coverage(monkeypatch):
    if not PDF.is_file():
        pytest.skip("authorized 600760 PDF not provisioned locally")
    authorize(monkeypatch)
    headers = {"x-frp-local-token": TOKEN}

    response = TestClient(app).post(
        ASK_URL,
        json={"question": "600760 中航沈飞 2026 年半年度合并利润表中营业收入和净利润分别是多少？"},
        headers=headers,
    )
    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "REPORT_READY"
    assert report["report_type"] == "FACTS_ONLY_MULTI_REQUIREMENT_REPORT"
    assert len(report["facts"]) == 2
    assert report["coverage"]["complete"] is True


def test_partial_multi_repair_roundtrip(monkeypatch):
    if not PDF.is_file():
        pytest.skip("authorized 600760 PDF not provisioned locally")
    authorize(monkeypatch)
    headers = {"x-frp-local-token": TOKEN}
    question = "600760 中航沈飞 2026 年半年度合并利润表中营业收入和研发投入分别是多少？"

    asked = TestClient(app).post(ASK_URL, json={"question": question}, headers=headers)
    assert asked.status_code == 200
    partial = asked.json()
    assert partial["status"] == "REPORT_READY"
    assert partial["coverage"]["complete"] is False
    repair = partial["coverage"]["repair"]
    assert repair["facet"] == "研发投入"
    option = next(o for o in repair["options"] if o["core"] == "研发费用")

    resolved = resolve(question, repair["clarification_id"], option["option_id"])
    assert resolved.status_code == 200
    report = resolved.json()
    assert report["status"] == "REPORT_READY"
    assert report["coverage"]["complete"] is True
    assert "59,650,843.12" in {fact["value_verbatim"] for fact in report["facts"]}


def test_management_question_returns_a_preview_not_a_publication(monkeypatch, tmp_path):
    if not PDF.is_file():
        pytest.skip("authorized 600760 PDF not provisioned locally")
    authorize(monkeypatch)
    monkeypatch.setenv("FRP_SEMANTIC_REVIEW_STORAGE", str(tmp_path / "reviews"))
    headers = {"x-frp-local-token": TOKEN}

    response = TestClient(app).post(
        ASK_URL,
        json={"question": "600760 中航沈飞 2026 年半年度营业收入变动原因是什么？"},
        headers=headers,
    )
    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "REPORT_WITHHELD"
    assert report["reason"] == "MANAGEMENT_EXPLANATION_REQUIRES_SEMANTIC_REVIEW"
    assert report["facts"] == []
    assert report["management_preview"]["pointers"]


def test_mixed_question_route_returns_fact_and_preview(monkeypatch):
    if not PDF.is_file():
        pytest.skip("authorized 600760 PDF not provisioned locally")
    authorize(monkeypatch)
    headers = {"x-frp-local-token": TOKEN}

    response = TestClient(app).post(
        ASK_URL,
        json={"question": "600760 中航沈飞 2026 年半年度营业收入是多少？管理层为什么说利润下降？"},
        headers=headers,
    )
    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "REPORT_READY"
    assert report["report_type"] == "FACTS_WITH_MANAGEMENT_PREVIEW_REPORT"
    assert report["facts"]
    assert report["management_preview"]["pointers"]
    assert report["management_publication"]["may_publish"] is False


MANAGEMENT_Q = "600760 中航沈飞 2026 年半年度营业收入变动原因是什么？"
DECIDE_URL = "/api/v1/research/reviews/decide"
from app.modules.financial_report_analyst.semantic_review import CHECKLIST_KEYS

CHECKLIST = {key: True for key in CHECKLIST_KEYS}


def management_packet(monkeypatch, tmp_path):
    authorize(monkeypatch)
    monkeypatch.setenv("FRP_SEMANTIC_REVIEW_STORAGE", str(tmp_path / "reviews"))
    response = ask(question=MANAGEMENT_Q)
    assert response.status_code == 200
    return response.json()["review_packet"]


def decide(packet, **overrides):
    body = {
        "packet_id": packet["packet_id"],
        "reviewer_id": "local-reviewer",
        "verdict": "ADMIT",
        "checklist": CHECKLIST,
        "rationale": "人工核对原文、指标、期间与主体一致。",
    }
    body.update(overrides)
    return TestClient(app).post(
        DECIDE_URL, json=body, headers={"x-frp-local-token": TOKEN},
    )


def test_management_question_pauses_at_the_review_packet(monkeypatch, tmp_path):
    packet = management_packet(monkeypatch, tmp_path)

    assert packet["status"] == "AWAITING_EXPLICIT_HUMAN_DECISION"
    assert packet["development_only"] is True
    assert packet["independent_validation"] is False
    assert packet["evidence"]["page_number"] >= 1
    assert packet["context"]
    assert "营业收入变动原因说明" in packet["context"]
    assert "阶段性偏差" in packet["claim_text"]
    assert not (tmp_path / "reviews").exists()


def test_explicit_admit_records_a_development_only_review(monkeypatch, tmp_path):
    packet = management_packet(monkeypatch, tmp_path)

    response = decide(packet)
    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "REPORT_READY"
    assert report["report_type"] == "MANAGEMENT_EXPLANATION_DEVELOPMENT_REPORT"
    assert report["development_only"] is True
    assert report["independent_validation"] is False
    assert report["claim"]["text"] == packet["claim_text"]
    assert report["review"]["reviewer_id"] == "local-reviewer"
    assert "营业收入变动原因说明" in report["review"]["context"]
    assert report["review"]["verdict"] == "ADMIT"


def test_explicit_reject_withholds_publication(monkeypatch, tmp_path):
    packet = management_packet(monkeypatch, tmp_path)

    response = decide(packet, verdict="REJECT", checklist={key: False for key in CHECKLIST_KEYS})
    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "REPORT_WITHHELD"
    assert report["reason"] == "SEMANTIC_REVIEW_REJECTED"
    assert report["publication"]["may_publish"] is False


def test_unknown_reviewer_is_refused(monkeypatch, tmp_path):
    packet = management_packet(monkeypatch, tmp_path)

    response = decide(packet, reviewer_id="someone-else")
    assert response.status_code == 422
    assert "REVIEWER_NOT_ALLOWLISTED" in response.json()["detail"]


def test_incomplete_checklist_cannot_admit(monkeypatch, tmp_path):
    packet = management_packet(monkeypatch, tmp_path)

    incomplete = dict(CHECKLIST)
    incomplete["basis"] = False
    response = decide(packet, checklist=incomplete)
    assert response.status_code == 422
    assert "REVIEW_CHECKLIST_NOT_MET" in response.json()["detail"]


def test_a_tampered_packet_is_refused(monkeypatch, tmp_path):
    packet = management_packet(monkeypatch, tmp_path)

    tampered = dict(packet)
    tampered["packet_id"] = packet["packet_id"][:-4] + "0000"
    response = decide(tampered)
    assert response.status_code == 422


def test_checklist_notes_are_recorded(monkeypatch, tmp_path):
    packet = management_packet(monkeypatch, tmp_path)
    notes = {key: f"note-{key}" for key in CHECKLIST_KEYS}

    response = decide(packet, checklist_notes=notes)
    assert response.status_code == 200
    assert response.json()["review"]["checklist_notes"] == notes


def _build_management(question: str):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from app.modules.financial_report_analyst import report_builder
    return report_builder.build_management_report(
        "600760-2026H1", PDF, question,
        as_of=datetime(2026, 11, 3, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        review_secret="test-review-secret",
    )


def test_an_admitted_review_is_reused_for_the_same_claim(monkeypatch, tmp_path):
    packet = management_packet(monkeypatch, tmp_path)
    recorded = decide(packet)
    assert recorded.status_code == 200
    review_id = recorded.json()["review"]["review_id"]

    report = _build_management(MANAGEMENT_Q)
    assert report["status"] == "REPORT_READY"
    assert report["report_type"] == "MANAGEMENT_EXPLANATION_DEVELOPMENT_REPORT"
    assert report["review"]["review_id"] == review_id
    assert report["development_only"] is True
    assert report["independent_validation"] is False


def test_a_changed_claim_is_not_reused(monkeypatch, tmp_path):
    packet = management_packet(monkeypatch, tmp_path)
    assert decide(packet).status_code == 200

    other = "600760 中航沈飞 2026 年半年度营业成本变动原因是什么？"
    report = _build_management(other)
    assert report["status"] == "REPORT_WITHHELD"
    assert report["review_packet"]


def test_a_rejected_review_is_not_reused(monkeypatch, tmp_path):
    packet = management_packet(monkeypatch, tmp_path)
    rejected = decide(packet, verdict="REJECT", checklist={key: False for key in CHECKLIST_KEYS})
    assert rejected.status_code == 200

    report = _build_management(MANAGEMENT_Q)
    assert report["status"] == "REPORT_WITHHELD"
    assert report["review_packet"]


def test_a_non_allowlisted_reviewer_is_not_reused(tmp_path):
    from app.modules.financial_report_analyst import semantic_review
    storage = tmp_path / "reviews"
    storage.mkdir()
    (storage / "x.json").write_text(
        json.dumps({
            "review_id": "x", "reviewer_id": "other", "verdict": "ADMIT",
            "development_only": True,
            "checklist": {key: True for key in CHECKLIST_KEYS},
            "claim_text": "c", "excerpt_sha256": "e", "context_sha256": "k",
            "document_id": "d", "source_sha256": "s", "canonical_sha256": "n",
            "page_number": 1,
        }),
        encoding="utf-8",
    )
    assert semantic_review.find_admitted_review(
        claim_text="c", excerpt_sha256="e", context_sha256="k",
        document_id="d", source_sha256="s", canonical_sha256="n",
        page_number=1, allowlist=("local-reviewer",), storage_dir=storage,
    ) is None
