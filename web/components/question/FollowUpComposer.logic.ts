import type { AgentServiceRules } from "@/lib/types";

export function followUpDepthState(
  nextDepth: number,
  serviceRules?: Partial<AgentServiceRules> | null,
) {
  const maxDepth = Math.max(0, Number(serviceRules?.max_followup_depth ?? 2));
  const allowed = nextDepth <= maxDepth;
  return {
    maxDepth,
    allowed,
    label: allowed ? `追问 ${nextDepth}/${maxDepth}` : `已达追问上限 ${maxDepth}`,
  };
}
