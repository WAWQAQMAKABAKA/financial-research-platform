import { NextRequest, NextResponse } from "next/server";

const KEYS = new Set(["600276-2026H1", "600760-2026H1"]);
const QUESTION = "consolidated_revenue_2026H1";

export async function POST(request: NextRequest) {
  // This is NOT a production customer API. Fail closed outside dev mode.
  if (process.env.NODE_ENV !== "development" ||
      process.env.FRP_LOCAL_LLM_UI !== "1") {
    return NextResponse.json({ detail: "Disabled" }, { status: 404 });
  }
  // Reject cross-site browser submissions even when loopback is reachable.
  if (request.headers.get("origin") !== "http://127.0.0.1:3000") {
    return NextResponse.json({ detail: "Forbidden" }, { status: 403 });
  }
  const secret = process.env.FRP_LOCAL_LLM_ACCESS_TOKEN;
  if (!secret || secret.length < 32) {
    return NextResponse.json({ detail: "Unavailable" }, { status: 503 });
  }
  let input: unknown;
  try {
    input = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request" }, { status: 400 });
  }
  if (typeof input !== "object" || input === null || Array.isArray(input)) {
    return NextResponse.json({ detail: "Invalid request" }, { status: 400 });
  }
  const data = input as Record<string, unknown>;
  if (Object.keys(data).sort().join(",") !== "question_code,report_key" ||
      typeof data.report_key !== "string" || !KEYS.has(data.report_key) ||
      data.question_code !== QUESTION) {
    return NextResponse.json({ detail: "Unsupported question" }, { status: 400 });
  }
  try {
    const response = await fetch("http://127.0.0.1:8000/api/v1/research/local-source-answer", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-frp-local-token": secret,
      },
      cache: "no-store",
      body: JSON.stringify(data),
      signal: AbortSignal.timeout(85000),
    });
    // Never proxy raw exception text or arbitrary backend errors to browsers.
    if (!response.ok) {
      return NextResponse.json({ detail: "Local model request unavailable" },
        { status: response.status === 429 ? 429 : 503 });
    }
    const body = await response.json();
    return NextResponse.json(body, { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json({ detail: "Local model request unavailable" }, { status: 503 });
  }
}
