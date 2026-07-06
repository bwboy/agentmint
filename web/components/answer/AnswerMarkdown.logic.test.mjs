import assert from "node:assert/strict";
import { test } from "node:test";

import { parseAnswerContent } from "./AnswerMarkdown.logic.ts";

test("separates tool traces from final answer text", () => {
  const parsed = parseAnswerContent('🌐 browser_navigate: "https://example.com" 💻 terminal: "curl -sL https://example.com"\n最终结论：可以玩。');

  assert.equal(parsed.finalText, "最终结论：可以玩。");
  assert.equal(parsed.hasFinalAnswer, true);
  assert.deepEqual(parsed.traces, [
    { kind: "tool", text: '🌐 browser_navigate: "https://example.com"' },
    { kind: "tool", text: '💻 terminal: "curl -sL https://example.com"' },
  ]);
});

test("removes terminal traces that contain nested quotes", () => {
  const parsed = parseAnswerContent('💻 terminal: "curl -sL "https://www.zelda.com/breath-of-the-wild/""\n最终结论：值得玩。');

  assert.equal(parsed.finalText, "最终结论：值得玩。");
  assert.equal(parsed.hasFinalAnswer, true);
  assert.deepEqual(parsed.traces, [
    { kind: "tool", text: '💻 terminal: "curl -sL "https://www.zelda.com/breath-of-the-wild/""' },
  ]);
});

test("detects working-only status updates", () => {
  const parsed = parseAnswerContent("⏳ Working — 3 min — iteration 1/150, receiving stream response");

  assert.equal(parsed.finalText, "");
  assert.equal(parsed.hasFinalAnswer, false);
  assert.equal(parsed.workingOnly, true);
  assert.deepEqual(parsed.traces, [
    { kind: "status", text: "⏳ Working — 3 min — iteration 1/150, receiving stream response" },
  ]);
});

test("separates vision tool traces from final answer text", () => {
  const parsed = parseAnswerContent('👁️ vision_analyze: "这张图片里有三位人物，请识别他们分别是《荒野大镖客：救赎2》..."');

  assert.equal(parsed.finalText, "");
  assert.equal(parsed.hasFinalAnswer, false);
  assert.deepEqual(parsed.traces, [
    { kind: "tool", text: '👁️ vision_analyze: "这张图片里有三位人物，请识别他们分别是《荒野大镖客：救赎2》..."' },
  ]);
});

test("keeps regular markdown intact", () => {
  const parsed = parseAnswerContent("# 标题\n\n| A | B |\n| - | - |\n| 1 | 2 |");

  assert.equal(parsed.finalText, "# 标题\n\n| A | B |\n| - | - |\n| 1 | 2 |");
  assert.equal(parsed.traces.length, 0);
});
