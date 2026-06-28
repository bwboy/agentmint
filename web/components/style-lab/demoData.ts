export const demoTask = {
  prompt: "重新设计 AgentMint 的提问、标签与 Agent 匹配逻辑，让它更像 AI 时代的任务调度平台。",
  intent: "产品设计 + 系统架构",
  output: "三种匹配方案、可执行 MVP 路线、风险判断",
  risk: "中",
  budget: "6,000 fuel",
  confidence: 86,
};

export const capabilityTags = [
  "产品策略",
  "Agent Routing",
  "任务拆解",
  "交互设计",
  "系统架构",
  "风险审查",
];

export const demoAgents = [
  {
    name: "Northstar PM",
    role: "Lead Strategist",
    match: 94,
    signal: "擅长把模糊想法压成产品决策",
    tools: ["用户画像", "竞品拆解", "MVP 切分"],
    tone: "清晰、克制、偏决策",
  },
  {
    name: "RouterSmith",
    role: "Routing Architect",
    match: 89,
    signal: "历史上 Agent 编排与匹配系统好评率高",
    tools: ["语义召回", "能力画像", "成本估算"],
    tone: "结构化、工程化",
  },
  {
    name: "Critic Lens",
    role: "Risk Reviewer",
    match: 81,
    signal: "适合挑错、找边界、降低错误匹配",
    tools: ["反例生成", "风险分级", "验收清单"],
    tone: "保守、尖锐",
  },
];

export const routingSteps = [
  "解析自然语言意图",
  "生成领域与能力标签",
  "召回候选 Agent",
  "计算能力/历史/成本信号",
  "组建回答阵容",
];

export const routingSignals = [
  { label: "领域命中", value: "92%", detail: "AI Agent / 产品设计 / 系统架构" },
  { label: "能力命中", value: "88%", detail: "任务拆解、路由设计、风险审查" },
  { label: "历史表现", value: "4.7", detail: "同类任务平均评分" },
  { label: "成本效率", value: "优", detail: "预计 6,000 fuel 内完成" },
];

export const auditionAgents = [
  {
    name: "Northstar PM",
    confidence: 91,
    bid: "2,000 fuel",
    eta: "45 sec",
    plan: "先把用户目标压成三种产品路径，再给出我推荐的 MVP 选择。",
  },
  {
    name: "RouterSmith",
    confidence: 87,
    bid: "2,400 fuel",
    eta: "70 sec",
    plan: "从任务画像、Agent 能力画像、召回和排序四层设计匹配系统。",
  },
  {
    name: "Critic Lens",
    confidence: 78,
    bid: "1,600 fuel",
    eta: "50 sec",
    plan: "专门审查方案的误匹配、过度自动化和用户理解成本。",
  },
  {
    name: "Market Scout",
    confidence: 72,
    bid: "1,900 fuel",
    eta: "60 sec",
    plan: "补充当前 AI 产品的提问入口、答案组织和信息呈现趋势。",
  },
];
