"use client";

import { useState } from "react";
import styles from "./report.module.css";

const HEX = /^[0-9a-f]{64}$/;

type SourceIdentity = Readonly<{
  documentId: string;
  url: string;
  sha: string;
  canonicalSha: string;
}>;

type PreviewClaim = {
  claim_id: string;
  text: string;
  evidence_id: string;
  source_page: number;
  source_quote: string;
  review: {
    verdict: "UNCERTAIN";
    scope: "QUOTE_AND_NUMERIC_BINDING_ONLY";
    reason: "SOURCE_QUOTE_BOUND_SEMANTICS_UNREVIEWED";
  };
};

type CoverageFacet = {
  question_phrase: string;
  literal_status:
    | "PHRASE_VISIBLE_IN_SOURCE_AND_DRAFT"
    | "PHRASE_VISIBLE_IN_SOURCE_ONLY"
    | "PHRASE_NOT_LOCATED_LEXICALLY";
  source_evidence_ids: string[];
  draft_claim_ids: string[];
};

type CoverageProbe = {
  coverage_id: string;
  coverage_version: "frp-question-phrase-visibility-v1";
  basis: "EXACT_NORMALIZED_QUESTION_PHRASES_ONLY";
  segmentation: "SURFACE_CONJUNCTION_SPLIT" | "FALLBACK_SINGLE_QUESTION_PHRASE";
  review: "COVERAGE_NOT_SEMANTICALLY_QUALIFIED";
  facets: CoverageFacet[];
  limitations: string;
};

type PreviewPacket = {
  status: "UNPUBLISHED_ANALYST_PREVIEW" | "WITHHELD";
  reason?: string;
  failure_code?: string;
  draft_id?: string;
  draft_version?: string;
  report_key: string;
  question: string;
  retrieval_id: string;
  document_id: string;
  source_url: string;
  source_sha256: string;
  canonical_sha256: string;
  claims: PreviewClaim[];
  coverage_probe?: CoverageProbe;
  financial_semantic_review: "NOT_PERFORMED";
  research_publication: "BLOCKED";
  report_storage: "NOT_PERSISTED";
  claim_level_review?: "UNCERTAIN_SEMANTICS_NOT_REVIEWED";
};

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function validate(
  raw: unknown,
  source: SourceIdentity,
  question: string,
  retrievalId: string,
  evidenceIds: Set<string>,
): raw is PreviewPacket {
  if (!record(raw)) return false;
  if (
    !["UNPUBLISHED_ANALYST_PREVIEW", "WITHHELD"].includes(String(raw.status)) ||
    raw.report_key !== "600276-2026H1" || raw.question !== question ||
    raw.retrieval_id !== retrievalId ||
    raw.document_id !== source.documentId || raw.source_url !== source.url ||
    raw.source_sha256 !== source.sha || raw.canonical_sha256 !== source.canonicalSha ||
    raw.financial_semantic_review !== "NOT_PERFORMED" ||
    raw.research_publication !== "BLOCKED" || raw.report_storage !== "NOT_PERSISTED" ||
    !Array.isArray(raw.claims)
  ) return false;
  if (raw.status === "WITHHELD") {
    return raw.claims.length === 0 && typeof raw.reason === "string" &&
      (raw.failure_code === undefined || (
        typeof raw.failure_code === "string" &&
        /^[A-Z_]{3,64}$/.test(raw.failure_code)
      ));
  }
  if (
    raw.draft_version !== "frp-retrieval-analyst-preview-v1" ||
    typeof raw.draft_id !== "string" || !HEX.test(raw.draft_id) ||
    raw.claim_level_review !== "UNCERTAIN_SEMANTICS_NOT_REVIEWED" ||
    raw.claims.length < 1 || raw.claims.length > 3
  ) return false;
  if (!record(raw.coverage_probe)) return false;
  const coverage = raw.coverage_probe;
  if (
    typeof coverage.coverage_id !== "string" || !HEX.test(coverage.coverage_id) ||
    coverage.coverage_version !== "frp-question-phrase-visibility-v1" ||
    coverage.basis !== "EXACT_NORMALIZED_QUESTION_PHRASES_ONLY" ||
    !(coverage.segmentation === "SURFACE_CONJUNCTION_SPLIT" ||
      coverage.segmentation === "FALLBACK_SINGLE_QUESTION_PHRASE") ||
    coverage.review !== "COVERAGE_NOT_SEMANTICALLY_QUALIFIED" ||
    typeof coverage.limitations !== "string" || !coverage.limitations.trim() ||
    !Array.isArray(coverage.facets) || coverage.facets.length < 1 ||
    coverage.facets.length > 4
  ) return false;
  const claimIds = new Set(raw.claims.map((claim: unknown) =>
    record(claim) ? claim.claim_id : null,
  ));
  if (!coverage.facets.every((item: unknown) => {
    if (!record(item) || typeof item.question_phrase !== "string" ||
        !item.question_phrase.trim() || item.question_phrase.length > 240 ||
        !Array.isArray(item.source_evidence_ids) ||
        !Array.isArray(item.draft_claim_ids) ||
        item.source_evidence_ids.length > 5 || item.draft_claim_ids.length > 3 ||
        !item.source_evidence_ids.every((id: unknown) =>
          typeof id === "string" && evidenceIds.has(id)) ||
        !item.draft_claim_ids.every((id: unknown) =>
          typeof id === "string" && claimIds.has(id))
    ) return false;
    const sourceCount = item.source_evidence_ids.length;
    const draftCount = item.draft_claim_ids.length;
    return (
      (item.literal_status === "PHRASE_VISIBLE_IN_SOURCE_AND_DRAFT" && draftCount > 0 && sourceCount > 0) ||
      (item.literal_status === "PHRASE_VISIBLE_IN_SOURCE_ONLY" && sourceCount > 0 && draftCount === 0) ||
      (item.literal_status === "PHRASE_NOT_LOCATED_LEXICALLY" && sourceCount === 0 && draftCount === 0)
    );
  })) return false;
  return raw.claims.every((claim: unknown, index) => {
    if (!record(claim) || !record(claim.review)) return false;
    return claim.claim_id === `C${index + 1}` &&
      typeof claim.text === "string" && claim.text.length > 0 &&
      typeof claim.evidence_id === "string" && evidenceIds.has(claim.evidence_id) &&
      Number.isInteger(claim.source_page) && Number(claim.source_page) >= 1 &&
      Number(claim.source_page) <= 182 &&
      typeof claim.source_quote === "string" && claim.source_quote.trim().length > 0 &&
      claim.review.verdict === "UNCERTAIN" &&
      claim.review.scope === "QUOTE_AND_NUMERIC_BINDING_ONLY" &&
      claim.review.reason === "SOURCE_QUOTE_BOUND_SEMANTICS_UNREVIEWED";
  });
}

export default function AnalystPreviewSection({
  source, question, retrievalId, evidenceIds,
}: {
  source: SourceIdentity;
  question: string;
  retrievalId: string;
  evidenceIds: string[];
}) {
  const [busy, setBusy] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<PreviewPacket | null>(null);

  async function draft() {
    if (busy || attempted) return;
    setBusy(true);
    setAttempted(true); // Local paid-call budget; no automatic retry.
    setResult(null);
    setError("");
    try {
      const response = await fetch("/api/local-retrieval-analyst", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ report_key: "600276-2026H1", question }),
        cache: "no-store",
      });
      if (!response.ok) throw new Error("REQUEST_FAILED");
      const data: unknown = await response.json();
      if (!validate(data, source, question, retrievalId, new Set(evidenceIds))) {
        throw new Error("REVIEW_CONTRACT_MISMATCH");
      }
      setResult(data);
    } catch {
      setError("研究摘录请求失败或来源核验不通过，已停止；不会自动重试调用模型。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.card} aria-label="检索驱动的研究摘录实验">
      <p className={styles.smallTag}>M125 · 检索驱动研究草稿与覆盖线索</p>
      <h3>基于已检索证据生成研究摘录</h3>
      <p className={styles.qaHelp}>
        可选调用一次 DeepSeek 生成 1–3 条来源归属的研究陈述。
        独立检查仅核对引用、证据身份和数值词项；不证明财务语义或因果关系。
        如检索结果混合不同报表标题，则在模型调用前拒绝生成。
      </p>
      <button type="button" className={styles.button} disabled={busy || attempted}
        onClick={() => { void draft(); }}>
        {busy ? "正在生成并核对引用…" : attempted ? "本次已尝试生成" : "生成未发布研究草稿（调用一次模型）"}
      </button>
      {error && <p role="alert" className={styles.challengeCaution}>{error}</p>}
      {result?.status === "WITHHELD" && (
        <p className={styles.challengeCaution}>
          草稿已保留不展示：{result.reason}。
          {result.failure_code ? ` 原因分类：${result.failure_code}。` : ""}
          本次未通过模型输出的来源绑定审核；不能据此判断公告缺少相关事实。
        </p>
      )}
      {result?.status === "UNPUBLISHED_ANALYST_PREVIEW" && (
        <div aria-live="polite" className={styles.qaResult}>
          <h3>研究摘录 · 未经财务语义审核</h3>
          {result.claims.map((claim) => (
            <article className={styles.answerManagement} key={claim.claim_id}>
              <p><strong>{claim.claim_id} · {claim.text}</strong></p>
              <blockquote className={styles.answerPassage}>{claim.source_quote}</blockquote>
              <a className={styles.source} target="_blank" rel="noopener noreferrer"
                href={`${source.url}#page=${claim.source_page}`}>
                原始公告 · PDF 第 {claim.source_page} 页
              </a>
              <p className={styles.qaHelp}>
                证据：{claim.evidence_id.slice(0, 16)}… · 审核：UNCERTAIN（仅字面引用和数值绑定）
              </p>
            </article>
          ))}
          {result.coverage_probe && (
            <section className={styles.answerBoundary} aria-label="研究问题字面覆盖线索">
              <h4>提问覆盖线索 · 不是完整性判定</h4>
              <p className={styles.qaHelp}>
                自动分解问题中的表面短语，只检查它们是否在已检索原文与草稿引文中逐字出现。
                无法识别同义词或解释性改写；任何匹配都不等于真正回答了问题。
              </p>
              <ul>
                {result.coverage_probe.facets.map((facet, i) => (
                  <li key={`${i}-${facet.question_phrase}`}>
                    <strong>「{facet.question_phrase}」</strong>：{" "}
                    {facet.literal_status === "PHRASE_VISIBLE_IN_SOURCE_AND_DRAFT"
                      ? `原文与草稿均出现该词组（${facet.draft_claim_ids.join("、")}）；语义尚未审核。`
                      : facet.literal_status === "PHRASE_VISIBLE_IN_SOURCE_ONLY"
                        ? "已检索原文出现该词组，但草稿陈述及引文未同时匹配；可能有遗漏。"
                        : "当前候选中未逐字找到该词组；同义表达可能存在，不能认定事实缺失。"}
                  </li>
                ))}
              </ul>
              <p className={styles.qaHelp}>
                检查范围仅限本次传给 Analyst 的原文候选及本次草稿；
                检索相关性、问题完整性和财务语义均未获核验。
              </p>
            </section>
          )}
          <p className={styles.challengeCaution}>
            所有陈述仍是未审核的模型草稿；不可视为合格研究报告。
            财务语义：NOT_PERFORMED · 发布：BLOCKED · 未持久化。
          </p>
        </div>
      )}
    </div>
  );
}
