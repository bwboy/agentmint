import assert from "node:assert/strict";
import { test } from "node:test";

import { NOTIFICATIONS_CHANGED_EVENT, emitNotificationsChanged } from "./notificationEvents.ts";

test("emits a shared notifications-changed event", () => {
  const events = [];
  const target = {
    dispatchEvent(event) {
      events.push({ type: event.type, detail: event.detail });
      return true;
    },
  };

  emitNotificationsChanged({ unreadDelta: -1 }, target);

  assert.equal(NOTIFICATIONS_CHANGED_EVENT, "agentmint:notifications-changed");
  assert.deepEqual(events, [{ type: NOTIFICATIONS_CHANGED_EVENT, detail: { unreadDelta: -1 } }]);
});
