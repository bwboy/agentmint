/** Server-side helpers: read cookie + call API as logged-in user. */
import { cookies } from "next/headers";
import { api } from "./api";

export function getServerToken(): string | null {
  return cookies().get("agentmint_token")?.value ?? null;
}

export async function serverApi<T = any>(path: string, opts: Parameters<typeof api>[1] = {}): Promise<T> {
  const token = opts.token ?? getServerToken();
  return api<T>(path, { ...opts, token });
}
