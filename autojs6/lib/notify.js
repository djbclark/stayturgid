var config = require("./config.js");

var _channelReady = false;

function ensureChannel() {
    if (_channelReady) return;
    if (device.sdkInt >= 26) {
        importClass(android.app.NotificationChannel);
        importClass(android.app.NotificationManager);
        var nm = context.getSystemService(context.NOTIFICATION_SERVICE);
        var ch = new NotificationChannel(
            config.NOTIFY_CHANNEL,
            "stayturgid",
            NotificationManager.IMPORTANCE_HIGH
        );
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
        h = ((h * 31) + s.charCodeAt(i)) & 0x7fffffff;
    }
    return 5000 + (h % 100000);
}

function show(title, text, key) {
    ensureChannel();
    var nm = context.getSystemService(context.NOTIFICATION_SERVICE);
    var builder;
    if (device.sdkInt >= 26) {
        builder = new android.app.Notification.Builder(context, config.NOTIFY_CHANNEL);
    } else {
        builder = new android.app.Notification.Builder(context);
    }
    builder.setContentTitle(String(title))
        .setContentText(String(text))
        .setSmallIcon(android.R.drawable.ic_dialog_alert)
        .setAutoCancel(true);
    nm.notify(idFor(key || title), builder.build());
}

/** Remove a previously shown alert (call on recovery). */
function clear(key) {
    var nm = context.getSystemService(context.NOTIFICATION_SERVICE);
    nm.cancel(idFor(key));
}

module.exports = { show: show, clear: clear };
