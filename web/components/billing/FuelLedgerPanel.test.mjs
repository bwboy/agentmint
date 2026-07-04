import assert from "node:assert/strict";
import { test } from "node:test";

import { ledgerCategory, ledgerEventMeta } from "./FuelLedgerPanel.logic.ts";

test("categorizes fuel ledger events by settlement phase", () => {
  assert.equal(ledgerCategory("base_reserved"), "reserve");
  assert.equal(ledgerCategory("answer_base_earned"), "settlement");
  assert.equal(ledgerCategory("base_refunded"), "refund");
  assert.equal(ledgerCategory("reward_auto_awarded"), "reward");
  assert.equal(ledgerCategory("usage_correction"), "correction");
  assert.equal(ledgerCategory("unknown_event"), "other");
});

test("explains reward auto-award ledger rows", () => {
  assert.deepEqual(ledgerEventMeta("reward_auto_awarded"), {
    label: "系统分配奖励收入",
    category: "reward",
    explanation: "提问者超时未选择时，系统按互动信号自动分配奖励。",
  });
});

test("explains extra base fuel charges", () => {
  assert.deepEqual(ledgerEventMeta("base_extra_charged"), {
    label: "基础回答补扣",
    category: "settlement",
    explanation: "实际 Token 消耗超过预授权上限时，从提问者余额补扣差额。",
  });
});
