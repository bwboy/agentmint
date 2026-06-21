import assert from "node:assert/strict";
import { test } from "node:test";

import { getConnectorInstructions } from "./connectorInstructions.ts";

test("shows Hermes plugin environment variables for Hermes agents", () => {
  const instructions = getConnectorInstructions({
    agentType: "hermes",
    connectorId: "conn_123",
    token: "conn_sk_abc",
  });

  assert.equal(instructions.title, "Hermes Plugin 配置");
  assert.match(instructions.command, /AGENTMINT_CONNECTOR_ID=conn_123/);
  assert.match(instructions.command, /AGENTMINT_CONNECTOR_TOKEN=conn_sk_abc/);
  assert.match(instructions.command, /AGENTMINT_PLATFORM_URL=ws:\/\/localhost:8000\/ws/);
  assert.match(instructions.command, /hermes gateway/);
});

test("keeps simulator instructions for OpenClaw agents", () => {
  const instructions = getConnectorInstructions({
    agentType: "openclaw",
    connectorId: "conn_123",
    token: "conn_sk_abc",
  });

  assert.equal(instructions.title, "Connector 模拟器");
  assert.match(instructions.command, /CONNECTOR_ID=conn_123/);
  assert.match(instructions.command, /CONNECTOR_TOKEN=conn_sk_abc/);
  assert.match(instructions.command, /python scripts\/connector-sim.py/);
});
