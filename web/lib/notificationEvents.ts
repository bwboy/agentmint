export const NOTIFICATIONS_CHANGED_EVENT = "agentmint:notifications-changed";

export type NotificationsChangedDetail = {
  unreadDelta?: number;
  unreadCount?: number;
};

export function emitNotificationsChanged(
  detail: NotificationsChangedDetail = {},
  target: Pick<Window, "dispatchEvent"> = window,
) {
  target.dispatchEvent(new CustomEvent(NOTIFICATIONS_CHANGED_EVENT, { detail }));
}
