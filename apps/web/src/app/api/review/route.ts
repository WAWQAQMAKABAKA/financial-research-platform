import { NextResponse } from "next/server";

const CHECK_KEYS = [
  "metric_identity",
  "period",
  "entity",
  "basis",
  "evidence_support",
  "no_overreach",
] as const;

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const form = await request.formData();
  const packetId = String(form.get("packet_id") ?? "");
  const question = String(form.get("question") ?? "");
  const reviewerId = String(form.get("reviewer_id") ?? "local-reviewer");
  const verdict = String(form.get("verdict") ?? "");
  const rationale = String(form.get("rationale") ?? "").trim();

  const checklist: Record<string, boolean> = {};
  const checklistNotes: Record<string, string> = {};
  for (const key of CHECK_KEYS) {
    checklist[key] = form.get(`check_${key}`) === "on";
    const note = String(form.get(`note_${key}`) ?? "").trim();
    if (note.length > 0) checklistNotes[key] = note;
  }

  const base = process.env.RESEARCH_API_BASE_URL ?? "http://127.0.0.1:8000";
  const token = process.env.FRP_LOCAL_LLM_ACCESS_TOKEN ?? "";

  let status = 0;
  try {
    const response = await fetch(`${base}/api/v1/research/reviews/decide`, {
      method: "POST",
      cache: "no-store",
      headers: {
        "content-type": "application/json",
        "x-frp-local-token": token,
      },
      body: JSON.stringify({
        packet_id: packetId,
        reviewer_id: reviewerId,
        verdict,
        checklist,
        checklist_notes: checklistNotes,
        rationale,
      }),
      signal: AbortSignal.timeout(120_000),
    });
    status = response.status;
  } catch {
    status = 0;
  }

  if (status !== 200) {
    return new NextResponse(
      `审阅提交失败（HTTP ${status}）。请返回并检查：六项是否全部勾选、是否填写理由、审阅包是否仍在有效期。\n`,
      { status: status === 0 ? 502 : 400, headers: { "content-type": "text/plain; charset=utf-8" } },
    );
  }

  const target = new URL("/research/reports/600760-2026H1", request.url);
  if (question) target.searchParams.set("q", question);
  target.searchParams.set("reviewed", String(status));
  return NextResponse.redirect(target, 303);
}
