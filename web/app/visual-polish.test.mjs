import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const agentDetail = readFileSync(new URL("./agents/[id]/page.tsx", import.meta.url), "utf8");
const questionDetail = readFileSync(new URL("./questions/[id]/page.tsx", import.meta.url), "utf8");

test("agent detail page uses shared workbench surfaces and tokens", () => {
  assert.match(agentDetail, /surface-card/);
  assert.match(agentDetail, /text-ink/);
  assert.match(agentDetail, /text-text-secondary/);
  assert.match(agentDetail, /border-border-subtle/);
});

test("question detail page uses shared workbench surfaces and tokens", () => {
  assert.match(questionDetail, /surface-card/);
  assert.match(questionDetail, /text-ink/);
  assert.match(questionDetail, /text-text-secondary/);
  assert.match(questionDetail, /border-border-subtle/);
});
