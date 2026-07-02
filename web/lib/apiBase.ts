export function apiBaseForRuntime({
  isServer,
  publicApiBase,
  internalApiBase,
}: {
  isServer: boolean;
  publicApiBase?: string;
  internalApiBase?: string;
}) {
  const publicBase = (publicApiBase || "").trim();
  if (!isServer) return "";
  return (internalApiBase || publicBase || "http://localhost:8000").trim();
}
