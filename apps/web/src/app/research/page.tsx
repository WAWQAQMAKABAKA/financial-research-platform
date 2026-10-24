import { Suspense } from "react";
import Link from "next/link";
import styles from "./research.module.css";

const REPORT_PATH = "/research/reports/600276-2026H1";

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
              <h2>恒瑞医药 · 2026年半年度</h2>
              <p className={styles.metadata}>
                股票代码：600276 · 公告日期：2026年8月20日
              </p>
            </div>
            <span className={styles.localBadge}>
              本地预览 · 尚未发布
            </span>
          </div>

          <div className={styles.question}>
            <span>核心研究问题</span>
            <p>
              恒瑞医药2026年半年度报告中有哪些营业收入相关数据
              和创新药销售披露？这些原始证据能够证明什么，
              哪些财务解释仍需进一步核验？
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
              打开恒瑞医药研究报告 →
            </Link>
            <p>
              进入报告后点击“生成研究预览”，
              系统将重新核验本地原始PDF及其证据关联。
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
              查看两项保留原始报表口径的营业收入数据、
              一段注明来源的管理层披露、原始PDF页码链接，
              并对限定范围内的拟议观点进行核验。
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
            研究报告未持久化保存，研究发布始终处于阻止状态。
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
