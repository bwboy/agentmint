import type { AgentType } from "@/lib/types";

export function getRuntimeNodeInstructions({
  runtimeType,
  runtimeNodeId,
  token,
  permissionProfile = "balanced",
}: {
  runtimeType: AgentType;
  runtimeNodeId: string;
  token: string;
  permissionProfile?: "strict" | "balanced" | "expanded";
}) {
  if (runtimeType === "hermes") {
    return {
      title: "Hermes Runtime Node 配置",
      command: [
        "git pull",
        [
          "connector/hermes-plugin/setup.sh",
          "--mode copy",
          `--runtime-node-id ${runtimeNodeId}`,
          `--runtime-node-token ${token}`,
          "--platform-url ws://localhost:8000/ws",
          `--permission-profile ${permissionProfile}`,
        ].join(" "),
        "hermes gateway",
      ].join("\n"),
    };
  }

  return {
    title: "OpenClaw Runtime 模拟器",
    command: `AGENTMINT_RUNTIME_NODE_ID=${runtimeNodeId} AGENTMINT_RUNTIME_NODE_TOKEN=${token} python scripts/connector-sim.py`,
  };
}

export const getConnectorInstructions = getRuntimeNodeInstructions;
