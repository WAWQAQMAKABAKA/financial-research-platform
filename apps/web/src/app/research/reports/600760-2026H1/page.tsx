import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { devAccessIssue } from "../../lib/dev-access";
import styles from "./facts-report.module.css";

const REPORT_KEY = "600760-2026H1";
const DEFAULT_QUESTION =
  "600760 中航沈飞 2026 年半年度合并利润表中营业收入是多少？";
const AMOUNT = /^-?(?:0|[1-9]\d{0,2}(?:,\d{3})+|[1-9]\d*)\.\d{2}$/;
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

type WithheldItem = {
  claim_id?: string;
  kind: string;
  status: string;
  reason: string;
};

type RetrievalHit = {
  page_number: number | null;
  evidence_id: string;
  excerpt: string;
};

type Retrieval = {
  status: string;
  retriever_version?: string;
  hits: RetrievalHit[];
};

type Selection = {
  status: string;
  reason: string | null;
  statement_kind: string | null;
  column_header: string | null;
  rows: string[];
  trace?: {
    selection_basis?: string;
    statement_title?: string;
    row_labels_considered?: number;
  } | null;
};

type Report = {
  status: "REPORT_READY";
  reason: null;
  report_type: string;
  report_key: string;
  report_id: string;
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
  request: { question: string; question_code: string | null };
  retrieval?: Retrieval;
  selection?: Selection;
  facts: Fact[];
  reviews: Review[];
  publication: {
    may_publish: boolean;
    research_publication: string;
    publication_label: string;
    financial_semantic_review: string;
    published_claim_ids: string[];
    withheld: WithheldItem[];
    withheld_capabilities: WithheldItem[];
  };
  limitations: string[];
};

type WithheldReport = {
  status: "REPORT_WITHHELD";
  reason: string;
  request?: { question: string; question_code: string | null } | null;
  retrieval?: Retrieval;
  selection?: Selection;
  publication?: {
    financial_semantic_review?: string;
    research_publication?: string;
    publication_label?: string;
  };
};

type Clarification = {
  status: "CLARIFICATION_REQUIRED";
  kind?: string;
  reason: string;
  question: string;
  clarification_id: string;
  option_basis: string;
  options: {
    option_id: string;
    row_label: string;
    core: string;
    statement_kind: string;
    statement_title: string;
  }[];
  interpretation: { status: string; rationale: string | null } | null;
  financial_semantic_review: string;
  research_publication: string;
};

const REASONS: Record<string, string> = {
  NO_ROW_MATCH: "问题没有匹配到该报表中的任何行项目。",
  NO_STATEMENT_SCOPE: "问题未指明报表范围，或检索未找到利润表。",
  AMBIGUOUS_STATEMENT_SCOPE:
    "问题同时指向多个报表，请注明「合并利润表」或「母公司利润表」。",
  OUT_OF_PERIOD_SCOPE: "本报告只支持 2026 年半年度，跨期问题不发布。",
  SOURCE_CELL_BLANK_NOT_ZERO: "该行在原文中是空白单元格。空白不等于 0，因此不发布。",
  SOURCE_CELL_DASH_NOT_ZERO: "该单元格在原文中是横线。横线不等于 0，因此不发布。",
  TOO_MANY_ROW_MATCHES: "问题匹配到过多行项目，无法唯一定位。",
  COLUMN_HEADER_UNAVAILABLE: "该报表中找不到对应报告期的列。",
  LITERAL_REVIEW_NOT_PASSED: "原文文字与单元格位置的复核未通过。",
  SOURCE_CELL_UNRESOLVED: "无法在原文中唯一定位该单元格。",
  SOURCE_CELL_AMBIGUOUS: "该单元格在同一报表中出现多次，无法唯一确定。",
  QUESTION_INVALID: "问题格式无效。",
  RETRIEVAL_NOT_READY: "检索未返回可用的原文候选。",
  PUBLICATION_WITHHELD: "发布策略拒绝了该报告。",
  COMPARISON_NOT_PUBLISHABLE: "比较类问题不在本报告的发布范围内，本报告只发布披露事实。",
  FORWARD_VIEW_NOT_PUBLISHABLE: "前瞻或预测类问题不在本报告的发布范围内。",
  QUESTION_INTENT_AMBIGUOUS: "无法确定这是一个披露事实查询，因此不发布。",
};

function reasonText(reason: string): string {
  return REASONS[reason] ?? `发布策略拒绝：${reason}`;
}

function compact(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function shortHash(value: string): string {
  return HASH.test(value) ? `${value.slice(0, 16)}…${value.slice(-8)}` : value;
}

function isFact(value: unknown): value is Fact {
  if (typeof value !== "object" || value === null) return false;
  const fact = value as Fact;
  return (
    fact.kind === "OBSERVED_FACT" &&
    AMOUNT.test(fact.value_verbatim) &&
    Number.isInteger(fact.page_number) && fact.page_number > 0 &&
    fact.citation?.page_number === fact.page_number &&
    typeof fact.citation.document_id === "string" &&
    HASH.test(fact.citation.canonical_sha256 ?? "")
  );
}

function isReport(value: unknown): value is Report {
  if (typeof value !== "object" || value === null) return false;
  const report = value as Report;
  if (report.status !== "REPORT_READY") return false;
  if (report.report_key !== REPORT_KEY) return false;
  if (typeof report.report_id !== "string" || !HASH.test(report.report_id)) return false;
  if (typeof report.issuer?.name !== "string" || report.issuer.ticker !== "600760") return false;
  if (report.issuer.report_period !== "2026H1") return false;
  if (!HASH.test(report.source?.source_sha256 ?? "")) return false;
  if (!HASH.test(report.source.canonical_sha256 ?? "")) return false;
  if (report.publication?.may_publish !== true) return false;
  if (report.publication.research_publication !== "FACTS_ONLY") return false;
  if (report.publication.financial_semantic_review !== "NOT_PERFORMED") return false;
  if (!Array.isArray(report.facts) || report.facts.length === 0) return false;
  if (!Array.isArray(report.reviews)) return false;
  if (report.reviews.length !== report.facts.length) return false;

  return report.facts.every((fact, index) => {
    const review = report.reviews[index];
    return (
      isFact(fact) &&
      fact.citation.document_id === report.source.document_id &&
      fact.citation.canonical_sha256 === report.source.canonical_sha256 &&
      review.claim_id === fact.claim_id &&
      review.verdict === "ADMIT" &&
      report.publication.published_claim_ids.includes(fact.claim_id)
    );
  });
}

function isWithheld(value: unknown): value is WithheldReport {
  if (typeof value !== "object" || value === null) return false;
  const report = value as WithheldReport;
  return report.status === "REPORT_WITHHELD" && typeof report.reason === "string";
}

function isClarification(value: unknown): value is Clarification {
  if (typeof value !== "object" || value === null) return false;
  const c = value as Clarification;
  return (
    c.status === "CLARIFICATION_REQUIRED" &&
    typeof c.clarification_id === "string" &&
    Array.isArray(c.options) && c.options.length >= 2
  );
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
        <p className={styles.muted}>研究发布：已阻止 · 财务语义核验：未进行</p>
      </div>
    </section>
  );
}

function Loading() {
  return (
    <section className={styles.loading} role="status">
      <strong>正在核验原始披露…</strong>
      <p>
        正在重新计算 PDF 来源哈希与正典文本哈希，检索原文候选，
        并从利润表行项目中定位单元格。约需 12–40 秒，不缓存结果。
      </p>
    </section>
  );
}

function Trace({ retrieval, selection, allowExcerpt = true }: {
  retrieval?: Retrieval;
  selection?: Selection;
  allowExcerpt?: boolean;
}) {
  if (!retrieval && !selection) return null;
  return (
    <section className={styles.trace} aria-label="检索与选择过程">
      <p className={styles.kicker}>检索与选择 / RETRIEVAL TRACE</p>
      {selection?.trace?.selection_basis === "RETRIEVAL_PAGE_PRIORITY" && (
        <p className={styles.notice}>
          问题未注明报表名称，报表范围由检索页序推断，不是语义认定。
        </p>
      )}
      {selection && (
        <p className={styles.traceLine}>
          报表范围：{selection.trace?.statement_title ?? selection.statement_kind ?? "未确定"}
          {" · "}列：{selection.column_header ?? "未确定"}
          {" · "}匹配行：{selection.rows.length > 0 ? selection.rows.map(compact).join("、") : "无"}
        </p>
      )}
      {retrieval && (
        <details className={styles.details} open>
          <summary>原文候选（前 5 个，共 {retrieval.hits.length} 个）</summary>
          <ol className={styles.hits}>
            {retrieval.hits.map((hit) => (
              <li key={hit.evidence_id}>
                <span className={styles.hitPage}>第 {hit.page_number} 页</span>
                <span className={styles.hitText}>
                  {allowExcerpt
                    ? compact(hit.excerpt)
                    : `候选证据 ${hit.evidence_id.slice(0, 8)}…（未发布状态不展示原文）`}
                </span>
              </li>
            ))}
          </ol>
        </details>
      )}
    </section>
  );
}

function FactCard({ fact }: { fact: Fact }) {
  const citationUrl = `${fact.citation.source_url}#page=${fact.citation.page_number}`;
  return (
    <section className={styles.factCard} aria-label="已核对事实">
      <div className={styles.cardTop}>
        <p className={styles.kicker}>已核对事实 / VERIFIED FACT</p>
        <span className={styles.tag}>{fact.kind}</span>
      </div>
      <p className={styles.value}>{fact.value_verbatim}</p>
      <dl className={styles.facts}>
        <div><dt>报表</dt><dd>{fact.statement_title}</dd></div>
        <div><dt>行项目</dt><dd>{compact(fact.row_label)}</dd></div>
        <div><dt>列</dt><dd>{compact(fact.column_header)}</dd></div>
        <div><dt>页码</dt><dd>第 {fact.page_number} 页</dd></div>
      </dl>
      <p className={styles.context}>原文上下文：{fact.statement_context}</p>
      <a className={styles.source} href={citationUrl} target="_blank" rel="noopener noreferrer">
        在原始披露中打开第 {fact.citation.page_number} 页 ↗
      </a>
    </section>
  );
}

function ClarificationBody({ clarification }: { clarification: Clarification }) {
  const isScope = clarification.kind === "STATEMENT_SCOPE";
  return (
    <>
      <section className={styles.boundary} aria-label="需要澄清">
        <strong>{isScope ? "需要澄清 · 请选择报表范围" : "需要澄清 · 请选择指标"}</strong>
        <p>
          {isScope
            ? "问题未注明报表名称，合并与母公司利润表中都存在匹配行项目，选择后继续核验。"
            : "问题中的指标在原文里对应多个行项目，选择后继续核验并生成事实报告。"}
        </p>
        {clarification.interpretation?.rationale ? (
          <p className={styles.muted}>解释（模型提议，未核验）：{clarification.interpretation.rationale}</p>
        ) : null}
        <p className={styles.muted}>选项来源：{clarification.option_basis} · 不展示任何金额。</p>
      </section>
      <section className={styles.clarifyOptions} aria-label="指标选项">
        {clarification.options.map((option) => {
          const href =
            `/research/reports/${REPORT_KEY}?q=${encodeURIComponent(clarification.question)}` +
            `&clarification_id=${encodeURIComponent(clarification.clarification_id)}` +
            `&option_id=${encodeURIComponent(option.option_id)}`;
          return (
            <a key={option.option_id} className={styles.clarifyOption} href={href}>
              <strong>{isScope ? option.statement_title : option.core}</strong>
              <span>
                {isScope
                  ? "报表范围"
                  : `${option.statement_title} · ${compact(option.row_label)}`}
              </span>
            </a>
          );
        })}
      </section>
      <p className={styles.muted}>研究发布：已阻止 · 财务语义核验：未进行</p>
    </>
  );
}

async function ReportBody({ searchParams }: {
  searchParams: Promise<{ q?: string | string[]; clarification_id?: string | string[]; option_id?: string | string[] }>;
}) {
  const issue = devAccessIssue(process.env);
  if (issue !== null) {
    return <ClosedNotice reason={`本地开发访问未启用（${issue}）。`} />;
  }

  const params = await searchParams;
  const raw = typeof params.q === "string" ? params.q.trim().slice(0, 240) : "";
  const askedQuestion = raw.length > 0 ? raw : null;
  const clarificationId =
    typeof params.clarification_id === "string" ? params.clarification_id : null;
  const optionId = typeof params.option_id === "string" ? params.option_id : null;
  const resolving = clarificationId !== null && optionId !== null && askedQuestion !== null;

  const base = process.env.RESEARCH_API_BASE_URL ?? "http://127.0.0.1:8000";
  const token = process.env.FRP_LOCAL_LLM_ACCESS_TOKEN ?? "";
  const endpoint = resolving
    ? `${base}/api/v1/research/reports/${REPORT_KEY}/ask/resolve`
    : askedQuestion === null
      ? `${base}/api/v1/research/reports/${REPORT_KEY}`
      : `${base}/api/v1/research/reports/${REPORT_KEY}/ask`;

  let report: Report | null = null;
  let withheld: WithheldReport | null = null;
  let clarification: Clarification | null = null;
  try {
    const method = askedQuestion === null ? "GET" : "POST";
    const headers: Record<string, string> = askedQuestion === null
      ? { "x-frp-local-token": token }
      : { "content-type": "application/json", "x-frp-local-token": token };
    const body = askedQuestion === null
      ? undefined
      : JSON.stringify(
          resolving
            ? { question: askedQuestion, clarification_id: clarificationId, option_id: optionId }
            : { question: askedQuestion },
        );
    const response = await fetch(endpoint, {
      method, cache: "no-store", headers, body,
      signal: AbortSignal.timeout(120_000),
    });
    if (response.ok) {
      const payload: unknown = await response.json();
      if (isReport(payload)) report = payload;
      else if (isWithheld(payload)) withheld = payload;
      else if (isClarification(payload)) clarification = payload;
    }
  } catch {
    report = null;
  }

  if (clarification !== null) {
    return <ClarificationBody clarification={clarification} />;
  }

  if (withheld !== null) {
    return (
      <>
        <Trace
          retrieval={withheld.retrieval}
          selection={withheld.selection}
          allowExcerpt={false}
        />
        <section className={styles.closed} role="status">
          <span className={styles.closedMark} aria-hidden="true">!</span>
          <div>
            <h2>该问题未取得可发布的披露事实</h2>
            <p>{reasonText(withheld.reason)}</p>
            <p className={styles.muted}>
              未展示任何金额。研究发布：已阻止 · 财务语义核验：未进行。
            </p>
            <p className={styles.muted}>
              支持的提问范围：600760 2026 年半年度合并利润表 / 母公司利润表的金额行，
              且问题中请注明报表名称。
            </p>
          </div>
        </section>
      </>
    );
  }

  if (report === null) return <Unavailable />;

  return (
    <>
      <Trace retrieval={report.retrieval} selection={report.selection} />

      <section className={styles.boundary} aria-label="解读边界">
        <strong>{report.publication.publication_label}</strong>
        <p>
          金额为披露原文的逐字定位结果。未进行财务语义核验，不构成会计口径认定，
          也不构成投资建议。
        </p>
      </section>

      <div className={styles.grid}>
        <div>
          {report.facts.map((fact) => <FactCard key={fact.claim_id} fact={fact} />)}

          <section className={styles.reviewCard} aria-label="逐条独立核验">
            <p className={styles.kicker}>逐条独立核验 / CLAIM-LEVEL REVIEW</p>
            {report.reviews.map((review) => (
              <div key={review.claim_id} className={styles.reviewRow}>
                <div><dt>主张</dt><dd>{review.claim_id}</dd></div>
                <div><dt>核验结论</dt><dd className={styles.admit}>{review.verdict}</dd></div>
                <div><dt>核验范围</dt><dd>{review.review_scope}</dd></div>
              </div>
            ))}
            <p className={styles.muted}>
              核验者：{report.reviews[0]?.reviewer_id} · 依据：{report.reviews[0]?.rationale}
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

export default function FactsReportPage({ searchParams }: {
  searchParams: Promise<{ q?: string | string[] }>;
}) {
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
            <span>2026 年半年度 · 利润表</span>
          </h1>
          <p>
            提出一个披露事实问题，系统检索原始 PDF 候选、定位利润表行项目，
            并由独立字面核验与发布策略决定能否展示。只发布已核对的事实。
          </p>
          <div className={styles.heroTags}>
            <span>来源哈希已复核</span>
            <span>PIT 已校验</span>
            <span>仅事实发布</span>
          </div>
        </section>

        <form className={styles.ask} method="get" action={`/research/reports/${REPORT_KEY}`}>
          <label htmlFor="q">研究问题</label>
          <div className={styles.askRow}>
            <input
              id="q" name="q" type="text" maxLength={240}
              placeholder={DEFAULT_QUESTION}
              aria-describedby="q-hint"
            />
            <button type="submit">检索并核验</button>
          </div>
          <p id="q-hint" className={styles.askHint}>
            支持范围：600760 2026 年半年度合并利润表 / 母公司利润表的金额行；
            问题中请注明报表名称。跨期、比较与推断不发布。
          </p>
        </form>

        <Suspense fallback={<Loading />}>
          <ReportBody searchParams={searchParams} />
        </Suspense>

        <footer className={styles.footer}>
          <span>已授权语料：data/manifests/corpus.v1.json</span>
          <span>仅展示已核对的披露事实 · 不含财务趋势判断</span>
        </footer>
      </div>
    </main>
  );
}
