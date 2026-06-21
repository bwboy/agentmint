import type { AgentType } from "@/lib/types";

export function getConnectorInstructions({
  agentType,
  connectorId,
  token,
}: {
  agentType: AgentType;
  connectorId: string;
  token: string;
}) {
  if (agentType === "hermes") {
    return {
      title: "Hermes Plugin 配置",
      command: [
        `export AGENTMINT_CONNECTOR_ID=${connectorId}`,
        `export AGENTMINT_CONNECTOR_TOKEN=${token}`,
        "export AGENTMINT_PLATFORM_URL=ws://localhost:8000/ws",
        "hermes gateway",
      ].join("\n"),
    };
  }

  return {
    title: "Connector 模拟器",
    command: `CONNECTOR_ID=${connectorId} CONNECTOR_TOKEN=${token} python scripts/connector-sim.py`,
  };
}
