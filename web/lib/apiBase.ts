export function apiBaseForRuntime({
  isServer,
  publicApiBase,
  internalApiBase,
  browserHostname,
}: {
  isServer: boolean;
  publicApiBase?: string;
  internalApiBase?: string;
  browserHostname?: string;
}) {
  const publicBase = (publicApiBase || "").trim();
  if (!isServer) {
    if (isLoopbackApi(publicBase) && !isLoopbackHost(browserHostname || "")) {
      return "";
    }
    return publicBase;
  }
  return (internalApiBase || publicBase || "http://localhost:8000").trim();
}

function isLoopbackApi(value: string) {
  return /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?($|\/)/i.test(value);
}

function isLoopbackHost(value: string) {
  return value === "localhost" || value === "127.0.0.1" || value === "::1";
}
