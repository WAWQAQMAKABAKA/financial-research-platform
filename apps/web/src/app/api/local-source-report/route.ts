import { NextRequest, NextResponse } from "next/server";

const unavailable = (status: number) =>
  NextResponse.json(
    { detail: "Local report preview unavailable" },
    { status, headers: { "cache-control": "no-store" } },
  );

export async function POST(request: NextRequest) {
  if (
    process.env.NODE_ENV !== "development" ||
    process.env.FRP_LOCAL_REPORT_PREVIEW_UI !== "1"
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

  if (
    typeof payload !== "object" ||
    payload === null ||
    Array.isArray(payload)
  ) {
    return unavailable(400);
  }

  const data = payload as Record<string, unknown>;
  const keys = Object.keys(data).sort().join(",");
  const hasRoute = keys === "answer_kind,report_key";

  if (
    (keys !== "report_key" && !hasRoute) ||
    data.report_key !== "600276-2026H1" ||
    (hasRoute &&
      data.answer_kind !== "CONSOLIDATED_REVENUE" &&
      data.answer_kind !== "INNOVATIVE_SHARE_OF_DRUG_SALES")
  ) {
    return unavailable(400);
  }

  try {
    const response = await fetch(
      "http://127.0.0.1:8000/api/v1/research/local-source-report",
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
