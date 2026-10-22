"""M1.8B synthetic, offline model proposal and inference-withholding tests."""
import json
from types import SimpleNamespace

from app.modules.financial_report_analyst import management_brief as b

SYN_SENTENCE = "2026年上半年公司创新药销售收入1.23亿元，同比增长4.56%，占药品销售收入的比重达7.89%。"


def configure(monkeypatch):
    source = SimpleNamespace(document_id="doc-synthetic", source_sha256="a"*64,
        canonical_sha256="b"*64, source_url="https://example.test/synthetic.pdf")
    monkeypatch.setattr(b.revenue_scope, "SOURCE", source)
    items = [
        {"evidence_id":"1"*64,"statement_kind":"consolidated_income_statement", "statement_title":"合并利润表",
         "row_label":"其中：营业收入", "column_header":"2026 年半年度", "value":"1,000.00","page_number":11},
        {"evidence_id":"2"*64,"statement_kind":"parent_income_statement", "statement_title":"母公司利润表",
         "row_label":"一、营业收入", "column_header":"2026 年半年度", "value":"900.00","page_number":12},
    ]
    monkeypatch.setattr(b.deepseek_draft, "_verified_packet", lambda _: {"evidence":items})
    monkeypatch.setattr(b.deepseek_draft, "_usage", lambda _: {"total_tokens":100,"prompt_tokens":60,"completion_tokens":40,
      "estimated_cost_usd_low":"0.00000100","estimated_cost_usd_high":"0.00000200"})
    management = {"status":"SOURCE_PASSAGE_REVIEWED","document_id":source.document_id,
        "source_sha256":source.source_sha256,"canonical_sha256":source.canonical_sha256,
        "source_url":source.source_url,"source_page":20,"evidence_id":"3"*64,
        "source_kind":"MANAGEMENT_DISCUSSION_PASSAGE","review_scope":"NATIVE_PDF_TEXT_AND_WORD_LOCATION_ONLY",
        "passage_whitespace_normalized":SYN_SENTENCE,
        "financial_semantic_review":"NOT_PERFORMED","research_publication":"BLOCKED"}
    return {"report_id":"c"*64}, management


def fake_provider(payload, api_key, client):
    assert api_key == "synthetic-key"
    packet = json.loads(payload["messages"][1]["content"].split("packet: ", 1)[1])
    assert [e["claim_id"] for e in packet["evidence"]] == ["F1", "F2", "M1"]
    proposal = {"claims":[{k:e[k] for k in ("claim_id","kind","evidence_id","text")}
                          for e in packet["evidence"]],
                "inference":{"claim_id":"A1","kind":"ANALYST_INFERENCE",
                   "supporting_claim_ids":["F1","F2","M1"],
                   "assumptions":["Unknown scope association"],
                   "text":"An unjustified inference about growth should not be displayed."}}
    return {"model":b.deepseek_draft.MODEL,"choices":[{"finish_reason":"stop",
        "message":{"content":json.dumps(proposal,ensure_ascii=False)}}],"usage":{}}


def test_three_provenance_claims_and_inference_redaction(monkeypatch):
    source, management = configure(monkeypatch)
    monkeypatch.setattr(b.deepseek_draft, "_send", fake_provider)
    result = b.draft_management_brief(source, management, api_key="synthetic-key",client=object())
    assert result["status"] == "LLM_MANAGEMENT_SOURCE_BOUND"
    assert [c["claim_id"] for c in result["claims"]] == ["F1","F2","M1"]
    assert result["claims"][2]["source_page"] == 20
    assert len(result["reviews"]) == 4
    assert result["reviews"][3]["verdict"] == "WITHHELD_UNQUALIFIED_INFERENCE"
    assert result["inference_withheld_count"] == 1
    assert "unjustified inference" not in json.dumps(result)
    assert result["research_publication"] == "BLOCKED"


def test_model_changed_literal_amount_withheld(monkeypatch):
    source, management = configure(monkeypatch)
    def corrupted(payload, api_key, client):
        result = fake_provider(payload,api_key,client)
        p = json.loads(result["choices"][0]["message"]["content"])
        p["claims"][0]["text"] = "Wrong source amount 999.00"
        result["choices"][0]["message"]["content"] = json.dumps(p)
        return result
    monkeypatch.setattr(b.deepseek_draft,"_send",corrupted)
    result = b.draft_management_brief(source, management, api_key="synthetic-key",client=object())
    assert result["status"] == "WITHHELD" and result["claims"] == []


def test_management_packet_mismatch_never_calls_provider(monkeypatch):
    source, management = configure(monkeypatch)
    management["source_sha256"] = "0"*64
    monkeypatch.setattr(b.deepseek_draft, "_send", lambda *a,**k: (_ for _ in ()).throw(AssertionError("PAID_CALL")))
    result = b.draft_management_brief(source, management,api_key="synthetic-key",client=object())
    assert result["status"] == "WITHHELD" and result["claims"] == []


def test_inference_cannot_become_reviewed_fact(monkeypatch):
    source, management = configure(monkeypatch)
    def corrupted(payload, api_key, client):
        result=fake_provider(payload,api_key,client)
        p=json.loads(result["choices"][0]["message"]["content"])
        p["inference"]["kind"]="SOURCE_FACT"
        result["choices"][0]["message"]["content"]=json.dumps(p)
        return result
    monkeypatch.setattr(b.deepseek_draft,"_send",corrupted)
    result=b.draft_management_brief(source,management,api_key="synthetic-key",client=object())
    assert result["status"]=="WITHHELD"
