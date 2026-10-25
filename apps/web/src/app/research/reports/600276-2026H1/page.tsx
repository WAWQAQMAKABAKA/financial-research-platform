"use client";

import Link from "next/link";
import { useState } from "react";
import styles from "./report.module.css";

const REPORT_KEY = "600276-2026H1";
const QUESTION_CODE =
  "revenue_and_innovation_source_context_2026H1";

const SOURCE = {
  documentId: "600276-2026H1-cninfo-1225483600",
  url: "https://static.cninfo.com.cn/finalpage/2026-08-20/1225483600.PDF",
  sha: "ff6910663a9726acb889aa061a8bab1433f58890d81ebea013b8c637a097a7aa",
  canonicalSha:
    "96784f9deba244aab85bd117b9a1894bdcbd689a8368554f84014703f1e8b864",
} as const;

type Observation = {
  claim_id: string;
  kind: string;
  text: string;
  evidence_id: string;
  page: number;
  statement_title: string;
  row_label: string;
  column_header: string;
  value_verbatim: string;
  statement_context: string;
  review_result: string;
  review_scope: string;
};

type ManagementStatement = {
  claim_id: string;
  kind: string;
  text: string;
  evidence_id: string;
  page: number;
  review_result: string;
  review_scope: string;
};

type ReportPacket = {
  status: string;
  report_type: string;
  report_key: string;
  report_identity: string;
  source_draft_id: string;
  report_storage: string;
  question_code: string;
  question: string;
  issuer_name: string;
  report_period: string;
  as_of: string;
  generated_at: string;
  document_id: string;
  source_url: string;
  source_sha256: string;
  canonical_sha256: string;
  observations: Observation[];
  management_statement: ManagementStatement;
  analyst_interpretation: {
    status: string;
    reason: string;
  };
  financial_semantic_review: string;
  research_publication: string;
  limitations: string[];
};


type ReviewPacket = {
  status: string;
  report_key: string;
  review_id: string;
  as_of: string;
  draft_origin: string;
  document_id: string;
  source_url: string;
  source_sha256: string;
  canonical_sha256: string;
  financial_semantic_review: string;
  research_publication: string;
  limitation: string;
  claim: {
    claim_id: string;
    kind: string;
    text: string;
    evidence_ids: string[];
  };
  review: {
    claim_id: string;
    verdict: "REJECT" | "UNCERTAIN";
    reason: string;
    compared_evidence_ids: string[];
    review_scope: string;
  };
  evidence: {
    evidence_id: string;
    source_page: number;
    excerpt: string;
    review_scope: string;
  };
};


const REVIEW_REASONS_ZH: Record<string, string> = {
  SOURCE_SHARE_DENOMINATOR_SUBSTITUTED:
    "原文以药品销售收入为分母，而拟议表述错误地替换为公司整体营业收入。",
  SOURCE_SHARE_PERCENTAGE_MISMATCH:
    "拟议占比与当前所引管理层原文不一致。",
  SOURCE_SHARE_NOT_FINANCIALLY_QUALIFIED:
    "拟议表述保留了原文的药品销售收入分母，但财务语义尚未独立核验。",
  SOURCE_GROWTH_METRIC_SUBSTITUTED:
    "把创新药销售收入的增长率错误归于公司整体营业收入。",
  SOURCE_GROWTH_DIRECTION_MISMATCH:
    "拟议表述的增长或下降方向与当前所引原文不一致。",
  SOURCE_GROWTH_NOT_FINANCIALLY_QUALIFIED:
    "增长表述与所引原文一致，但尚未完成独立财务语义核验。",
  GROWTH_PERCENTAGE_NOT_SOURCE_MATCHED:
    "增长比例与当前所引原文不匹配，尚无法确认。",
  NARRATIVE_NOT_ASSERTED_UNAMBIGUOUSLY:
    "表述存在疑问、否定或条件语气，无法按明确断言核验。",
  NARRATIVE_NOT_WITHIN_BOUNDED_GRAMMAR:
    "当前限定规则无法识别该表述，不能视为核验通过。",
  UNSTRUCTURED_NARRATIVE:
    "该表述超出当前可处理的范围。",
};

const LIMITATIONS_ZH: Record<string, string> = {
  "Statement cells are verified literal source observations.":
    "财务报表数值仅完成原始位置和字面内容核验。",
  "Management statements are attributed, not independently endorsed.":
    "管理层表述仅作注明来源的引用，不代表独立认可。",
  "No financial comparability, causality, inference, or publication is approved.":
    "尚未批准财务数据可比性、因果推断、分析结论或报告发布。",
};

function verdictZh(value: "REJECT" | "UNCERTAIN"): string {
  return value === "REJECT"
    ? "与所引原文不符"
    : "尚无法确认";
}

function reviewReasonZh(code: string): string {
  return REVIEW_REASONS_ZH[code] ??
    `未识别的核验原因（${code}）；不得视为已通过核验。`;
}

const EXPECTED_ROWS = [
  { title: "合并利润表", row: "其中：营业收入" },
  { title: "母公司利润表", row: "一、营业收入" },
] as const;

const MANAGEMENT_SENTENCE =
  /^2026年上半年公司创新药销售收入\d+(?:\.\d+)?亿元，同比增长\d+(?:\.\d+)?%，占药品销售收入的比重达\d+(?:\.\d+)?%[。]$/u;

const HASH = /^[a-f0-9]{64}$/;
const AMOUNT = /^[0-9][0-9,]*\.[0-9]{2}$/;

function record(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" &&
    v !== null &&
    !Array.isArray(v);
}

function norm(v: string): string {
  return v.replace(/\s/g, "");
}

function verifiedReport(v: unknown): v is ReportPacket {
  if (!record(v)) return false;

  const r = v;
  const management = r.management_statement;
  const interpretation = r.analyst_interpretation;

  if (
    r.status !== "LOCAL_SOURCE_REPORT_READY" ||
    r.report_type !== "UNPUBLISHED_SOURCE_REPORT_PREVIEW" ||
    r.report_key !== REPORT_KEY ||
    r.question_code !== QUESTION_CODE ||
    r.issuer_name !== "恒瑞医药" ||
    r.report_period !== "2026H1" ||
    r.document_id !== SOURCE.documentId ||
    r.source_url !== SOURCE.url ||
    r.source_sha256 !== SOURCE.sha ||
    r.canonical_sha256 !== SOURCE.canonicalSha ||
    r.report_storage !== "NOT_PERSISTED" ||
    r.research_publication !== "BLOCKED" ||
    r.financial_semantic_review !== "NOT_PERFORMED" ||
    typeof r.report_identity !== "string" ||
    !HASH.test(r.report_identity) ||
    typeof r.source_draft_id !== "string" ||
    !HASH.test(r.source_draft_id) ||
    typeof r.as_of !== "string" ||
    !Number.isFinite(Date.parse(r.as_of)) ||
    typeof r.generated_at !== "string" ||
    !Number.isFinite(Date.parse(r.generated_at)) ||
    typeof r.question !== "string" ||
    !r.question.trim() ||
    !Array.isArray(r.observations) ||
    r.observations.length !== 2 ||
    !record(management) ||
    !record(interpretation) ||
    interpretation.status !== "WITHHELD" ||
    interpretation.reason !==
      "FINANCIAL_SEMANTIC_REVIEW_NOT_PERFORMED" ||
    !Array.isArray(r.limitations) ||
    r.limitations.length !== 3 ||
    !r.limitations.every(
      (x: unknown) => typeof x === "string" && !!x.trim()
    )
  ) {
    return false;
  }

  const evidenceIds = new Set<string>();

  for (let i = 0; i < 2; i++) {
    const o = r.observations[i];
    const expected = EXPECTED_ROWS[i];

    if (!record(o)) return false;

    if (
      o.claim_id !== `REV${i + 1}` ||
      o.kind !== "SOURCE_LITERAL_OBSERVATION" ||
      typeof o.statement_title !== "string" ||
      norm(o.statement_title) !== expected.title ||
      typeof o.row_label !== "string" ||
      norm(o.row_label) !== expected.row ||
      typeof o.column_header !== "string" ||
      norm(o.column_header) !== "2026年半年度" ||
      typeof o.value_verbatim !== "string" ||
      !AMOUNT.test(o.value_verbatim) ||
      typeof o.statement_context !== "string" ||
      !o.statement_context.trim() ||
      typeof o.evidence_id !== "string" ||
      !HASH.test(o.evidence_id) ||
      typeof o.page !== "number" ||
      !Number.isInteger(o.page) ||
      o.page < 1 ||
      o.page > 182 ||
      o.review_result !== "SOURCE_LOCATION_VERIFIED_ONLY" ||
      o.review_scope !== "LITERAL_CELL_LOCATION_ONLY" ||
      typeof o.text !== "string" ||
      o.text !==
        `In the source section "${o.statement_title}", ` +
        `the row "${o.row_label}" under ` +
        `"${o.column_header}" reads "${o.value_verbatim}".` ||
      evidenceIds.has(o.evidence_id)
    ) {
      return false;
    }

    evidenceIds.add(o.evidence_id);
  }

  return (
    management.claim_id === "M1" &&
    management.kind === "ATTRIBUTED_MANAGEMENT_STATEMENT" &&
    management.review_result === "SOURCE_PASSAGE_LOCATED_ONLY" &&
    management.review_scope ===
      "NATIVE_PDF_TEXT_AND_WORD_LOCATION_ONLY" &&
    management.page === 20 &&
    typeof management.text === "string" &&
    MANAGEMENT_SENTENCE.test(management.text) &&
    typeof management.evidence_id === "string" &&
    HASH.test(management.evidence_id) &&
    !evidenceIds.has(management.evidence_id)
  );
}


function verifiedClaimReview(
  value: unknown,
  submittedText: string,
  source: ReportPacket,
): value is ReviewPacket {
  if (!record(value)) return false;

  const v = value;
  const c = v.claim;
  const r = v.review;
  const e = v.evidence;

  if (!record(c) || !record(r) || !record(e)) {
    return false;
  }
  const management = source.management_statement;

  return (
    v.status === "UNPUBLISHED_ANALYST_CANDIDATE_REVIEWED" &&
    v.report_key === source.report_key &&
    v.draft_origin === "MANUAL_ANALYST_DRAFT" &&
    v.document_id === source.document_id &&
    v.source_url === source.source_url &&
    v.source_sha256 === source.source_sha256 &&
    v.canonical_sha256 === source.canonical_sha256 &&
    v.financial_semantic_review === "NOT_QUALIFIED" &&
    v.research_publication === "BLOCKED" &&
    typeof v.review_id === "string" &&
    HASH.test(v.review_id) &&
    typeof v.as_of === "string" &&
    Number.isFinite(Date.parse(v.as_of)) &&
    typeof v.limitation === "string" &&
    !!v.limitation.trim() &&
    c.claim_id === "MC1" &&
    c.kind === "OBSERVED_FACT" &&
    c.text === submittedText &&
    Array.isArray(c.evidence_ids) &&
    c.evidence_ids.length === 1 &&
    c.evidence_ids[0] === management.evidence_id &&
    r.claim_id === c.claim_id &&
    (r.verdict === "REJECT" ||
      r.verdict === "UNCERTAIN") &&
    typeof r.reason === "string" &&
    /^[A-Z][A-Z0-9_]{2,100}$/.test(r.reason) &&
    r.review_scope ===
      "BOUNDED_NARRATIVE_CONTRADICTION_ONLY" &&
    Array.isArray(r.compared_evidence_ids) &&
    r.compared_evidence_ids.length === 1 &&
    r.compared_evidence_ids[0] === management.evidence_id &&
    e.evidence_id === management.evidence_id &&
    e.source_page === management.page &&
    e.excerpt === management.text &&
    e.review_scope === management.review_scope
  );
}

function exampleClaim(
  source: ReportPacket,
  denominator: "公司总营业收入" | "药品销售收入",
): string {
  const share = source.management_statement.text.match(
    /比重达([0-9]+(?:\.[0-9]+)?)%/,
  );

  if (!share) return "";

  return `创新药销售收入占${denominator}的${share[1]}%。`;
}

function OriginalLink({ page }: { page: number }) {
  return (
    <a
      className={styles.source}
      href={`${SOURCE.url}#page=${page}`}
      target="_blank"
      rel="noopener noreferrer"
    >
      查看原始公告 · PDF第{page}页 ↗
    </a>
  );
}

export default function HengruiSourceReport() {
  const [report, setReport] = useState<ReportPacket | null>(null);
  const [loading, setLoading] = useState(false);
  const [reportRequested, setReportRequested] = useState(false);
  const [error, setError] = useState("");
  const [candidate, setCandidate] = useState("");
  const [reviewPacket, setReviewPacket] =
    useState<ReviewPacket | null>(null);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewError, setReviewError] = useState("");

  async function loadReport() {
    if (loading || reviewBusy) return;

    setReviewPacket(null);
    setReviewError("");
    setCandidate("");
    setReportRequested(true);
    setLoading(true);
    setReport(null);
    setError("");

    try {
      const response = await fetch("/api/local-source-report", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ report_key: REPORT_KEY }),
        cache: "no-store",
      });

      if (!response.ok) throw new Error("REPORT_UNAVAILABLE");

      const packet: unknown = await response.json();

      if (!verifiedReport(packet)) {
        throw new Error("REPORT_CONTRACT_NOT_QUALIFIED");
      }

      setReport(packet);
    } catch {
      setError(
        "原始报告不可用，或未通过来源及核验关系检查；" +
        "本次不展示未经确认的报告内容。"
      );
    } finally {
      setLoading(false);
    }
  }


  async function reviewCandidate() {
    if (
      !report ||
      loading ||
      reviewBusy ||
      !candidate.trim() ||
      candidate.length > 400 ||
      new TextEncoder().encode(candidate).length > 1200
    ) {
      return;
    }

    const submittedText = candidate;
    const sourceReport = report;

    setReviewBusy(true);
    setReviewPacket(null);
    setReviewError("");

    try {
      const response = await fetch(
        "/api/local-analyst-draft-review",
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            report_key: REPORT_KEY,
            candidate_text: submittedText,
          }),
          cache: "no-store",
        },
      );

      if (!response.ok) {
        throw new Error("REVIEW_UNAVAILABLE");
      }

      const packet: unknown = await response.json();

      if (
        !verifiedClaimReview(
          packet,
          submittedText,
          sourceReport,
        )
      ) {
        throw new Error("REVIEW_EVIDENCE_MISMATCH");
      }

      setReviewPacket(packet);
    } catch {
      setReviewError(
        "观点核验不可用，或引用证据与当前报告不一致；" +
        "本次不展示核验结论。",
      );
    } finally {
      setReviewBusy(false);
    }
  }

  return (
    <main className={styles.page}>
      <div className={styles.shell}>

        <header className={styles.top}>
          <Link href="/research" className={styles.brand}>
            FR / 金融研究平台
          </Link>
          <Link href="/research" className={styles.back}>
            ← 返回研究首页
          </Link>
        </header>

        <section className={styles.hero}>
          <p className={styles.kicker}>
            原始证据研究报告 / 本地预览
          </p>

          <h1>
            恒瑞医药 <span>2026年半年度研究</span>
          </h1>

          <p>
            基于原始公告展示两项财务报表数据及一段管理层披露。
            每项证据均保留原始来源。尚未进行会计口径勾稽、
            财务语义认定、估值分析或投资判断。
          </p>

          <div className={styles.heroMeta}>
            <span>600276 · 2026年上半年</span>
            <span>公告日期：2026年8月20日</span>
            <span>本地预览 · 尚未发布</span>
          </div>
        </section>

        <LiveQuestionSection />

        <div className={styles.toolbar}>
          <div>
            <strong>查看完整原始证据包（可选）</strong>
            <p>
              重新校验本地原始PDF、文件哈希及证据关联。
              不调用付费模型，不保存或发布研究报告。
            </p>
          </div>

          <button
            type="button"
            className={styles.button}
            onClick={loadReport}
            disabled={loading || reviewBusy}
          >
            {loading ? "正在核验原始公告…" : "展开完整证据报告"}
          </button>
        </div>

        {error && (
          <div className={styles.error} role="alert">
            <strong>报告内容暂不展示</strong>
            <p>{error}</p>
            <p>财务语义核验尚未完成，研究发布仍被阻止。</p>
          </div>
        )}

        {reportRequested && !report && !error && (
          <section className={styles.empty} aria-live="polite">
            <h2>
              {loading
                ? "正在核对原始证据…"
                : "尚未生成研究预览"}
            </h2>
            <p>
              只有原始公告及其证据关联通过核验，
              才会展示对应的研究内容。
            </p>
          </section>
        )}

        {report && (
          <div aria-live="polite">
            <nav
              className={styles.reportNav}
              aria-label="研究报告内容导航"
            >
              <a href="#evidence-summary">核心回答与来源</a>
              <a href="#claim-review">核验研究观点</a>
              <a href="#evidence-details">详细证据与溯源</a>
            </nav>

            <section
              className={styles.answerFirst}
              id="evidence-summary"
              aria-label="原始证据摘要"
            >
              <p className={styles.kicker}>
                原始证据摘要 / 优先阅读
              </p>
              <h2>目前找到哪些证据？</h2>

              <div
                className={styles.directAnswer}
                aria-label="核心研究问题的直接回答"
              >
                <p className={styles.directAnswerTitle}>
                  核心研究问题 · 直接回答
                </p>

                <p>
                  在原始公告的
                  《{report.observations[0].statement_title}》中，
                  “{report.observations[0].row_label}”
                  对应的原始数值为
                  <strong>
                    {" "}{report.observations[0].value_verbatim}
                  </strong>
                  ；在
                  《{report.observations[1].statement_title}》中，
                  “{report.observations[1].row_label}”
                  对应的原始数值为
                  <strong>
                    {" "}{report.observations[1].value_verbatim}
                  </strong>
                  。两项数值属于不同报表列示，
                  本报告未认定它们可以直接比较或勾稽。
                </p>

                <p>
                  关于创新药销售，当前定位到的管理层原文为：
                  <span className={styles.directQuote}>
                    {report.management_statement.text}
                  </span>
                </p>

                <p className={styles.directCaution}>
                  重要口径提示：上述63.16%的分母，
                  按管理层原文为“药品销售收入”，
                  不应直接改写成占公司整体营业收入的比例。
                  这属于原文表述辨析，尚非独立财务语义认定。
                </p>

                <div className={styles.directCitations}>
                  <a
                    href={`${SOURCE.url}#page=${report.observations[0].page}`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    REV1 · 原始PDF第{report.observations[0].page}页 ↗
                  </a>
                  <a
                    href={`${SOURCE.url}#page=${report.observations[1].page}`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    REV2 · 原始PDF第{report.observations[1].page}页 ↗
                  </a>
                  <a
                    href={`${SOURCE.url}#page=${report.management_statement.page}`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    M1 · 原始PDF第{report.management_statement.page}页 ↗
                  </a>
                </div>
              </div>

              <p className={styles.answerIntro}>
                在恒瑞医药2026年半年度原始公告中，
                已定位两项财务报表营业收入数据，
                以及一段管理层关于创新药销售的披露。
                以下数值均保留各自的来源和原始口径。
              </p>

              <div className={styles.answerGrid}>
                {report.observations.map((o) => (
                  <article
                    key={o.claim_id}
                    className={styles.answerItem}
                  >
                    <span className={styles.smallTag}>
                      {o.claim_id} · 财务报表原始数据
                    </span>

                    <h3>{o.statement_title}</h3>
                    <p className={styles.answerRow}>
                      {o.row_label}
                    </p>
                    <p className={styles.answerValue}>
                      {o.value_verbatim}
                    </p>

                    <p className={styles.answerContext}>
                      公告印刷口径：{o.statement_context}
                    </p>

                    <OriginalLink page={o.page} />
                  </article>
                ))}
              </div>

              <article className={styles.answerManagement}>
                <span className={styles.smallTag}>
                  M1 · 注明来源的管理层原文
                </span>

                <h3>创新药销售情况</h3>

                <blockquote className={styles.answerPassage}>
                  {report.management_statement.text}
                </blockquote>

                <p className={styles.answerContext}>
                  该段为管理层披露的原文，
                  不是已获得独立财务语义核验的研究结论。
                </p>

                <OriginalLink
                  page={report.management_statement.page}
                />
              </article>

              <div className={styles.answerBoundary}>
                <strong>
                  这些证据目前尚不能证明什么？
                </strong>

                <p>
                  尚未完成两项报表数据之间的口径可比性核验，
                  也未建立其与创新药销售收入之间的财务勾稽关系。
                  当前定位结果不能直接证明因果关系或公司整体收入增长。
                  这不意味着完整公告不存在其他相关证据。
                </p>

                <p>
                  分析结论：暂不生成。
                  财务语义核验：未完成。
                  研究发布：已阻止。
                </p>
              </div>
            </section>

            <section
              className={styles.challenge}
              id="claim-review"
              aria-label="核验研究观点"
            >
              <p className={styles.kicker}>
                研究观点核验 / 指定管理层原文
              </p>

              <h2>拟提出的观点是否符合原文？</h2>

              <p className={styles.challengeIntro}>
                将拟议表述与原始公告第20页的管理层原文比对。
                当前规则只能识别限定句式中的明确矛盾，
                或返回“尚无法确认”。
                不能据此批准完整的财务研究结论。
              </p>

              <p className={styles.challengeIntro}>
                当前支持少量明确的中文断言句式，
                包括创新药销售收入占比及同比增长表述。
                其他句式、疑问或带条件的表达仍可能返回“尚无法确认”。
                这不代表观点正确，也不构成独立财务语义核验。
              </p>

              <div className={styles.challengeOptions}>
                <button
                  type="button"
                  disabled={reviewBusy}
                  onClick={() => {
                    setCandidate(
                      exampleClaim(
                        report,
                        "公司总营业收入",
                      ),
                    );
                    setReviewPacket(null);
                    setReviewError("");
                  }}
                >
                  示例一：错误替换收入分母
                </button>

                <button
                  type="button"
                  disabled={reviewBusy}
                  onClick={() => {
                    setCandidate(
                      exampleClaim(
                        report,
                        "药品销售收入",
                      ),
                    );
                    setReviewPacket(null);
                    setReviewError("");
                  }}
                >
                  示例二：保留原文收入分母
                </button>
              </div>

              <label
                htmlFor="m114-candidate"
                className={styles.challengeLabel}
              >
                待核验表述
              </label>

              <textarea
                id="m114-candidate"
                className={styles.challengeInput}
                rows={3}
                maxLength={400}
                disabled={reviewBusy}
                value={candidate}
                onChange={(event) => {
                  setCandidate(event.target.value);
                  setReviewPacket(null);
                  setReviewError("");
                }}
                placeholder="输入有关管理层披露的拟议表述…"
              />

              <div className={styles.challengeActions}>
                <span>
                  {candidate.length}/400字 ·
                  仅限本地原始证据核验
                </span>

                <button
                  type="button"
                  className={styles.button}
                  disabled={
                    reviewBusy ||
                    !candidate.trim() ||
                    candidate.length > 400 ||
                    new TextEncoder().encode(candidate).length > 1200
                  }
                  onClick={reviewCandidate}
                >
                  {reviewBusy
                    ? "正在核验表述…"
                    : "核验这项观点"}
                </button>
              </div>

              {reviewError && (
                <div
                  className={styles.challengeError}
                  role="alert"
                >
                  <strong>本次观点核验未能完成</strong>
                  <p>{reviewError}</p>
                  <p>研究发布仍处于阻止状态。</p>
                </div>
              )}

              {reviewPacket && (
                <article
                  className={styles.challengeResult}
                  aria-live="polite"
                >
                  <p className={styles.kicker}>
                    原始证据观点核验 / 尚未发布
                  </p>

                  <h3>
                    核验结果：
                    {verdictZh(reviewPacket.review.verdict)}
                  </h3>

                  <p>
                    <strong>待核验表述：</strong>{" "}
                    {reviewPacket.claim.text}
                  </p>

                  <p>
                    <strong>核验依据：</strong>{" "}
                    {reviewReasonZh(
                      reviewPacket.review.reason
                    )}
                  </p>

                  <div className={styles.challengeEvidence}>
                    <strong>用于比对的管理层原文</strong>

                    <blockquote>
                      {reviewPacket.evidence.excerpt}
                    </blockquote>

                    <OriginalLink
                      page={reviewPacket.evidence.source_page}
                    />
                  </div>

                  <p className={styles.challengeCaution}>
                    “与所引原文不符”仅指当前限定规则识别到的
                    原文矛盾，不代表已全面核验整份公告。
                    “尚无法确认”不等于核验通过。
                    财务语义尚未独立认定，研究发布已阻止。
                  </p>

                  <details className={styles.details}>
                    <summary>
                      查看观点、核验记录与证据身份
                    </summary>

                    <p>
                      观点编号：{reviewPacket.claim.claim_id}
                    </p>
                    <p className={styles.hash}>
                      证据编号：
                      {reviewPacket.evidence.evidence_id}
                    </p>
                    <p className={styles.hash}>
                      核验记录编号：{reviewPacket.review_id}
                    </p>
                    <p className={styles.hash}>
                      所属研究报告：{report.report_identity}
                    </p>
                    <p>
                      核验范围：仅限指定管理层原文的矛盾识别
                    </p>
                    <p>核验时点：{reviewPacket.as_of}</p>
                    <p className={styles.hash}>
                      原始核验原因代码：
                      {reviewPacket.review.reason}
                    </p>
                  </details>
                </article>
              )}
            </section>

            <div className={styles.summary}>
              <div>
                <span>财务报表原始数据</span>
                <strong>02</strong>
                <small>已核验原始位置与字面内容</small>
              </div>

              <div>
                <span>管理层披露</span>
                <strong>01</strong>
                <small>已定位并注明来源的原文</small>
              </div>

              <div>
                <span>独立财务语义核验</span>
                <strong className={styles.blocked}>
                  尚未完成
                </strong>
                <small>研究发布已阻止</small>
              </div>
            </div>

            <details
              className={styles.appendix}
              id="evidence-details"
            >
              <summary>
                展开完整证据、核验范围与溯源记录
              </summary>
              <p className={styles.appendixHint}>
                包含逐项报表数值、管理层原文、证据编号、
                PDF文件哈希和未完成的财务语义核验事项。
              </p>

            <section className={styles.intro}>
              <p className={styles.kicker}>
                01 / 核心研究问题
              </p>
              <h2>营业收入数据与管理层披露</h2>

              <p>
                恒瑞医药2026年半年度报告中有哪些
                营业收入相关数据和创新药销售披露？
                现有证据能够证明什么，
                哪些财务解释仍需进一步核验？
              </p>

              <p className={styles.note}>
                当前展示的是已核验来源位置的研究预览，
                不构成独立会计口径或财务指标可比性认定。
              </p>
            </section>

            <div className={styles.grid}>
              <div>
                <section className={styles.sectionBlock}>
                  <div className={styles.sectionHead}>
                    <div>
                      <p className={styles.kicker}>
                        02 / 财务报表证据
                      </p>
                      <h2>财务报表数据及核验记录</h2>
                    </div>
                    <span className={styles.smallTag}>
                      已定位2项数据
                    </span>
                  </div>

                  {report.observations.map((o) => (
                    <article
                      key={o.claim_id}
                      className={styles.card}
                    >
                      <div className={styles.cardTop}>
                        <span className={styles.smallTag}>
                          {o.claim_id} · 原始报表单元格
                        </span>
                      </div>

                      <h3>{o.statement_title}</h3>
                      <div className={styles.value}>
                        {o.value_verbatim}
                      </div>

                      <p className={styles.label}>
                        原始行名：{o.row_label}
                      </p>
                      <p className={styles.label}>
                        原始列名：{o.column_header}
                      </p>
                      <p className={styles.note}>
                        印刷单位及期间：{o.statement_context}
                      </p>

                      <div className={styles.review}>
                        已核验来源位置及字面数值
                        <p>
                          不代表已经独立认定其会计口径。
                        </p>
                      </div>

                      <OriginalLink page={o.page} />

                      <details className={styles.details}>
                        <summary>
                          查看原文单元格与证据关联
                        </summary>
                        <p>
                          在“{o.statement_title}”中，
                          “{o.column_header}”列下，
                          “{o.row_label}”的原始数值为
                          “{o.value_verbatim}”。
                        </p>
                        <p className={styles.hash}>
                          证据编号：{o.evidence_id}
                        </p>
                        <p>
                          核验范围：原始单元格位置与字面内容
                        </p>
                      </details>
                    </article>
                  ))}
                </section>

                <section className={styles.sectionBlock}>
                  <p className={styles.kicker}>
                    03 / 管理层原文
                  </p>
                  <h2>创新药销售披露</h2>

                  <article className={styles.card}>
                    <span className={styles.smallTag}>
                      M1 · 注明来源的管理层表述
                    </span>

                    <blockquote className={styles.passage}>
                      {report.management_statement.text}
                    </blockquote>

                    <p className={styles.note}>
                      上述销售金额、增长率及收入分母
                      均来自管理层原文，
                      并非独立认定的会计结论。
                    </p>

                    <div className={styles.review}>
                      已定位管理层原文 · 财务语义尚未核验
                    </div>

                    <OriginalLink
                      page={report.management_statement.page}
                    />

                    <details className={styles.details}>
                      <summary>查看管理层证据关联</summary>
                      <p className={styles.hash}>
                        证据编号：
                        {report.management_statement.evidence_id}
                      </p>
                      <p>
                        核验范围：原始PDF文本及文字位置
                      </p>
                    </details>
                  </article>
                </section>

                <section className={styles.sectionBlock}>
                  <p className={styles.kicker}>
                    04 / 研究解释
                  </p>
                  <h2>分析结论暂不生成</h2>

                  <div className={styles.withheld}>
                    <strong>暂不提供分析结论</strong>
                    <p>
                      原因：尚未完成独立财务语义核验。
                    </p>
                    <p>
                      当前来源定位结果不能单独支持
                      财务数据勾稽、因果解释、
                      投资观点或前瞻性判断。
                    </p>
                  </div>
                </section>
              </div>

              <aside className={styles.side}>
                <section className={styles.sideCard}>
                  <p className={styles.kicker}>
                    研究发布限制
                  </p>
                  <h2>证据通过定位，不等于结论获批</h2>

                  <dl className={styles.facts}>
                    <div>
                      <dt>研究发布</dt>
                      <dd>已阻止</dd>
                    </div>
                    <div>
                      <dt>财务语义核验</dt>
                      <dd>尚未完成</dd>
                    </div>
                    <div>
                      <dt>报告存储</dt>
                      <dd>未持久化保存</dd>
                    </div>
                  </dl>
                </section>

                <section className={styles.sideCard}>
                  <p className={styles.kicker}>
                    原始来源与证据溯源
                  </p>

                  <h2>原始公告</h2>

                  <p className={styles.note}>
                    恒瑞医药 · 2026年半年度
                  </p>

                  <a
                    href={SOURCE.url}
                    className={styles.source}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    查看完整原始PDF ↗
                  </a>

                  <details className={styles.details}>
                    <summary>
                      查看报告身份和文件哈希
                    </summary>

                    <p className={styles.hash}>
                      报告身份编号：{report.report_identity}
                    </p>
                    <p className={styles.hash}>
                      来源草稿编号：{report.source_draft_id}
                    </p>
                    <p className={styles.hash}>
                      原始文档编号：{report.document_id}
                    </p>
                    <p className={styles.hash}>
                      原始PDF SHA-256：
                      {report.source_sha256}
                    </p>
                    <p className={styles.hash}>
                      规范化文本 SHA-256：
                      {report.canonical_sha256}
                    </p>
                    <p>
                      研究时点：{report.as_of}
                    </p>
                    <p>
                      报告生成时间：{report.generated_at}
                    </p>
                  </details>
                </section>

                <section className={styles.sideCard}>
                  <p className={styles.kicker}>
                    研究限制
                  </p>

                  <ul className={styles.limits}>
                    {report.limitations.map((item) => (
                      <li key={item}>
                        {LIMITATIONS_ZH[item] ??
                          `尚未翻译的原始研究限制：${item}`}
                      </li>
                    ))}
                  </ul>
                </section>
              </aside>
            </div>
            </details>

          </div>
        )}

        <footer className={styles.footer}>
          <span>
            金融研究平台 · 原始证据研究预览
          </span>
          <span>
            独立财务语义核验尚未完成 · 禁止对外发布
          </span>
        </footer>

      </div>
    </main>
  );
}

// M120: two bounded research questions with distinct evidence semantics.
type ResearchKind = "CONSOLIDATED_REVENUE" | "INNOVATIVE_SHARE_OF_DRUG_SALES";

const DEFAULT_QUESTION = "恒瑞医药2026年上半年合并营业收入是多少？";
const SHARE_QUESTION =
  "恒瑞医药2026年上半年创新药销售收入占药品销售收入的比例是多少？";

function classifyQuestion(question: string): ResearchKind | null {
  if (question.length > 240 || new TextEncoder().encode(question).length > 800) {
    return null;
  }
  const q = question.normalize("NFKC").toLowerCase().replace(/\s/g, "");
  const issuer = /恒瑞医药|600276|hengrui/u.test(q);
  const period = /2026.{0,6}(上半年|半年度|h1)|firsthalfof2026/u.test(q);
  if (!issuer || !period) return null;
  if (/买入|卖出|仓位|持仓|预测|forecast|buy|sell|同比|增长|growth|利润|profit|毛利|margin|母公司|parent/iu.test(q)) {
    return null;
  }
  const innovative = /创新药|innovative/iu.test(q);
  const drugSales = /药品销售收入|drugsales/iu.test(q);
  const share = /占|比例|比重|share|percentage|percent/iu.test(q);
  const company = /合并|公司整体|公司总|公司全部|总营业收入|总营收|consolidated|companyrevenue|totalrevenue|overallcompany/iu.test(q);
  if (innovative && drugSales && share && !company) {
    return "INNOVATIVE_SHARE_OF_DRUG_SALES";
  }
  if (innovative || drugSales || share) return null;
  if (company && /营业收入|营收|revenue/iu.test(q)) {
    return "CONSOLIDATED_REVENUE";
  }
  return null;
}

function verifiedQuestionIntent(
  value: unknown,
  question: string,
  kind: ResearchKind,
): boolean {
  if (!record(value)) return false;
  const p = value.proposal;
  if (!record(p)) return false;
  const metric = p.metric_candidate;
  const scope = p.reporting_scope_candidate;
  if (
    value.status !== "INTENT_PROPOSAL_READY" ||
    value.model !== "deepseek-flash" ||
    value.report_key !== REPORT_KEY ||
    value.answer_kind !== kind ||
    value.interpretation_status !== "UNVERIFIED_PROPOSAL" ||
    value.financial_semantic_review !== "NOT_PERFORMED" ||
    value.research_publication !== "BLOCKED" ||
    p.question !== question ||
    typeof p.question_sha256 !== "string" ||
    !HASH.test(p.question_sha256) ||
    p.interpretation_status !== "UNVERIFIED_PROPOSAL" ||
    p.financial_semantic_review !== "NOT_PERFORMED" ||
    p.research_publication !== "BLOCKED" ||
    typeof metric !== "string"
  ) return false;
  if (kind === "CONSOLIDATED_REVENUE") {
    return (
      p.operation_candidate === "LOOKUP" &&
      p.numerator_candidate === null &&
      p.denominator_candidate === null &&
      /营业收入|营收|revenue/iu.test(metric) &&
      !/创新药|药品销售|母公司|parent/iu.test(metric) &&
      typeof scope === "string" &&
      /合并|consolidated/iu.test(scope)
    );
  }
  const numerator = p.numerator_candidate;
  const denominator = p.denominator_candidate;
  return (
    p.operation_candidate === "RATIO" &&
    typeof numerator === "string" &&
    /创新药|innovative/iu.test(numerator) &&
    typeof denominator === "string" &&
    /药品销售收入|drug\s*sales|pharmaceutical\s*sales/iu.test(denominator) &&
    !/合并|公司整体|公司总|公司全部|consolidated|companyrevenue|totalrevenue|parent/iu.test(denominator) &&
    !(typeof scope === "string" &&
      /合并|母公司|公司整体|公司总|公司全部|consolidated|companyrevenue|totalrevenue|parent/iu.test(scope))
  );
}

function LiveQuestionSection() {
  const [question, setQuestion] = useState(DEFAULT_QUESTION);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<{
    question: string;
    kind: ResearchKind;
    source: ReportPacket;
  } | null>(null);

  function selectExample(example: string) {
    if (busy) return;
    setQuestion(example);
    setResult(null);
    setError("");
  }

  async function askQuestion() {
    const submitted = question.trim();
    if (busy || !submitted || submitted.length > 240) return;
    const kind = classifyQuestion(submitted);
    if (!kind) {
      setResult(null);
      setError(
        "目前仅支持合并营业收入查询，或创新药销售收入占药品销售收入的管理层披露查询；未调用付费模型。",
      );
      return;
    }
    setBusy(true);
    setError("");
    setResult(null);

    try {
      // A paid interpretation is independent from the subsequent source verification.
      const intentResponse = await fetch("/api/local-question-intent", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ report_key: REPORT_KEY, question: submitted }),
        cache: "no-store",
      });
      if (!intentResponse.ok) throw new Error("INTENT_UNAVAILABLE");
      const intent: unknown = await intentResponse.json();
      if (!verifiedQuestionIntent(intent, submitted, kind)) {
        throw new Error("INTENT_NOT_QUALIFIED");
      }

      const sourceResponse = await fetch("/api/local-source-report", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ report_key: REPORT_KEY }),
        cache: "no-store",
      });
      if (!sourceResponse.ok) throw new Error("SOURCE_UNAVAILABLE");
      const source: unknown = await sourceResponse.json();
      if (!verifiedReport(source)) throw new Error("SOURCE_NOT_QUALIFIED");
      if (kind === "INNOVATIVE_SHARE_OF_DRUG_SALES" &&
        !/占药品销售收入的比重达\d+(?:\.\d+)?%/u.test(source.management_statement.text)) {
        throw new Error("SHARE_SOURCE_MISSING");
      }
      setResult({ question: submitted, kind, source });
    } catch {
      setError(
        "问题解释或原始PDF证据核验未通过。未生成财务结论；" +
        "研究发布仍被阻止。",
      );
    } finally {
      setBusy(false);
    }
  }

  const observation = result?.source.observations[0];
  const management = result?.source.management_statement;
  const disclosedShare = management?.text.match(
    /占药品销售收入的比重达(\d+(?:\.\d+)?)%/u,
  );

  return (
    <section className={styles.qaPanel} aria-label="DeepSeek原始披露问答">
      <p className={styles.kicker}>限定问题研究 / 本地实验</p>
      <h2>向恒瑞医药半年度公告提问</h2>
      <p className={styles.qaHelp}>
        当前支持两种来源定位：合并营业收入，以及管理层披露的
        创新药销售收入占药品销售收入比例。每次提交可能产生一次
        DeepSeek API费用；原始PDF不发送给模型。
      </p>
      <div className={styles.qaExamples} aria-label="示例研究问题">
        <button type="button" disabled={busy} onClick={() => selectExample(DEFAULT_QUESTION)}>
          合并营业收入
        </button>
        <button type="button" disabled={busy} onClick={() => selectExample(SHARE_QUESTION)}>
          创新药占药品销售收入
        </button>
      </div>
      <form className={styles.qaForm} onSubmit={(event) => {
        event.preventDefault();
        void askQuestion();
      }}>
        <label htmlFor="m119-financial-question">研究问题</label>
        <input
          id="m119-financial-question"
          type="text"
          required
          maxLength={240}
          value={question}
          disabled={busy}
          onChange={(event) => {
            setQuestion(event.target.value);
            setResult(null);
            setError("");
          }}
        />
        <button className={styles.button} type="submit" disabled={busy || !question.trim()}>
          {busy ? "正在核对问题与来源…" : "调用DeepSeek并核验原始PDF（计费）"}
        </button>
      </form>
      {error && (
        <div className={styles.error} role="alert">
          <strong>本次研究内容未能展示</strong>
          <p>{error}</p>
        </div>
      )}
      {result && (
        <article className={styles.qaResult} aria-live="polite">
          <p className={styles.smallTag}>
            模型识别：{result.kind === "CONSOLIDATED_REVENUE" ? "LOOKUP" : "RATIO"}
            （未经独立财务语义认定）
          </p>
          <p><strong>所提问题：</strong>{result.question}</p>
          {result.kind === "CONSOLIDATED_REVENUE" && observation && (
            <>
              <h3>原始公告找到的合并利润表营业收入行</h3>
              <p className={styles.answerValue}>{observation.value_verbatim}</p>
              <p>
                来源：《{observation.statement_title}》 ·
                “{observation.row_label}” ·
                “{observation.column_header}” · 人民币元。
              </p>
              <OriginalLink page={observation.page} />
              <p className={styles.qaHelp}>
                该数值来自重新核验的原始PDF单元格，并非模型生成。
                公告日期为2026年8月20日；模型对披露时间的猜测不能作为事实。
                仅核验原文位置与字面数值。
              </p>
              <p className={styles.hash}>证据ID：{observation.evidence_id}</p>
            </>
          )}
          {result.kind === "INNOVATIVE_SHARE_OF_DRUG_SALES" && management && disclosedShare && (
            <>
              <h3>管理层披露的创新药销售收入占比</h3>
              <p className={styles.answerValue}>{disclosedShare[1]}%</p>
              <p>原文明确使用“药品销售收入”作为分母，不是公司合并营业收入占比。</p>
              <blockquote className={styles.answerPassage}>
                {management.text}
              </blockquote>
              <OriginalLink page={management.page} />
              <p className={styles.qaHelp}>
                这是对管理层原文的来源归属与字面定位，不是独立计算得出的财务比率，
                也未核验该管理层口径与合并利润表是否可比。
              </p>
              <p className={styles.hash}>证据ID：{management.evidence_id}</p>
            </>
          )}
          <p className={styles.hash}>报告身份：{result.source.report_identity}</p>
          <p><strong>财务语义：NOT_PERFORMED · 研究发布：BLOCKED · 报告未持久化</strong></p>
        </article>
      )}
    </section>
  );
}
