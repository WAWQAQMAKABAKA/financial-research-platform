import assert from "node:assert/strict";
import { test } from "node:test";

import { devAccessIssue } from "./dev-access.ts";

const TOKEN = "m1-local-dev-token-0123456789abcdef";

function env(overrides: Record<string, string | undefined> = {}) {
  return {
    NODE_ENV: "development",
    FRP_ENV: undefined,
    FRP_LOCAL_FACTS_REPORT: "1",
    FRP_LOCAL_LLM_ACCESS_TOKEN: TOKEN,
    ...overrides,
  } as Record<string, string | undefined>;
}

test("local development with flag and secret is allowed", () => {
  assert.equal(devAccessIssue(env()), null);
});

test("production build is always refused", () => {
  assert.equal(devAccessIssue(env({ NODE_ENV: "production" })), "PRODUCTION_BUILD");
});

test("production FRP_ENV is refused even in a dev build", () => {
  assert.equal(devAccessIssue(env({ FRP_ENV: "PRODUCTION" })), "PRODUCTION_ENV");
});

test("missing feature flag is refused", () => {
  assert.equal(
    devAccessIssue(env({ FRP_LOCAL_FACTS_REPORT: "0" })),
    "FACTS_REPORT_DISABLED",
  );
});

test("missing or short secret is refused", () => {
  assert.equal(
    devAccessIssue(env({ FRP_LOCAL_LLM_ACCESS_TOKEN: undefined })),
    "LOCAL_TOKEN_MISSING",
  );
  assert.equal(
    devAccessIssue(env({ FRP_LOCAL_LLM_ACCESS_TOKEN: "short" })),
    "LOCAL_TOKEN_MISSING",
  );
});
