import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { devAccessIssue } from "../../lib/dev-access";
import styles from "./facts-report.module.css";

const REPORT_KEY = "600760-2026H1";
const AMOUNT = /^(?:0|[1-9]\d{0,2}(?:,\d{3})+|[1-9]\d*)\.\d{2}$/;
const HASH = /^[0-9a-f]{64}$/;

export const metadata: Metadata = {
  title: "披露事实报告 · 600760 中航沈飞 2026 年半年度",
  description: "仅展示已核对的披露事实，不含财务趋势判断。",
};

type Fact = {
  claim_id: string;
  kind: string;
  statement_title: string;
  statement_type: string;
  row_label: string;
  column_header: string;
  value_verbatim: string;
  statement_context: string;
  page_number: number;
  evidence_id: string;
  citation: {
    document_id: string;
    page_number: number;
    source_url: string;
    source_sha256: string;
    canonical_sha256: string;
    cell_bbox_pt: number[] | null;
  };
};

type Review = {
  claim_id: string;
  verdict: string;
  reviewer_id: string;
  rationale: string;
  review_scope: string;
};

type Withheld = {
  claim_id?: string;
  kind: string;
  status: string;
  reason: string;
};

type Report = {
  status: string;
  reason: string | null;
  report_key: string;
  report_id: string;
  report_type: string;
  report_storage: string;
  issuer: { name: string; ticker: string; report_period: string };
  source: {
    document_id: string;
    source_url: string;
    published_on: string;
    pit_available_at: string;
    source_sha256: string;
    canonical_sha256: string;
    page_count: number;
    authorization_note: string;
  };
  request: { question_code: string; question: string };
  facts: Fact[];
  reviews: Review[];
  publication: {
    may_publish: boolean;
    research_publication: string;
    publication_label: string;
    financial_semantic_review: string;
    published_claim_ids: string[];
    withheld: Withheld[];
    withheld_capabilities: Withheld[];
  };
  limitations: string[];
};

function shortHash(value: string): string {
  return /^[0-9a-f]{64}$/.test(value)
    ? `${value.slice(0, 16)}…${value.slice(-8)}`
    : value;
}

function isReport(value: unknown): value is Report {
  if (typeof value !== "object" || value === null) return false;
  const report = value as Report;
  if (report.status !== "REPORT_READY") return false;
  if (report.report_key !== REPORT_KEY) return false;
  if (typeof report.report_id !== "string" || !HASH.test(report.report_id)) return false;
  if (typeof report.issuer?.name !== "string" || report.issuer.ticker !== "600760") return false;
  if (report.issuer.report_period !== "2026H1") return false;
  if (typeof report.source?.document_id !== "string") return false;
  if (!HASH.test(report.source.source_sha256 ?? "")) return false;
  if (!HASH.test(report.source.canonical_sha256 ?? "")) return false;
  if (report.publication?.may_publish !== true) return false;
  if (report.publication.research_publication !== "FACTS_ONLY") return false;
  if (report.publication.financial_semantic_review !== "NOT_PERFORMED") return false;
  if (!Array.isArray(report.facts) || report.facts.length === 0) return false;
  if (!Array.isArray(report.reviews) || report.reviews.length !== report.facts.length) return false;

  return report.facts.every((fact, index) => {
    const review = report.reviews[index];
    return (
      fact.kind === "OBSERVED_FACT" &&
      AMOUNT.test(fact.value_verbatim) &&
      Number.isInteger(fact.page_number) && fact.page_number > 0 &&
      fact.citation?.page_number === fact.page_number &&
      fact.citation.document_id === report.source.document_id &&
      fact.citation.canonical_sha256 === report.source.canonical_sha256 &&
      review.claim_id === fact.claim_id &&
      review.verdict === "ADMIT" &&
      report.publication.published_claim_ids.includes(fact.claim_id)
    );
  });
}

function ClosedNotice({ reason }: { reason: string }) {
  return (
    <section className={styles.closed} role="status">
      <span className={styles.closedMark} aria-hidden="true">!</span>
      <div>
        <h2>本报告未开放</h2>
        <p>{reason}</p>
        <p className={styles.muted}>
          本页面仅在本地开发环境、经本地密钥授权时可用；生产构建始终拒绝。
        </p>
      </div>
    </section>
  );
}

function Unavailable() {
  return (
    <section className={styles.closed} role="status">
      <span className={styles.closedMark} aria-hidden="true">!</span>
      <div>
        <h2>未取得可核验的披露事实</h2>
        <p>
          原始披露缺失、来源哈希或正典哈希不符、报告期或单位不一致、
          或独立核验未通过，因此不展示任何金额与结论。
        </p>
        <p className={styles.muted}>
          研究发布：已阻止 · 财务语义核验：未进行
        </p>
      </div>
    </section>
  );
}

function Loading() {
  return (
    <section className={styles.loading} role="status">
      <strong>正在核验原始披露…</strong>
      <p>
        正在重新计算 PDF 来源哈希与正典文本哈希，并定位合并利润表单元格。
        首次核验约需 20–40 秒，不缓存结果。
      </p>
    </section>
  );
}

async function ReportBody() {
  const issue = devAccessIssue(process.env);
  if (issue !== null) {
    return <ClosedNotice reason={`本地开发访问未启用（${issue}）。`} />;
  }

  const base = process.env.RESEARCH_API_BASE_URL ?? "http://127.0.0.1:8000";
  const token = process.env.FRP_LOCAL_LLM_ACCESS_TOKEN ?? "";

  let report: Report | null = null;
  try {
    const response = await fetch(`${base}/api/v1/research/reports/${REPORT_KEY}`, {
      cache: "no-store",
      headers: { "x-frp-local-token": token },
      signal: AbortSignal.timeout(120_000),
    });
    if (response.ok) {
      const payload: unknown = await response.json();
      if (isReport(payload)) report = payload;
    }
  } catch {
    report = null;
  }

  if (report === null) return <Unavailable />;

  const fact = report.facts[0];
  const review = report.reviews[0];
  const citationUrl = `${fact.citation.source_url}#page=${fact.citation.page_number}`;

  return (
    <>
      <section className={styles.request} aria-label="研究请求">
        <div>
          <p className={styles.kicker}>研究请求 / RESEARCH REQUEST</p>
          <h2>{report.request.question}</h2>
        </div>
        <span className={styles.code}>{report.request.question_code}</span>
      </section>

      <section className={styles.boundary} aria-label="解读边界">
        <strong>{report.publication.publication_label}</strong>
        <p>
          金额为披露原文的逐字定位结果。未进行财务语义核验，不构成会计口径认定，
          也不构成投资建议。
        </p>
      </section>

      <div className={styles.grid}>
        <div>
          <section className={styles.factCard} aria-label="已核对事实">
            <div className={styles.cardTop}>
              <p className={styles.kicker}>已核对事实 / VERIFIED FACT</p>
              <span className={styles.tag}>{fact.kind}</span>
            </div>
            <p className={styles.value}>{fact.value_verbatim}</p>
            <dl className={styles.facts}>
              <div><dt>报表</dt><dd>{fact.statement_title}</dd></div>
              <div><dt>行项目</dt><dd>{fact.row_label}</dd></div>
              <div><dt>列</dt><dd>{fact.column_header}</dd></div>
              <div><dt>页码</dt><dd>第 {fact.page_number} 页</dd></div>
            </dl>
            <p className={styles.context}>原文上下文：{fact.statement_context}</p>
            <a className={styles.source} href={citationUrl} target="_blank" rel="noopener noreferrer">
              在原始披露中打开第 {fact.citation.page_number} 页 ↗
            </a>
          </section>

          <section className={styles.reviewCard} aria-label="逐条独立核验">
            <p className={styles.kicker}>逐条独立核验 / CLAIM-LEVEL REVIEW</p>
            <div className={styles.reviewRow}>
              <div><dt>主张</dt><dd>{review.claim_id}</dd></div>
              <div><dt>核验结论</dt><dd className={styles.admit}>{review.verdict}</dd></div>
              <div><dt>核验范围</dt><dd>{review.review_scope}</dd></div>
            </div>
            <p className={styles.muted}>
              核验者：{review.reviewer_id} · 依据：{review.rationale}
            </p>
            <p className={styles.muted}>
              该核验仅确认原文文字与单元格位置一致，不确认会计口径、可比性或趋势含义。
            </p>
          </section>

          <section className={styles.withheldCard} aria-label="未发布内容">
            <p className={styles.kicker}>未发布内容 / WITHHELD</p>
            <ul className={styles.withheldList}>
              {report.publication.withheld.map((item) => (
                <li key={item.claim_id ?? item.kind}>
                  <strong>{item.claim_id ?? item.kind}</strong>
                  <span>{item.reason}</span>
                </li>
              ))}
              {report.publication.withheld_capabilities.map((item) => (
                <li key={item.kind}>
                  <strong>{item.kind}</strong>
                  <span>{item.reason}</span>
                </li>
              ))}
            </ul>
          </section>
        </div>

        <aside className={styles.side}>
          <section className={styles.sideCard} aria-label="发布范围">
            <h2>发布范围</h2>
            <dl className={styles.facts}>
              <div><dt>研究发布</dt><dd className={styles.admit}>{report.publication.research_publication}</dd></div>
              <div><dt>财务语义核验</dt><dd>{report.publication.financial_semantic_review}</dd></div>
              <div><dt>已发布主张</dt><dd>{report.publication.published_claim_ids.join("、")}</dd></div>
              <div><dt>报告持久化</dt><dd>{report.report_storage}</dd></div>
            </dl>
          </section>

          <section className={styles.sideCard} aria-label="来源与哈希">
            <h2>来源与哈希</h2>
            <dl className={styles.facts}>
              <div><dt>发行人</dt><dd>{report.issuer.name} · {report.issuer.ticker}</dd></div>
              <div><dt>报告期</dt><dd>{report.issuer.report_period}</dd></div>
              <div><dt>披露日期</dt><dd>{report.source.published_on}</dd></div>
              <div><dt>PIT 可用时间</dt><dd>{report.source.pit_available_at}</dd></div>
              <div><dt>文档编号</dt><dd>{report.source.document_id}</dd></div>
              <div><dt>页数</dt><dd>{report.source.page_count}</dd></div>
            </dl>
            <details className={styles.details}>
              <summary>来源哈希</summary>
              <p className={styles.hash}>来源：{shortHash(report.source.source_sha256)}</p>
              <p className={styles.hash}>正典：{shortHash(report.source.canonical_sha256)}</p>
              <p className={styles.hash}>报告：{shortHash(report.report_id)}</p>
            </details>
            <a className={styles.provenanceLink} href={report.source.source_url} target="_blank" rel="noopener noreferrer">
              原始披露 PDF ↗
            </a>
          </section>

          <section className={styles.sideCard} aria-label="报告限制">
            <h2>报告限制</h2>
            <ul className={styles.limits}>
              {report.limitations.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </section>
        </aside>
      </div>
    </>
  );
}

export default function FactsReportPage() {
  return (
    <main className={styles.page}>
      <div className={styles.shell}>
        <header className={styles.top}>
          <Link href="/research" className={styles.brand}>FR / 金融研究平台</Link>
          <span className={styles.preview}>本地开发预览 · 非对外发布</span>
        </header>

        <section className={styles.hero}>
          <p className={styles.heroKicker}>DISCLOSURE FACT REPORT / 披露事实报告</p>
          <h1>
            600760 中航沈飞
            <span>2026 年半年度 · 合并利润表</span>
          </h1>
          <p>
            从已授权的原始披露中定位一条事实，逐条展示独立核验结果与可追溯引用。
            报告仅发布披露事实，不包含趋势判断。
          </p>
          <div className={styles.heroTags}>
            <span>来源哈希已复核</span>
            <span>PIT 已校验</span>
            <span>仅事实发布</span>
          </div>
        </section>

        <Suspense fallback={<Loading />}>
          <ReportBody />
        </Suspense>

        <footer className={styles.footer}>
          <span>已授权语料：data/manifests/corpus.v1.json</span>
          <span>仅展示已核对的披露事实 · 不含财务趋势判断</span>
        </footer>
      </div>
    </main>
  );
}
