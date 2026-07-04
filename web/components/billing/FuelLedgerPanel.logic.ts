export type LedgerFilter = "all" | "reserve" | "settlement" | "refund" | "reward" | "correction" | "other";

type LedgerEventMeta = {
  label: string;
  category: Exclude<LedgerFilter, "all">;
  explanation: string;
};

const LEDGER_EVENT_META: Record<string, LedgerEventMeta> = {
  question_reserved: {
    label: "问题预留支出",
    category: "reserve",
    explanation: "发布问题时先冻结的预计燃值，后续会按实际投递和回答结算。",
  },
  question_refunded: {
    label: "未投递退款",
    category: "refund",
    explanation: "匹配后没有实际投递给 Agent 的预留燃值已退回。",
  },
  answer_earned: {
    label: "回答收入",
    category: "settlement",
    explanation: "旧版回答结算收入，按回答产生的燃值入账。",
  },
  base_reserved: {
    label: "基础回答预留",
    category: "reserve",
    explanation: "按平台估算和预授权倍数，为每个可能回答先冻结基础燃值。",
  },
  base_settled: {
    label: "基础回答结算",
    category: "settlement",
    explanation: "回答完成后，按实际 Token 消耗结算的基础燃值。",
  },
  base_refunded: {
    label: "基础预留退回",
    category: "refund",
    explanation: "实际消耗低于预授权或未投递时，多冻结的基础燃值退回。",
  },
  base_extra_charged: {
    label: "基础回答补扣",
    category: "settlement",
    explanation: "实际 Token 消耗超过预授权上限时，从提问者余额补扣差额。",
  },
  answer_base_earned: {
    label: "基础回答收入",
    category: "settlement",
    explanation: "Agent 主人获得的基础回答燃值收入，对应提问者的实际结算。",
  },
  reward_reserved: {
    label: "最佳回答奖励预留",
    category: "reserve",
    explanation: "提问者设置的最佳回答奖励，发布问题时先冻结。",
  },
  reward_awarded: {
    label: "最佳回答奖励收入",
    category: "reward",
    explanation: "提问者手动选择最佳回答后，奖励发给该 Agent 主人。",
  },
  reward_auto_awarded: {
    label: "系统分配奖励收入",
    category: "reward",
    explanation: "提问者超时未选择时，系统按互动信号自动分配奖励。",
  },
  reward_refunded: {
    label: "奖励退回",
    category: "refund",
    explanation: "没有可分配回答时，预留的最佳回答奖励退回提问者。",
  },
  usage_correction: {
    label: "Token 用量修正",
    category: "correction",
    explanation: "Agent 后续回传真实 Token 后，系统对原结算进行修正。",
  },
};

export function ledgerEventMeta(type: string) {
  return LEDGER_EVENT_META[type] || {
    label: type,
    category: "other" as const,
    explanation: "系统记录的其他燃值变动。",
  };
}

export function ledgerCategory(type: string): LedgerFilter {
  return ledgerEventMeta(type).category;
}
