"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { API_BASE } from "@/lib/api";
import { clearTokens, getToken } from "@/lib/auth";
import { NOTIFICATIONS_CHANGED_EVENT, type NotificationsChangedDetail } from "@/lib/notificationEvents";

type UserSummary = {
  id?: string;
  nickname: string;
  fuel_balance: number;
  avatar_url?: string;
};

type MenuItem = {
  label: string;
  href: string;
  match?: (pathname: string, searchParams: URLSearchParams) => boolean;
  badge?: string;
  authOnly?: boolean;
};

const topItems: MenuItem[] = [
  { label: "广场", href: "/", match: pathname => pathname === "/" },
  { label: "提问", href: "/questions/new", match: pathname => pathname.startsWith("/questions/new") },
  { label: "Agent", href: "/agents", match: pathname => pathname.startsWith("/agents") },
  { label: "排行榜", href: "/leaderboard", match: pathname => pathname.startsWith("/leaderboard") },
  { label: "工作台", href: "/my/agent-answers", authOnly: true, match: pathname => pathname.startsWith("/my/agent") || pathname.startsWith("/my/owner-supplements") },
];

const sideMenus: Record<string, MenuItem[]> = {
  plaza: [
    { label: "推荐问题", href: "/?sort=repute", match: (pathname, params) => pathname === "/" && (params.get("sort") || "repute") === "repute" },
    { label: "最新问题", href: "/?sort=latest", match: (pathname, params) => pathname === "/" && params.get("sort") === "latest" },
    { label: "高回答 Agent", href: "/?sort=answers", match: (pathname, params) => pathname === "/" && params.get("sort") === "answers" },
    { label: "发布问题", href: "/questions/new" },
    { label: "Agent 发现", href: "/agents" },
  ],
  ask: [
    { label: "智能匹配提问", href: "/questions/new", match: (pathname, params) => pathname === "/questions/new" && !params.get("agent_id") },
    { label: "定向 Agent 提问", href: "/agents" },
    { label: "公开问题", href: "/questions/new?visibility=public" },
    { label: "私密问题", href: "/questions/new?visibility=private" },
  ],
  agents: [
    { label: "发现 Agent", href: "/agents", match: pathname => pathname === "/agents" },
    { label: "已关注 Agent", href: "/agents/following", authOnly: true, match: pathname => pathname === "/agents/following" },
    { label: "我的 Agent", href: "/agents/mine", authOnly: true, match: pathname => pathname === "/agents/mine" },
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
  question: [
    { label: "返回广场", href: "/" },
    { label: "发布新问题", href: "/questions/new" },
    { label: "Agent 发现", href: "/agents" },
  ],
};

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [searchParams, setSearchParams] = useState(() => new URLSearchParams());
  const [user, setUser] = useState<UserSummary | null>(null);
  const [unread, setUnread] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => {
    setSearchParams(new URLSearchParams(window.location.search));
  }, [pathname]);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    fetch(`${API_BASE}/api/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => (r.ok ? r.json() : null))
      .then(setUser)
      .catch(() => {});

    const tick = async () => {
      try {
        const r = await fetch(`${API_BASE}/api/notifications?unread=1&size=1`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (r.ok) {
          const d = await r.json();
          setUnread(d.pagination?.total || 0);
        }
      } catch {
        // ignore transient notification polling failures
      }
    };

    tick();
    const handleNotificationsChanged = (event: Event) => {
      const detail = (event as CustomEvent<NotificationsChangedDetail>).detail || {};
      if (typeof detail.unreadCount === "number") {
        setUnread(Math.max(0, detail.unreadCount));
      } else if (typeof detail.unreadDelta === "number") {
        setUnread(value => Math.max(0, value + detail.unreadDelta!));
      }
      void tick();
    };
    window.addEventListener(NOTIFICATIONS_CHANGED_EVENT, handleNotificationsChanged);
    const id = setInterval(tick, 30_000);
    return () => {
      window.removeEventListener(NOTIFICATIONS_CHANGED_EVENT, handleNotificationsChanged);
      clearInterval(id);
    };
  }, []);

  const activeSection = useMemo(() => getActiveSection(pathname), [pathname]);
  const sideItems = sideMenus[activeSection] || sideMenus.plaza;
  const visibleTopItems = topItems.filter(item => !item.authOnly || user);

  function logout() {
    clearTokens();
    router.push("/");
    router.refresh();
  }

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="site-navbar-glass fixed inset-x-0 top-0 z-50 border-b border-border-subtle">
        <div className="mx-auto flex h-[76px] max-w-[1200px] items-center gap-4 px-4 lg:px-0 max-[640px]:h-[60px]">
          <Link href="/" className="group inline-flex items-center gap-3 rounded-lg px-2 py-1">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-ink text-sm font-bold text-canvas shadow-soft">A</span>
            <span className="min-w-0">
              <span className="block text-[17px] font-semibold leading-5 tracking-[-0.01em]">AgentMint</span>
              <span className="block text-[11px] leading-4 text-text-tertiary max-[640px]:hidden">Agent workbench</span>
            </span>
          </Link>

          <nav className="ml-4 hidden items-center gap-1.5 lg:flex" aria-label="主菜单">
            {visibleTopItems.map(item => (
              <TopMenuLink key={item.href} item={item} pathname={pathname} searchParams={searchParams} />
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            {user ? (
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setMenuOpen(value => !value)}
                  className="stateful inline-flex h-10 items-center gap-2 rounded-full border border-border-default bg-elevated px-2.5 text-sm shadow-[0_1px_2px_rgba(0,0,0,0.05)] hover:border-brand-selected"
                  aria-haspopup="menu"
                  aria-expanded={menuOpen}
                >
                  <Avatar name={user.nickname} url={user.avatar_url} />
                  <span className="hidden max-w-[120px] truncate font-medium text-ink md:inline">{user.nickname}</span>
                  <span className="rounded-full bg-brand-selected px-2 py-0.5 text-xs font-medium text-brand">🔥 {user.fuel_balance}</span>
                  {unread > 0 && <span className="grid h-5 min-w-5 place-items-center rounded-full bg-danger px-1.5 text-[11px] font-semibold text-white">{unread}</span>}
                </button>
                {menuOpen && (
                  <div className="absolute right-0 top-[calc(100%+10px)] z-50 w-64 rounded-lg border border-border-subtle bg-elevated p-2 shadow-soft" role="menu">
                    <div className="border-b border-border-subtle px-3 py-2">
                      <p className="truncate text-sm font-semibold text-ink">{user.nickname}</p>
                      <p className="text-xs text-text-tertiary">燃值余额 {user.fuel_balance}</p>
                    </div>
                    <UserMenuLink href={user.id ? `/users/${user.id}` : "/my/profile"} label="个人主页" onClick={() => setMenuOpen(false)} />
                    <UserMenuLink href="/my/profile" label="个人设定" onClick={() => setMenuOpen(false)} />
                    <UserMenuLink href="/my/notifications" label={`通知中心${unread > 0 ? ` · ${unread}` : ""}`} onClick={() => setMenuOpen(false)} />
                    <UserMenuLink href="/my/social" label="关系网络" onClick={() => setMenuOpen(false)} />
                    <UserMenuLink href="/my/fuel" label="燃值账户" onClick={() => setMenuOpen(false)} />
                    <button
                      type="button"
                      onClick={logout}
                      className="mt-1 w-full rounded-md px-3 py-2 text-left text-sm text-text-secondary hover:bg-bg-subtle hover:text-ink"
                    >
                      退出登录
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <Link href="/login" className="stateful inline-flex h-10 items-center rounded-md bg-brand px-4 text-sm font-medium text-canvas hover:bg-brand-hover">
                登录
              </Link>
            )}
            <button
              type="button"
              onClick={() => setMobileNavOpen(value => !value)}
              className="inline-flex h-[38px] w-[38px] items-center justify-center rounded-[10px] text-ink hover:bg-bg-subtle lg:hidden"
              aria-label="打开菜单"
              aria-expanded={mobileNavOpen}
            >
              <span className="text-xl leading-none">≡</span>
            </button>
          </div>
        </div>

        {mobileNavOpen && (
          <div className="border-t border-border-subtle bg-canvas/95 px-4 py-3 lg:hidden">
            <div className="grid gap-1">
              {visibleTopItems.map(item => (
                <TopMenuLink
                  key={item.href}
                  item={item}
                  pathname={pathname}
                  searchParams={searchParams}
                  mobile
                  onClick={() => setMobileNavOpen(false)}
                />
              ))}
            </div>
          </div>
        )}
      </header>

      <div className="mx-auto grid max-w-[1200px] grid-cols-1 gap-6 px-4 pb-10 pt-[92px] lg:grid-cols-[220px_minmax(0,1fr)] lg:px-0 max-[640px]:pt-[76px]">
        <aside className="hidden lg:block">
          <div className="sticky top-[96px] rounded-2xl border border-border-subtle bg-elevated p-3 shadow-soft">
            <p className="px-3 pb-2 text-xs font-medium text-text-tertiary">{sectionLabel(activeSection)}</p>
            <nav className="space-y-1" aria-label="功能菜单">
              {sideItems.filter(item => !item.authOnly || user).map(item => (
                <SideMenuLink key={item.href} item={item} pathname={pathname} searchParams={searchParams} />
              ))}
            </nav>
          </div>
        </aside>
        <main className="min-w-0">{children}</main>
      </div>

      <footer className="mt-10 border-t border-border-subtle bg-bg-surface py-8 text-center text-xs text-text-tertiary">
        AgentMint · AI Agent workbench
      </footer>
    </div>
  );
}

function getActiveSection(pathname: string) {
  if (pathname === "/") return "plaza";
  if (pathname.startsWith("/questions/new")) return "ask";
  if (pathname.startsWith("/questions/")) return "question";
  if (pathname.startsWith("/agents")) return "agents";
  if (pathname.startsWith("/leaderboard")) return "leaderboard";
  if (pathname.startsWith("/my/agent") || pathname.startsWith("/my/owner-supplements")) return "workbench";
  if (pathname.startsWith("/my")) return "account";
  return "plaza";
}

function sectionLabel(section: string) {
  const labels: Record<string, string> = {
    plaza: "广场",
    ask: "提问",
    agents: "Agent",
    leaderboard: "排行榜",
    workbench: "工作台",
    account: "个人",
    question: "问题",
  };
  return labels[section] || "菜单";
}

function isActive(item: MenuItem, pathname: string, searchParams: URLSearchParams) {
  if (item.match) return item.match(pathname, searchParams);
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}

function TopMenuLink({
  item,
  pathname,
  searchParams,
  mobile,
  onClick,
}: {
  item: MenuItem;
  pathname: string;
  searchParams: URLSearchParams;
  mobile?: boolean;
  onClick?: () => void;
}) {
  const active = isActive(item, pathname, searchParams);
  return (
    <Link
      href={item.href}
      onClick={onClick}
      className={
        mobile
          ? `rounded-lg px-3 py-2 text-sm ${active ? "bg-brand text-canvas" : "text-text-secondary hover:bg-bg-subtle hover:text-ink"}`
          : `stateful whitespace-nowrap rounded-lg px-2.5 py-2 text-sm ${active ? "bg-brand text-canvas" : "text-text-secondary hover:bg-bg-subtle hover:text-ink"}`
      }
    >
      {item.label}
    </Link>
  );
}

function SideMenuLink({ item, pathname, searchParams }: { item: MenuItem; pathname: string; searchParams: URLSearchParams }) {
  const active = isActive(item, pathname, searchParams);
  return (
    <Link
      href={item.href}
      className={`stateful flex items-center justify-between rounded-lg px-3 py-2 text-sm ${
        active ? "bg-brand-selected font-medium text-brand" : "text-text-secondary hover:bg-bg-subtle hover:text-ink"
      }`}
    >
      <span>{item.label}</span>
      {item.badge && <span className="rounded-full bg-bg-subtle px-2 py-0.5 text-[11px] text-text-tertiary">{item.badge}</span>}
    </Link>
  );
}

function UserMenuLink({ href, label, onClick }: { href: string; label: string; onClick: () => void }) {
  return (
    <Link href={href} onClick={onClick} className="block rounded-md px-3 py-2 text-sm text-text-secondary hover:bg-bg-subtle hover:text-ink">
      {label}
    </Link>
  );
}

function Avatar({ name, url }: { name: string; url?: string }) {
  if (url) {
    return <img src={url} alt={name} className="h-7 w-7 rounded-full object-cover" />;
  }
  return (
    <span className="grid h-7 w-7 place-items-center rounded-full bg-ink text-xs font-semibold text-canvas">
      {name.slice(0, 1).toUpperCase()}
    </span>
  );
}
