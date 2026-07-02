import assert from "node:assert/strict";
import { test } from "node:test";

import { apiBaseForRuntime } from "./apiBase.ts";

test("browser API base defaults to same-origin proxy", () => {
  assert.equal(apiBaseForRuntime({ isServer: false }), "");
});

test("browser API base ignores explicit public URL and uses same-origin proxy", () => {
  assert.equal(
    apiBaseForRuntime({ isServer: false, publicApiBase: "https://api.example.com" }),
    "",
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
