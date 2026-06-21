"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { setTokens } from "@/lib/auth";

export function LoginForm() {
  const router = useRouter();
  const [phone, setPhone] = useState("+8613800000002");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function sendCode() {
    setErr(null); setBusy(true);
    try {
      await api("/api/auth/send-code", { method: "POST", json: { phone } });
      setSent(true);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function verify() {
    setErr(null); setBusy(true);
    try {
      const r = await api<{ token: string; refresh_token: string }>(
        "/api/auth/verify-code",
        { method: "POST", json: { phone, code } }
      );
      setTokens(r.token, r.refresh_token);
      window.location.href = "/";
    } catch (e: any) {
      setErr(e instanceof ApiError ? e.message : "登录失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-xs text-gray-500 mb-1">手机号</label>
        <input value={phone} onChange={e => setPhone(e.target.value)}
          className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-primary"
          placeholder="+8613800000002" />
      </div>
      {sent ? (
        <>
          <div>
            <label className="block text-xs text-gray-500 mb-1">验证码（开发模式默认 123456）</label>
            <input value={code} onChange={e => setCode(e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-primary"
              placeholder="6 位数字" inputMode="numeric" />
          </div>
          <button onClick={verify} disabled={busy || code.length < 4}
            className="w-full py-2.5 rounded-lg bg-primary text-white text-sm font-medium hover:bg-primary-dark disabled:opacity-50">
            {busy ? "登录中..." : "登录"}
          </button>
          <button onClick={() => setSent(false)} className="text-xs text-gray-400 hover:text-gray-600">
            重新发送验证码
          </button>
        </>
      ) : (
        <button onClick={sendCode} disabled={busy || !phone}
          className="w-full py-2.5 rounded-lg bg-primary text-white text-sm font-medium hover:bg-primary-dark disabled:opacity-50">
          {busy ? "发送中..." : "获取验证码"}
        </button>
      )}
      {err && <p className="text-xs text-red-500">{err}</p>}
    </div>
  );
}
