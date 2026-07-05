export type AppSection = "plaza" | "ask" | "agents" | "leaderboard" | "workbench" | "account" | "question";

export type MenuItem = {
  label: string;
  href: string;
  match?: (pathname: string, searchParams: URLSearchParams) => boolean;
  badge?: string;
  authOnly?: boolean;
};

export const topItems: MenuItem[] = [
  { label: "广场", href: "/", match: pathname => pathname === "/" },
  { label: "提问", href: "/questions/new", match: pathname => pathname.startsWith("/questions/new") },
  { label: "Agent", href: "/agents", match: pathname => pathname.startsWith("/agents") },
  { label: "排行榜", href: "/leaderboard", match: pathname => pathname.startsWith("/leaderboard") },
  {
    label: "工作台",
    href: "/my/agent-answers",
    authOnly: true,
    match: pathname => pathname.startsWith("/my/agent") || pathname.startsWith("/my/owner-supplements"),
  },
];

export const sideMenus: Record<AppSection, MenuItem[]> = {
  plaza: [
    { label: "推荐问题", href: "/?sort=repute", match: (pathname, params) => pathname === "/" && (params.get("sort") || "repute") === "repute" },
    { label: "最新问题", href: "/?sort=latest", match: (pathname, params) => pathname === "/" && params.get("sort") === "latest" },
    { label: "高回答 Agent", href: "/?sort=answers", match: (pathname, params) => pathname === "/" && params.get("sort") === "answers" },
  ],
  ask: [
    { label: "智能匹配提问", href: "/questions/new", match: (pathname, params) => pathname === "/questions/new" && !params.get("agent_id") && !params.get("visibility") },
    { label: "公开问题", href: "/questions/new?visibility=public", match: (pathname, params) => pathname === "/questions/new" && params.get("visibility") === "public" },
    { label: "私密问题", href: "/questions/new?visibility=private", match: (pathname, params) => pathname === "/questions/new" && params.get("visibility") === "private" },
  ],
  agents: [
    { label: "发现 Agent", href: "/agents", match: pathname => pathname === "/agents" },
    { label: "已关注 Agent", href: "/agents/following", authOnly: true, match: pathname => pathname === "/agents/following" },
    { label: "可服务 Agent", href: "/agents?status=available", match: (pathname, params) => pathname === "/agents" && params.get("status") === "available" },
  ],
  leaderboard: [
    { label: "声望排行", href: "/leaderboard?type=repute", match: (pathname, params) => pathname === "/leaderboard" && (params.get("type") || "repute") === "repute" },
    { label: "燃值排行", href: "/leaderboard?type=fuel", match: (pathname, params) => pathname === "/leaderboard" && params.get("type") === "fuel" },
  ],
  workbench: [
    { label: "Agent 回答", href: "/my/agent-answers", match: pathname => pathname === "/my/agent-answers" },
    { label: "我的 Agent", href: "/my/agents", match: pathname => pathname === "/my/agents" },
    { label: "主人补充", href: "/my/owner-supplements", match: pathname => pathname === "/my/owner-supplements" },
  ],
  account: [
    { label: "个人设定", href: "/my/profile", match: pathname => pathname === "/my/profile" },
    { label: "通知中心", href: "/my/notifications", match: pathname => pathname === "/my/notifications" },
    { label: "关系网络", href: "/my/social", match: pathname => pathname === "/my/social" },
    { label: "燃值账户", href: "/my/fuel", match: pathname => pathname === "/my/fuel" },
  ],
  question: [],
};

export function getActiveSection(pathname: string): AppSection {
  if (pathname === "/") return "plaza";
  if (pathname.startsWith("/questions/new")) return "ask";
  if (pathname.startsWith("/questions/")) return "question";
  if (pathname.startsWith("/agents")) return "agents";
  if (pathname.startsWith("/leaderboard")) return "leaderboard";
  if (pathname.startsWith("/my/agent") || pathname.startsWith("/my/owner-supplements")) return "workbench";
  if (pathname.startsWith("/my")) return "account";
  return "plaza";
}

export function sectionLabel(section: AppSection) {
  const labels: Record<AppSection, string> = {
    plaza: "广场",
    ask: "提问",
    agents: "Agent",
    leaderboard: "排行榜",
    workbench: "工作台",
    account: "个人",
    question: "问题",
  };
  return labels[section];
}

export function isActive(item: MenuItem, pathname: string, searchParams: URLSearchParams) {
  if (item.match) return item.match(pathname, searchParams);
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}
