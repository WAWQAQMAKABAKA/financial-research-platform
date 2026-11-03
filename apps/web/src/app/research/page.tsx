import { Suspense } from "react";
import Link from "next/link";
import styles from "./research.module.css";

const REPORT_PATH = "/research/reports/600760-2026H1";

async function getApiStatus(): Promise<"CONNECTED" | "UNAVAILABLE"> {
  const base =
    process.env.RESEARCH_API_BASE_URL ??
    "http://127.0.0.1:8000";

  try {
    const response = await fetch(`${base}/api/v1/health`, {
      cache: "no-store",
    });

    if (!response.ok) return "UNAVAILABLE";

    const data: unknown = await response.json();

    if (
      typeof data === "object" &&
      data !== null &&
      "status" in data &&
      data.status === "ok"
    ) {
      return "CONNECTED";
    }
  } catch {
    // Health is informational, not source verification.
  }

  return "UNAVAILABLE";
}

async function ResearchApiStatus() {
  const status = await getApiStatus();

  return (
    <p className={styles.apiStatus}>
      研究服务：
      <strong>
        {status === "CONNECTED" ? "已连接" : "暂不可用"}
      </strong>
      <span>
        {" "}· 此处仅检查服务状态，原始证据在生成报告时重新核验。
      </span>
    </p>
  );
}

export default function ResearchPage() {
  return (
    <main className={styles.page}>
      <div className={styles.shell}>
        <header className={styles.header}>
          <span className={styles.brand}>
            FR / 金融研究平台
          </span>
          <span className={styles.headerStatus}>
            本地研究预览
          </span>
        </header>

        <section className={styles.hero}>
          <p className={styles.eyebrow}>
            原始证据可追溯的金融研究
          </p>
          <h1>从研究问题出发，让每项表述都有据可查。</h1>
          <p>
            阅读上市公司原始披露，核对财务报表数据和管理层说明，
            并检验拟提出的研究观点是否符合所引原文。
          </p>
          <div className={styles.heroBoundary}>
            原始证据定位不等于财务语义核验，
            也不构成投资建议。
          </div>
        </section>

        <section
          className={styles.researchCard}
          aria-label="当前支持的研究任务"
        >
          <div className={styles.cardHeader}>
            <div>
              <p className={styles.eyebrow}>
                当前研究任务 / 仅支持以下披露
              </p>
              <h2>中航沈飞 · 2026年半年度</h2>
              <p className={styles.metadata}>
                股票代码：600760 · 公告日期：2026年8月28日
              </p>
            </div>
            <span className={styles.localBadge}>
              本地开发预览 · 仅披露事实
            </span>
          </div>

          <div className={styles.question}>
            <span>核心研究问题</span>
            <p>
              中航沈飞2026年半年度合并利润表中，
              「其中：营业收入」在「2026年半年度」列披露的金额是多少？
              这条披露事实的来源与原文位置是什么？
            </p>
          </div>

          <div className={styles.flow}>
            <div>
              <strong>01</strong>
              <h3>打开研究报告</h3>
              <p>围绕当前支持的问题查看研究内容。</p>
            </div>
            <div>
              <strong>02</strong>
              <h3>核对原始证据</h3>
              <p>查看财务报表数据、原文及对应PDF页码。</p>
            </div>
            <div>
              <strong>03</strong>
              <h3>核验研究观点</h3>
              <p>将拟提出的观点与指定原始披露进行比对。</p>
            </div>
          </div>

          <div className={styles.actionRow}>
            <Link className={styles.primary} href={REPORT_PATH}>
              查看 600760 披露事实报告 →
            </Link>
            <p>
              可输入研究问题；报告检索原文候选、逐字定位披露事实，
              并展示来源哈希、页码引用与逐条独立核验；仅发布披露事实。
            </p>
          </div>
        </section>

        <section
          className={styles.scope}
          aria-label="当前研究能力与限制"
        >
          <div>
            <h2>目前可以完成什么？</h2>
            <p>
              提出披露事实问题，系统检索原文候选并定位利润表行项目，
              查看已核对事实、原始 PDF 页码引用、来源哈希与正典哈希，
              以及独立核验结论与未发布内容清单。
            </p>
          </div>
          <div>
            <h2>目前尚不支持什么？</h2>
            <p>
              任意选择公司或研究问题、自定义历史研究时点、
              财务指标勾稽、独立财务语义认定、
              自动生成投资结论或保存研究记录。
              当前研究时点在生成报告时确定。
            </p>
          </div>
        </section>

        <section
          className={styles.boundary}
          aria-label="研究发布限制"
        >
          <strong>研究核验与发布边界</strong>
          <p>
            原始报告尚未完成独立财务语义核验。
            限定范围内的观点核验可以发现与原文不符的表述，
            或返回“尚无法确认”，但不会批准发布。
            披露事实报告不持久化保存，仅发布已核对的披露事实；
            比较、推断与前瞻性判断仍被阻止，不对外发布。
          </p>
          <Suspense
            fallback={
              <p className={styles.apiStatus}>
                研究服务：正在检查…
              </p>
            }
          >
            <ResearchApiStatus />
          </Suspense>
        </section>

        <details className={styles.developer}>
          <summary>查看开发与验证工具</summary>
          <p>
            以下页面用于开发或受限实验，
            不属于已经具备完整财务研究能力的客户流程。
          </p>
          <ul>
            <li>
              <Link href="/research/evidence">
                原始证据查看
              </Link>
            </li>
            <li>
              <Link href="/research/ask">
                限定问题问答原型
              </Link>
            </li>
            <li>
              <Link href="/research/revenue-scope">
                营业收入来源定位原型
              </Link>
            </li>
            <li>
              <Link href="/research/source-workspace">
                双报告证据工作区
              </Link>
            </li>
            <li>
              <Link href="/research/source-workspace/review">
                本地观点核验实验
              </Link>
            </li>
            <li>
              <Link href="/research/source-workspace/ask">
                本地付费模型实验（需明确授权）
              </Link>
            </li>
          </ul>
        </details>

        <footer className={styles.footer}>
          金融研究平台 · 本地研究预览 · 未对外发布
        </footer>
      </div>
    </main>
  );
}
