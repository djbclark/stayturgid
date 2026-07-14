var config = require("./config.js");

var _channelReady = false;
var STATE_FILE = config.SD_ROOT + "/state/notify_state.json";

function ensureChannel() {
  if (_channelReady) return;
  if (device.sdkInt >= 26) {
    importClass(android.app.NotificationChannel);
    importClass(android.app.NotificationManager);
    var nm = context.getSystemService(context.NOTIFICATION_SERVICE);
    var ch = new NotificationChannel(config.NOTIFY_CHANNEL, "stayturgid", NotificationManager.IMPORTANCE_HIGH);
    ch.setDescription("stayturgid remote-access watchdog");
    nm.createNotificationChannel(ch);
  }
  _channelReady = true;
}

/** Stable notification id per key so repeats coalesce instead of piling up. */
function idFor(key) {
  var s = String(key);
  var h = 0;
  for (var i = 0; i < s.length; i++) {
    h = (h * 31 + s.charCodeAt(i)) & 0x7fffffff;
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
  } catch (e) {
    /* corrupt state — start over */
  }
  return {};
}

function writeCounts(counts) {
  try {
    config.ensureParentDir(STATE_FILE); // self-heal if the state dir was deleted
    files.write(STATE_FILE, JSON.stringify(counts));
  } catch (e) {
    /* best effort */
  }
}

function show(title, text, key) {
  ensureChannel();
  key = key || String(title);

  var counts = readCounts();
  var n = (counts[key] || 0) + 1;
  counts[key] = n;
  writeCounts(counts);
  if (n > 1) title = String(title) + " (" + n + "x)";

  var nm = context.getSystemService(context.NOTIFICATION_SERVICE);
  var builder;
  if (device.sdkInt >= 26) {
    builder = new android.app.Notification.Builder(context, config.NOTIFY_CHANNEL);
  } else {
    builder = new android.app.Notification.Builder(context);
  }
  builder
    .setContentTitle(String(title))
    .setContentText(String(text))
    .setSmallIcon(android.R.drawable.ic_dialog_alert)
    .setOnlyAlertOnce(false)
    .setAutoCancel(true);
  nm.notify(idFor(key), builder.build());
}

/** Remove a previously shown alert and reset its repeat count (recovery). */
function clear(key) {
  var counts = readCounts();
  if (counts[key]) {
    delete counts[key];
    writeCounts(counts);
  }
  var nm = context.getSystemService(context.NOTIFICATION_SERVICE);
  nm.cancel(idFor(key));
}

module.exports = { show: show, clear: clear };
