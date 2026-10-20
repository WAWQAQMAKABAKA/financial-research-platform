import { Suspense } from "react";
import Link from "next/link";

async function getApiStatus(): Promise<string> {
  const baseUrl =
    process.env.RESEARCH_API_BASE_URL ??
    "http://127.0.0.1:8000";

  try {
    const response = await fetch(
      `${baseUrl}/api/v1/health`,
      { cache: "no-store" }
    );

    if (!response.ok) {
      return "UNAVAILABLE";
    }

    const data: { status?: string } = await response.json();

    return data.status === "ok"
      ? "CONNECTED"
      : "UNAVAILABLE";
  } catch {
    return "UNAVAILABLE";
  }
}

async function ResearchApiStatus() {
  const apiStatus = await getApiStatus();
  return <p>Research API: {apiStatus}</p>;
}

export default function ResearchPage() {
  return (
    <main style={{
      maxWidth: 800,
      margin: "80px auto",
      padding: 24,
      fontFamily: "Arial, sans-serif",
    }}>
      <h1>Financial Research Platform</h1>
      <p>
        Source-verifiable financial research.
      </p>

      <h2>Platform status</h2>
      <Suspense fallback={<p>Research API: CHECKING...</p>}>
        <ResearchApiStatus />
      </Suspense>

      <h2>Research modules</h2>
      <p>
        Financial Report Analyst — in development
      </p>
      <p><Link href="/research/evidence">View verified source evidence</Link></p>
      <p><Link href="/research/ask">Ask a bounded source question</Link></p>
    </main>
  );
}
