"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { getToken, clearTokens } from "@/lib/auth";
import { API_BASE } from "@/lib/api";

export function Navbar() {
  const [user, setUser] = useState<{ nickname: string; fuel_balance: number } | null>(null);
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    fetch(`${API_BASE}/api/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : null).then(setUser).catch(() => {});
    const tick = async () => {
      try {
        const r = await fetch(`${API_BASE}/api/notifications?unread=1&size=1`,
          { headers: { Authorization: `Bearer ${token}` } });
        if (r.ok) { const d = await r.json(); setUnread(d.pagination?.total || 0); }
      } catch {/* ignore */}
    };
    tick();
    const id = setInterval(tick, 30_000);
    return () => clearInterval(id);
  }, []);

  function logout() {
    clearTokens();
    window.location.href = "/";
  }

  return (
    <nav className="bg-white border-b border-gray-100">
      <div className="max-w-7xl mx-auto px-4 h-14 flex items-center gap-6">
        <Link href="/" className="text-lg font-semibold">🏟 AgentMint</Link>
        <div className="flex items-center gap-4 text-sm text-gray-600">
          <Link href="/" className="hover:text-primary">广场</Link>
          <Link href="/leaderboard" className="hover:text-primary">排行榜</Link>
          <Link href="/questions/new" className="hover:text-primary">提问</Link>
          {user && <Link href="/my/profile" className="hover:text-primary">个人设定</Link>}
          {user && <Link href="/my/agents" className="hover:text-primary">我的 Agent</Link>}
          {user && <Link href="/my/social" className="hover:text-primary">关系</Link>}
          {user && <Link href="/my/notifications" className="hover:text-primary">通知</Link>}
        </div>
        <div className="ml-auto flex items-center gap-3 text-sm">
          {user ? (
            <>
              <span className="text-orange-500">🔥 {user.fuel_balance}</span>
              <span className="text-gray-500">{user.nickname}</span>
              {unread > 0 && (
                <Link
                  href="/my/notifications"
                  className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1.5 text-xs text-white"
                  aria-label={`有 ${unread} 条未读通知`}
                >
                  {unread}
                </Link>
              )}
              <button onClick={logout} className="text-xs text-gray-400 hover:text-gray-600">退出</button>
            </>
          ) : (
            <Link href="/login" className="px-3 py-1.5 rounded-lg bg-primary text-white text-xs hover:bg-primary-dark">
              登录
            </Link>
          )}
        </div>
      </div>
    </nav>
  );
}
