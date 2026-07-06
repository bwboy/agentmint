import type { AgentType } from "@/lib/types";

export function getConnectorInstructions({
  agentType,
  connectorId,
  token,
  permissionProfile = "balanced",
}: {
  agentType: AgentType;
  connectorId: string;
  token: string;
  permissionProfile?: "strict" | "balanced" | "expanded";
}) {
  if (agentType === "hermes") {
    return {
      title: "Hermes Plugin 配置",
      command: [
        "git pull",
        [
          "connector/hermes-plugin/setup.sh",
          "--mode copy",
          `--connector-id ${connectorId}`,
          `--connector-token ${token}`,
          "--platform-url ws://localhost:8000/ws",
          `--permission-profile ${permissionProfile}`,
        ].join(" "),
        "hermes gateway",
      ].join("\n"),
    };
  }

  return {
    title: "Connector 模拟器",
    command: `CONNECTOR_ID=${connectorId} CONNECTOR_TOKEN=${token} python scripts/connector-sim.py`,
  };
}
