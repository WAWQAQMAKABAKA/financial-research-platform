/** M122: explicitly local, model-free retrieval proxy; no source file paths. */
import { NextRequest, NextResponse } from "next/server";

const unavailable = (status: number) =>
  NextResponse.json(
    { detail: "Local source retrieval unavailable" },
    { status, headers: { "cache-control": "no-store" } },
  );

export async function POST(request: NextRequest) {
  if (
    process.env.NODE_ENV !== "development" ||
    process.env.FRP_LOCAL_RETRIEVAL_UI !== "1"
  ) {
    return unavailable(404);
  }
  if (request.headers.get("origin") !== "http://127.0.0.1:3000") {
    return unavailable(403);
  }

  const token = process.env.FRP_LOCAL_LLM_ACCESS_TOKEN ?? "";
  if (token.length < 32) return unavailable(503);

  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return unavailable(400);
  }
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    return unavailable(400);
  }
  const data = payload as Record<string, unknown>;
  if (
    Object.keys(data).sort().join(",") !== "question,report_key" ||
    data.report_key !== "600276-2026H1" ||
    typeof data.question !== "string" ||
    !data.question.trim() ||
    data.question.length > 240 ||
    new TextEncoder().encode(data.question).length > 800
  ) {
    return unavailable(400);
  }

  try {
    const response = await fetch(
      "http://127.0.0.1:8000/api/v1/research/local-evidence-search",
      {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-frp-local-token": token,
        },
        body: JSON.stringify(data),
        cache: "no-store",
        signal: AbortSignal.timeout(110000),
      },
    );
    if (!response.ok) return unavailable(503);
    const result: unknown = await response.json();
    return NextResponse.json(result, {
      headers: { "cache-control": "no-store" },
    });
  } catch {
    return unavailable(503);
  }
}
