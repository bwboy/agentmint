import assert from "node:assert/strict";
import { test } from "node:test";

import { getActiveSection, isActive, sideMenus } from "./navigation.ts";

const params = (query = "") => new URLSearchParams(query);

test("agent subscription list stays in the Agent section", () => {
  assert.equal(getActiveSection("/agents/following"), "agents");
  assert.equal(getActiveSection("/agents/mine"), "agents");
  const item = sideMenus.agents.find(entry => entry.label === "已关注 Agent");

  assert.ok(item);
  assert.equal(item.href, "/agents/following");
  assert.equal(isActive(item, "/agents/following", params()), true);
});

test("workbench pages are owned by the workbench section", () => {
  assert.equal(getActiveSection("/my/agents"), "workbench");
  assert.equal(getActiveSection("/my/agent-answers"), "workbench");
  assert.equal(getActiveSection("/my/owner-supplements"), "workbench");
});

test("personal pages are owned by the account section", () => {
  assert.equal(getActiveSection("/my/profile"), "account");
  assert.equal(getActiveSection("/my/social"), "account");
  assert.equal(getActiveSection("/my/fuel"), "account");
});

test("sidebars do not contain cross-section shortcuts", () => {
  assert.deepEqual(sideMenus.plaza.map(item => item.href), ["/?sort=repute", "/?sort=latest", "/?sort=answers"]);
  assert.deepEqual(sideMenus.ask.map(item => item.href), [
    "/questions/new",
    "/questions/new?visibility=public",
    "/questions/new?visibility=private",
  ]);
  assert.equal(sideMenus.agents.some(item => item.href.startsWith("/my/")), false);
  assert.equal(sideMenus.question.length, 0);
});
