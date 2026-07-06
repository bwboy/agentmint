import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const source = readFileSync(new URL("./QuestionForm.tsx", import.meta.url), "utf8");

test("question controls avoid browser number spinners", () => {
  assert.doesNotMatch(source, /type="number"/);
  assert.match(source, /inputMode="numeric"/);
  assert.match(source, /NumericField/);
});

test("question controls provide preset choices for different value scales", () => {
  assert.match(source, /DEADLINE_PRESETS/);
  assert.match(source, /REWARD_PRESETS/);
  assert.match(source, /RESPONDER_PRESETS/);
  assert.match(source, /SegmentedNumber/);
});

test("responder control keeps a custom numeric entry", () => {
  assert.match(source, /customLabel="自定义"/);
  assert.match(source, /aria-label=\{customLabel/);
});

test("question form supports image and file attachments", () => {
  assert.match(source, /AttachmentPicker/);
  assert.match(source, /\/api\/files\/upload/);
  assert.match(source, /attachments/);
});
