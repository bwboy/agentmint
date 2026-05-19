/** Thin fetch wrapper for the FastAPI backend.
 *  Server components call `api()` directly; client components import from
 *  `./api-client` (which adds token retrieval from localStorage).
 */
import type { ApiList } from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type FetchOpts = RequestInit & { token?: string | null; json?: any };

export async function api<T = any>(path: string, opts: FetchOpts = {}): Promise<T> {
  const { token, json, headers, ...rest } = opts;
  const init: RequestInit = {
    ...rest,
    headers: {
      ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
    cache: rest.cache ?? "no-store",
  };

  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    let detail: any = null;
    try { detail = await res.json(); } catch { /* ignore */ }
    throw new ApiError(res.status, detail?.detail || res.statusText, detail);
  }
  if (res.status === 204) return undefined as unknown as T;
  return res.json();
}

export class ApiError extends Error {
  constructor(public status: number, message: string, public payload?: any) {
    super(message);
  }
}

export type { ApiList };
