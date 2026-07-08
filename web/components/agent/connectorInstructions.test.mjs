import assert from "node:assert/strict";
import { test } from "node:test";

import { getRuntimeNodeInstructions } from "./connectorInstructions.ts";

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
