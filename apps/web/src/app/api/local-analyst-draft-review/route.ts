import { NextRequest, NextResponse } from "next/server";

const unavailable = (status: number) =>
  NextResponse.json(
    { detail: "Local Analyst review unavailable" },
    {
      status,
      headers: { "cache-control": "no-store" },
    },
  );

export async function POST(request: NextRequest) {
  if (
    process.env.NODE_ENV !== "development" ||
    process.env.FRP_LOCAL_ANALYST_REVIEW_UI !== "1"
  ) {
    return unavailable(404);
  }

  if (request.headers.get("origin") !== "http://127.0.0.1:3000") {
    return unavailable(403);
  }

  const token = process.env.FRP_LOCAL_LLM_ACCESS_TOKEN ?? "";

  if (token.length < 32) {
    return unavailable(503);
  }

  let payload: unknown;

  try {
    payload = await request.json();
  } catch {
    return unavailable(400);
  }

  if (
    !payload ||
    typeof payload !== "object" ||
    Array.isArray(payload)
  ) {
    return unavailable(400);
  }

  const data = payload as Record<string, unknown>;

  if (
    Object.keys(data).sort().join(",") !==
      "candidate_text,report_key" ||
    data.report_key !== "600276-2026H1" ||
    typeof data.candidate_text !== "string" ||
    !data.candidate_text.trim() ||
    data.candidate_text.length > 400 ||
    new TextEncoder().encode(data.candidate_text).length > 1200
  ) {
    return unavailable(400);
  }

  try {
    const response = await fetch(
      "http://127.0.0.1:8000/api/v1/research/local-analyst-draft-review",
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

    if (!response.ok) {
      return unavailable(503);
    }

    const result: unknown = await response.json();

    return NextResponse.json(result, {
      headers: { "cache-control": "no-store" },
    });
  } catch {
    return unavailable(503);
  }
}
