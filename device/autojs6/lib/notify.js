// @generated
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.show = show;
exports.clear = clear;
// Rhino gotchas (redeclaration collisions, for...of, exports stamp, Java-string coercion): see docs/architecture/components/autojs6.md "Rhino JS-engine gotchas" before editing.
const notifyConfig = require("./config.js");
let channelReady = false;
const STATE_FILE = notifyConfig.SD_ROOT + "/state/notify_state.json";
function ensureChannel() {
  if (channelReady) return;
  if (device.sdkInt >= 26) {
    const nm = context.getSystemService(context.NOTIFICATION_SERVICE);
    const channel = new android.app.NotificationChannel(
      notifyConfig.NOTIFY_CHANNEL,
      "stayturgid",
      android.app.NotificationManager.IMPORTANCE_HIGH,
    );
    channel.setDescription("stayturgid remote-access watchdog");
    nm.createNotificationChannel(channel);
  }
  channelReady = true;
}
/** Stable notification id per key so repeats coalesce instead of piling up. */
function idFor(key) {
  let h = 0;
  for (let i = 0; i < key.length; i++) {
    h = (h * 31 + key.charCodeAt(i)) & 0x7fffffff;
  }
  return 5000 + (h % 100000);
}
// Repeat counts persist on /sdcard: engine restarts (the source of past
// notification spam) must not reset them — one notification per key, ever,
// with "(Nx)" and the most recent timestamp.
function readCounts() {
  try {
    if (files.exists(STATE_FILE)) {
      return JSON.parse(String(files.read(STATE_FILE))) || {};
    }
  } catch (_a) {
    /* corrupt state — start over */
  }
  return {};
}
function writeCounts(counts) {
  try {
    notifyConfig.ensureParentDir(STATE_FILE); // self-heal if the state dir was deleted
    files.write(STATE_FILE, JSON.stringify(counts));
  } catch (_a) {
    /* best effort */
  }
}
function show(title, text, key) {
  ensureChannel();
  const notificationKey = key || title;
  const counts = readCounts();
  const n = (counts[notificationKey] || 0) + 1;
  counts[notificationKey] = n;
  writeCounts(counts);
  const displayTitle = n > 1 ? `${title} (${n}x)` : title;
  const nm = context.getSystemService(context.NOTIFICATION_SERVICE);
  const builder =
    device.sdkInt >= 26
      ? new android.app.Notification.Builder(context, notifyConfig.NOTIFY_CHANNEL)
      : new android.app.Notification.Builder(context);
  builder
    .setContentTitle(displayTitle)
    .setContentText(text)
    .setSmallIcon(android.R.drawable.ic_dialog_alert)
    .setOnlyAlertOnce(false)
    .setAutoCancel(true);
  nm.notify(idFor(notificationKey), builder.build());
}
/** Remove a previously shown alert and reset its repeat count (recovery). */
function clear(key) {
  const counts = readCounts();
  if (counts[key]) {
    delete counts[key];
    writeCounts(counts);
  }
  const nm = context.getSystemService(context.NOTIFICATION_SERVICE);
  nm.cancel(idFor(key));
}
