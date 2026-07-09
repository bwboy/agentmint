import assert from "node:assert/strict";
import { test } from "node:test";

import { getRuntimeNodeInstructions, getRuntimeProfileInstructions } from "./connectorInstructions.ts";

test("shows Hermes plugin setup command for Hermes runtime nodes", () => {
  const instructions = getRuntimeNodeInstructions({
    runtimeType: "hermes",
    runtimeNodeId: "rn_123",
    token: "rn_sk_abc",
  });

  assert.equal(instructions.title, "Hermes Runtime Node 配置");
  assert.match(instructions.command, /--runtime-node-id rn_123/);
  assert.match(instructions.command, /--runtime-node-token rn_sk_abc/);
  assert.match(instructions.command, /--platform-url ws:\/\/localhost:8000\/ws/);
  assert.match(instructions.command, /hermes gateway/);
});

test("shows Hermes profile creation command for a bound agent", () => {
  const instructions = getRuntimeProfileInstructions({
    runtimeType: "hermes",
    profileName: "wow expert's profile",
  });

  assert.equal(instructions.title, "Hermes Profile 初始化");
  assert.match(instructions.command, /hermes profile create 'wow expert'\\''s profile'/);
  assert.doesNotMatch(instructions.command, /--clone/);
  assert.match(instructions.command, /hermes config set gateway\.multiplex_profiles true/);
  assert.match(instructions.command, /hermes gateway/);
});

test("shows OpenClaw workspace creation command for a bound agent", () => {
  const instructions = getRuntimeProfileInstructions({
    runtimeType: "openclaw",
    workspaceName: "bot-space",
  });

  assert.equal(instructions.title, "OpenClaw Workspace 初始化");
  assert.match(instructions.command, /AGENTMINT_WORKSPACE='bot-space'/);
});

test("keeps simulator instructions for OpenClaw runtime nodes", () => {
  const instructions = getRuntimeNodeInstructions({
    runtimeType: "openclaw",
    runtimeNodeId: "rn_123",
    token: "rn_sk_abc",
  });

  assert.equal(instructions.title, "OpenClaw Runtime 模拟器");
  assert.match(instructions.command, /AGENTMINT_RUNTIME_NODE_ID=rn_123/);
  assert.match(instructions.command, /AGENTMINT_RUNTIME_NODE_TOKEN=rn_sk_abc/);
  assert.match(instructions.command, /python scripts\/connector-sim.py/);
});
