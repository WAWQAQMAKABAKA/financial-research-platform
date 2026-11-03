/**
 * Local-development access guard for the facts-only report page.
 *
 * The page is a server component, so this check runs on the server. It is a
 * second, independent gate: the API also refuses without the shared local
 * secret. A production build must never fetch or render the report.
 */
export function devAccessIssue(
  env: Record<string, string | undefined>,
): string | null {
  if (env.NODE_ENV === "production") return "PRODUCTION_BUILD";
  if ((env.FRP_ENV ?? "").trim().toLowerCase() === "production") {
    return "PRODUCTION_ENV";
  }
  if (env.FRP_LOCAL_FACTS_REPORT !== "1") return "FACTS_REPORT_DISABLED";
  const token = env.FRP_LOCAL_LLM_ACCESS_TOKEN ?? "";
  if (token.length < 32) return "LOCAL_TOKEN_MISSING";
  return null;
}
