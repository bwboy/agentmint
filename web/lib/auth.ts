"use client";
/** Client-side auth helpers — token in localStorage + cookie for SSR. */

const TOKEN_KEY = "agentmint_token";
const REFRESH_KEY = "agentmint_refresh";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setTokens(token: string, refresh: string) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(REFRESH_KEY, refresh);
  // Cookie so SSR pages can read it.
  document.cookie = `agentmint_token=${token}; path=/; max-age=86400; samesite=lax`;
}

export function clearTokens() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
  document.cookie = "agentmint_token=; path=/; max-age=0";
}

export function isLoggedIn(): boolean {
  return !!getToken();
}
