import assert from "node:assert/strict";
import { test } from "node:test";

import { apiBaseForRuntime } from "./apiBase.ts";

test("browser API base defaults to same-origin proxy", () => {
  assert.equal(apiBaseForRuntime({ isServer: false }), "");
});

test("browser API base uses explicit public URL when configured", () => {
  assert.equal(
    apiBaseForRuntime({ isServer: false, publicApiBase: "https://api.example.com" }),
    "https://api.example.com",
  );
});

test("browser API base ignores loopback public URL from remote host", () => {
  assert.equal(
    apiBaseForRuntime({
      isServer: false,
      publicApiBase: "http://localhost:8000",
      browserHostname: "192.168.1.88",
    }),
    "",
  );
});

test("browser API base keeps loopback public URL for local browser", () => {
  assert.equal(
    apiBaseForRuntime({
      isServer: false,
      publicApiBase: "http://localhost:8000",
      browserHostname: "localhost",
    }),
    "http://localhost:8000",
  );
});

test("server API base prefers internal backend URL", () => {
  assert.equal(
    apiBaseForRuntime({
      isServer: true,
      publicApiBase: "https://public.example.com",
      internalApiBase: "http://backend:8000",
    }),
    "http://backend:8000",
  );
});

test("server API base falls back to localhost for local development", () => {
  assert.equal(apiBaseForRuntime({ isServer: true }), "http://localhost:8000");
});
