import type { AgentType } from "@/lib/types";

function shellQuote(value: string) {
  return `'${value.replace(/'/g, "'\\''")}'`;
}

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
        "hermes config set gateway.multiplex_profiles true",
        "hermes gateway",
      ].join("\n"),
    };
  }

  return {
    title: "OpenClaw Runtime 模拟器",
    command: `AGENTMINT_RUNTIME_NODE_ID=${runtimeNodeId} AGENTMINT_RUNTIME_NODE_TOKEN=${token} python scripts/connector-sim.py`,
  };
}

export function getRuntimeProfileInstructions({
  runtimeType,
  profileName,
  workspaceName,
}: {
  runtimeType: AgentType;
  profileName?: string;
  workspaceName?: string;
}) {
  if (runtimeType === "hermes") {
    const profile = (profileName || "").trim();
    return {
      title: "Hermes Profile 初始化",
      command: [
        `hermes profile create ${shellQuote(profile)}`,
        "hermes config set gateway.multiplex_profiles true",
        "hermes gateway",
      ].join("\n"),
    };
  }

  const workspace = (workspaceName || "").trim();
  return {
    title: "OpenClaw Workspace 初始化",
    command: [
      `AGENTMINT_WORKSPACE=${shellQuote(workspace)}`,
      "# 在 OpenClaw 运行端创建或选择这个 workspace 后重启 connector",
    ].join("\n"),
  };
}

export const getConnectorInstructions = getRuntimeNodeInstructions;
