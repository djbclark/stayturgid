import config = require("./config.js");

let channelReady = false;
const STATE_FILE = config.SD_ROOT + "/state/notify_state.json";

function ensureChannel(): void {
  if (channelReady) return;
  if (device.sdkInt >= 26) {
    const nm = context.getSystemService(context.NOTIFICATION_SERVICE) as android.app.NotificationManager;
    const channel = new android.app.NotificationChannel(
      config.NOTIFY_CHANNEL,
      "stayturgid",
      android.app.NotificationManager.IMPORTANCE_HIGH,
    );
    channel.setDescription("stayturgid remote-access watchdog");
    nm.createNotificationChannel(channel);
  }
  channelReady = true;
}

/** Stable notification id per key so repeats coalesce instead of piling up. */
function idFor(key: string): number {
  let h = 0;
  for (let i = 0; i < key.length; i++) {
    h = (h * 31 + key.charCodeAt(i)) & 0x7fffffff;
  }
  return 5000 + (h % 100000);
}

type RepeatCounts = Record<string, number>;

// Repeat counts persist on /sdcard: engine restarts (the source of past
// notification spam) must not reset them — one notification per key, ever,
// with "(Nx)" and the most recent timestamp.
function readCounts(): RepeatCounts {
  try {
    if (files.exists(STATE_FILE)) {
      return (JSON.parse(String(files.read(STATE_FILE))) as RepeatCounts) || {};
    }
  } catch {
    /* corrupt state — start over */
  }
  return {};
}

function writeCounts(counts: RepeatCounts): void {
  try {
    config.ensureParentDir(STATE_FILE); // self-heal if the state dir was deleted
    files.write(STATE_FILE, JSON.stringify(counts));
  } catch {
    /* best effort */
  }
}

export function show(title: string, text: string, key?: string): void {
  ensureChannel();
  const notificationKey = key || title;

  const counts = readCounts();
  const n = (counts[notificationKey] || 0) + 1;
  counts[notificationKey] = n;
  writeCounts(counts);
  const displayTitle = n > 1 ? `${title} (${n}x)` : title;

  const nm = context.getSystemService(context.NOTIFICATION_SERVICE) as android.app.NotificationManager;
  const builder =
    device.sdkInt >= 26
      ? new android.app.Notification.Builder(context, config.NOTIFY_CHANNEL)
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
export function clear(key: string): void {
  const counts = readCounts();
  if (counts[key]) {
    delete counts[key];
    writeCounts(counts);
  }
  const nm = context.getSystemService(context.NOTIFICATION_SERVICE) as android.app.NotificationManager;
  nm.cancel(idFor(key));
}
