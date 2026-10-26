"use client";

import { useState } from "react";
import AnalystPreviewSection from "./analyst-preview-section";
import styles from "./report.module.css";

const REPORT_KEY = "600276-2026H1";
const HEX = /^[a-f0-9]{64}$/;

type SourceIdentity = Readonly<{
  documentId: string;
  url: string;
  sha: string;
  canonicalSha: string;
}>;

type Evidence = {
  evidence_id: string;
  source_page: number;
  canonical_start: number;
  canonical_end: number;
  source_excerpt: string;
  review_scope: "VERIFIED_CANONICAL_TEXT_SPAN_ONLY";
  statement_heading_cue: {
    status: "STANDALONE_HEADING_CANDIDATE" | "UNRESOLVED";
    heading_verbatim: string | null;
    heading_page: number | null;
    heading_start: number | null;
    heading_end: number | null;
  };
};

type Packet = {
  status: "RETRIEVAL_CANDIDATES_READY" | "WITHHELD";
  reason: string | null;
  retrieval_id: string;
  retriever_version: "frp-canonical-lexical-v1";
  report_key: string;
  question: string;
  as_of: string;
  document_id: string;
  report_period: string;
  source_url: string;
  source_sha256: string;
  canonical_sha256: string;
  evidence: Evidence[];
  terminology_probe: {
    version: "frp-m126-retrieval-candidates-v1";
    registry_sha256: string;
    status: "ACTIVATED" | "NO_TRIGGER";
    matched_cues: string[];
    candidates: {
      concept_id: string;
      preferred_zh: string;
      kind: string;
      origin: string;
      not_equivalent_to: string[];
    }[];
    distinct_concepts_warning: "NON_EQUIVALENT_CANDIDATES" | "NOT_ASSESSED";
    review: "RETRIEVAL_CUES_ONLY_NOT_FINANCIAL_EQUIVALENCE";
  };
  ranking_version: "frp-m127-quantity-proximity-page-diversity-v1" | "frp-legacy-lexical-v1";
  retrieval_review: "CANDIDATES_NOT_RELEVANCE_QUALIFIED";
  context_probe_version: "frp-standalone-statement-heading-cue-v1";
  statement_heading_alert: "MULTIPLE_STATEMENT_HEADING_CANDIDATES" | "NOT_ASSESSED";
  retrieval_context_review: "HEADING_CUE_ONLY_NOT_SEMANTICALLY_REVIEWED";
  financial_semantic_review: "NOT_PERFORMED";
  research_publication: "BLOCKED";
  report_storage: "NOT_PERSISTED";
  limitations: string;
};

function isRecord(x: unknown): x is Record<string, unknown> {
  return x !== null && typeof x === "object" && !Array.isArray(x);
}

function verifiedPacket(
  data: unknown,
  source: SourceIdentity,
  question: string,
): data is Packet {
  if (!isRecord(data)) return false;
  const v = data;
  if (
    !(v.status === "RETRIEVAL_CANDIDATES_READY" || v.status === "WITHHELD") ||
    v.retriever_version !== "frp-canonical-lexical-v1" ||
    v.report_key !== REPORT_KEY ||
    v.question !== question ||
    v.document_id !== source.documentId ||
    v.source_url !== source.url ||
    v.source_sha256 !== source.sha ||
    v.canonical_sha256 !== source.canonicalSha ||
    v.report_period !== "2026H1" ||
    typeof v.retrieval_id !== "string" || !HEX.test(v.retrieval_id) ||
    typeof v.as_of !== "string" || !Number.isFinite(Date.parse(v.as_of)) ||
    v.retrieval_review !== "CANDIDATES_NOT_RELEVANCE_QUALIFIED" ||
    !isRecord(v.terminology_probe) ||
    v.terminology_probe.version !== "frp-m126-retrieval-candidates-v1" ||
    typeof v.terminology_probe.registry_sha256 !== "string" ||
    !HEX.test(v.terminology_probe.registry_sha256) ||
    !(v.terminology_probe.status === "ACTIVATED" || v.terminology_probe.status === "NO_TRIGGER") ||
    v.terminology_probe.review !== "RETRIEVAL_CUES_ONLY_NOT_FINANCIAL_EQUIVALENCE" ||
    !(v.terminology_probe.distinct_concepts_warning === "NON_EQUIVALENT_CANDIDATES" ||
      v.terminology_probe.distinct_concepts_warning === "NOT_ASSESSED") ||
    !Array.isArray(v.terminology_probe.matched_cues) ||
    v.terminology_probe.matched_cues.length > 8 ||
    !v.terminology_probe.matched_cues.every((x: unknown) => typeof x === "string" && x.length <= 40) ||
    !Array.isArray(v.terminology_probe.candidates) ||
    v.terminology_probe.candidates.length > 8 ||
    !v.terminology_probe.candidates.every((x: unknown) =>
      isRecord(x) && typeof x.concept_id === "string" && x.concept_id.length <= 80 &&
      typeof x.preferred_zh === "string" && x.preferred_zh.length <= 40 &&
      typeof x.kind === "string" && typeof x.origin === "string" &&
      Array.isArray(x.not_equivalent_to) &&
      x.not_equivalent_to.every((z: unknown) => typeof z === "string" && z.length <= 80)
    ) ||
    (v.terminology_probe.status === "NO_TRIGGER" && v.terminology_probe.candidates.length !== 0) ||
    (v.terminology_probe.status === "ACTIVATED" && v.terminology_probe.candidates.length === 0) ||
    (v.terminology_probe.status === "ACTIVATED" &&
      v.ranking_version !== "frp-m127-quantity-proximity-page-diversity-v1") ||
    (v.terminology_probe.status === "NO_TRIGGER" &&
      v.ranking_version !== "frp-legacy-lexical-v1") ||
    v.context_probe_version !== "frp-standalone-statement-heading-cue-v1" ||
    !(v.statement_heading_alert === "MULTIPLE_STATEMENT_HEADING_CANDIDATES" ||
      v.statement_heading_alert === "NOT_ASSESSED") ||
    v.retrieval_context_review !== "HEADING_CUE_ONLY_NOT_SEMANTICALLY_REVIEWED" ||
    v.financial_semantic_review !== "NOT_PERFORMED" ||
    v.research_publication !== "BLOCKED" ||
    v.report_storage !== "NOT_PERSISTED" ||
    typeof v.limitations !== "string" ||
    !Array.isArray(v.evidence) || v.evidence.length > 5
  ) return false;
  if (v.status === "WITHHELD" && (
    v.evidence.length !== 0 ||
    v.reason !== "NO_LEXICAL_MATCH_NOT_EVIDENCE_OF_ABSENCE"
  )) return false;
  if (v.status === "RETRIEVAL_CANDIDATES_READY" && (
    v.evidence.length === 0 || v.reason !== null
  )) return false;
  const ids = new Set<string>();
  return v.evidence.every((candidate: unknown) => {
    if (!isRecord(candidate)) return false;
    const e = candidate;
    if (
      typeof e.evidence_id !== "string" || !HEX.test(e.evidence_id) ||
      ids.has(e.evidence_id) ||
      typeof e.source_page !== "number" || !Number.isInteger(e.source_page) ||
      e.source_page < 1 || e.source_page > 182 ||
      typeof e.canonical_start !== "number" || !Number.isInteger(e.canonical_start) ||
      e.canonical_start < 0 ||
      typeof e.canonical_end !== "number" || !Number.isInteger(e.canonical_end) ||
      e.canonical_end <= e.canonical_start ||
      typeof e.source_excerpt !== "string" ||
      !e.source_excerpt.trim() || e.source_excerpt.length > 1200 ||
      e.review_scope !== "VERIFIED_CANONICAL_TEXT_SPAN_ONLY" ||
      !isRecord(e.statement_heading_cue)
    ) return false;
    const cue = e.statement_heading_cue;
    if (cue.status === "UNRESOLVED") {
      if (cue.heading_verbatim !== null || cue.heading_page !== null ||
          cue.heading_start !== null || cue.heading_end !== null) return false;
    } else if (cue.status === "STANDALONE_HEADING_CANDIDATE") {
      if (typeof cue.heading_verbatim !== "string" ||
          cue.heading_verbatim.length === 0 || cue.heading_verbatim.length > 40 ||
          typeof cue.heading_page !== "number" || !Number.isInteger(cue.heading_page) ||
          cue.heading_page < 1 || cue.heading_page > e.source_page ||
          e.source_page - cue.heading_page > 1 ||
          typeof cue.heading_start !== "number" || !Number.isInteger(cue.heading_start) ||
          cue.heading_start < 0 ||
          typeof cue.heading_end !== "number" || !Number.isInteger(cue.heading_end) ||
          cue.heading_end <= cue.heading_start || cue.heading_end > e.canonical_start) return false;
    } else return false;
    ids.add(e.evidence_id);
    return true;
  });
}

export default function RetrievalQuestionSection({ source }: { source: SourceIdentity }) {
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [packet, setPacket] = useState<Packet | null>(null);

  async function retrieve() {
    const asked = question.trim();
    if (!asked || busy || asked.length > 240) return;
    setBusy(true);
    setPacket(null);
    setMessage("");
    try {
      const response = await fetch("/api/local-evidence-search", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ report_key: REPORT_KEY, question: asked }),
        cache: "no-store",
      });
      if (!response.ok) throw new Error("RETRIEVAL_UNAVAILABLE");
      const responseData: unknown = await response.json();
      if (!verifiedPacket(responseData, source, asked)) {
        throw new Error("RETRIEVAL_CONTRACT_NOT_QUALIFIED");
      }
      setPacket(responseData);
    } catch {
      setMessage("原始PDF检索不可用，或来源身份核验未通过；不展示未经确认的证据。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={styles.qaPanel} aria-label="原始公告开放式证据检索">
      <p className={styles.kicker}>开放式问题 · 原始证据检索实验</p>
      <h2>向公告提出任何研究问题，先找证据</h2>
      <p className={styles.qaHelp}>
        当前资料库仅包含已核验的恒瑞医药 2026 年半年度公告。
        该功能检索相关原文片段，不是财务分析答案或报告摘要；
        不调用 DeepSeek，也不计算比率。
      </p>
      <form className={styles.qaForm} onSubmit={(event) => {
        event.preventDefault();
        void retrieve();
      }}>
        <label htmlFor="retrieval-natural-question">你的研究问题（不限于预设问题）</label>
        <input
          id="retrieval-natural-question"
          type="text"
          value={question}
          required
          maxLength={240}
          placeholder="例如：管理层如何描述创新药销售和研发进展？"
          disabled={busy}
          onChange={(event) => {
            setQuestion(event.target.value);
            setPacket(null);
            setMessage("");
          }}
        />
        <button type="submit" className={styles.button} disabled={busy || !question.trim()}>
          {busy ? "正在检索并校验PDF…" : "检索原始证据（不调用模型）"}
        </button>
      </form>
      {message && <div className={styles.error} role="alert"><p>{message}</p></div>}
      {packet && (
        <div className={styles.qaResult} aria-live="polite">
          {packet.status === "WITHHELD" ? (
            <p>未找到词项匹配的原文候选；这不表示公告没有相关事实。可换用公告中的中文术语。</p>
          ) : (
            <>
              <h3>相关原始片段候选（{packet.evidence.length} 条）</h3>
              {packet.terminology_probe.status === "ACTIVATED" && (
                <div className={styles.withheld} role="note">
                  <strong>术语扩展候选（仅用于原文召回）</strong>
                  <p>输入词项：{packet.terminology_probe.matched_cues.join("、")}。</p>
                  <p>独立候选概念：{packet.terminology_probe.candidates.map((x) =>
                    `${x.preferred_zh} (${x.concept_id})`
                  ).join("；")}。</p>
                  {packet.terminology_probe.distinct_concepts_warning === "NON_EQUIVALENT_CANDIDATES" && (
                    <p><strong>部分候选概念已标记为不等价，禁止混合数值或口径。</strong></p>
                  )}
                  <p>这些术语不代表已找到准确答案；当前暂不允许通过扩展结果调用模型草稿。</p>
                </div>
              )}
              {packet.terminology_probe.status === "ACTIVATED" && (
                <p className={styles.qaHelp}>
                  M127 候选排序优先保留不同原文页；金额类问题参考财务术语附近的数字线索。
                  这只是检索启发式，不证明数字属于该概念，也不证明报表口径正确。
                </p>
              )}
              <p className={styles.qaHelp}>
                根据原文词项及有限排序线索展示，尚未评定是否足以回答问题。只引用原始PDF；
                财务报表表格的行列含义没有因检索而被验证。
              </p>
              {packet.statement_heading_alert === "MULTIPLE_STATEMENT_HEADING_CANDIDATES" && (
                <div className={styles.withheld} role="note">
                  <strong>检索结果跨越不同财务报表标题候选。</strong>
                  <p>可能包含合并与母公司等不同报表口径；仅凭数值或词项命中不可混用。
                    请打开原始PDF核对表头、所属报表和期间。尚未完成财务语义审核。</p>
                </div>
              )}
              {packet.evidence.map((hit) => (
                <article key={hit.evidence_id} className={styles.card}>
                  <p className={styles.smallTag}>原文位置 · PDF 第 {hit.source_page} 页</p>
                  <p className={styles.qaHelp}>
                    {hit.statement_heading_cue.status === "STANDALONE_HEADING_CANDIDATE"
                      ? `附近独立报表标题候选：《${hit.statement_heading_cue.heading_verbatim}》（PDF 第 ${hit.statement_heading_cue.heading_page} 页）。仅字面标题线索，不证明该数值的报表或列含义。`
                      : "附近报表标题未定位或文本块跨越标题；报表口径未确定。"}
                  </p>
                  <blockquote className={styles.answerPassage} style={{whiteSpace: "pre-wrap"}}>
                    {hit.source_excerpt}
                  </blockquote>
                  <a className={styles.source} href={`${source.url}#page=${hit.source_page}`}
                    target="_blank" rel="noopener noreferrer">
                    查看原始公告 · PDF 第 {hit.source_page} 页
                  </a>
                  <details className={styles.details}>
                    <summary>查看原文偏移和证据身份</summary>
                    <p className={styles.hash}>证据ID：{hit.evidence_id}</p>
                    <p className={styles.hash}>
                      规范化文本范围：{hit.canonical_start}–{hit.canonical_end}
                    </p>
                    {hit.statement_heading_cue.status === "STANDALONE_HEADING_CANDIDATE" && (
                      <p className={styles.hash}>
                        标题原文偏移：{hit.statement_heading_cue.heading_start}–{hit.statement_heading_cue.heading_end}
                      </p>
                    )}
                  </details>
                </article>
              ))}
            </>
          )}
          {packet.status === "RETRIEVAL_CANDIDATES_READY" &&
            packet.terminology_probe.status === "NO_TRIGGER" && (
            <AnalystPreviewSection
              key={packet.retrieval_id}
              source={source}
              question={packet.question}
              retrievalId={packet.retrieval_id}
              evidenceIds={packet.evidence.map((hit) => hit.evidence_id)}
            />
          )}
          <p className={styles.hash}>检索身份：{packet.retrieval_id}</p>
          <p><strong>检索相关性：未审核 · 报表标题：仅候选线索 · 财务语义：NOT_PERFORMED · 发布：BLOCKED</strong></p>
        </div>
      )}
    </section>
  );
}
