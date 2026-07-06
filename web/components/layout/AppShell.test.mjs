import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const source = readFileSync(new URL("./AppShell.tsx", import.meta.url), "utf8");

test("login page uses auth-only shell without app menus", () => {
  assert.match(source, /AUTH_ONLY_PATHS/);
  assert.match(source, /const AUTH_ONLY_PATHS = \["\/login"\]/);
  assert.match(source, /pathname === path/);
  assert.match(source, /isAuthOnlyPath/);
  assert.match(source, /return <AuthOnlyShell>/);
});
