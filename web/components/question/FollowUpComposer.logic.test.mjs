import assert from "node:assert/strict";
import { test } from "node:test";

import { followUpDepthState } from "./FollowUpComposer.logic.ts";

test("reports follow-up depth availability from agent service rules", () => {
  assert.deepEqual(
    followUpDepthState(2, { max_followup_depth: 2 }),
    { maxDepth: 2, allowed: true, label: "追问 2/2" },
  );

  assert.deepEqual(
    followUpDepthState(3, { max_followup_depth: 2 }),
    { maxDepth: 2, allowed: false, label: "已达追问上限 2" },
  );
});
