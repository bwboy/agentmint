import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

test("answer markdown enables GFM tables and wraps tables for overflow", () => {
  const source = readFileSync(new URL("./AnswerMarkdown.tsx", import.meta.url), "utf8");

  assert.match(source, /from "remark-gfm"/);
  assert.match(source, /remarkPlugins=\{\[remarkGfm\]\}/);
  assert.match(source, /overflow-x-auto/);
  assert.match(source, /className="answer-table"/);
  assert.match(source, /className="answer-th"/);
  assert.match(source, /className="answer-td"/);
});
