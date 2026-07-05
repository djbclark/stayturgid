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

function show(title, text) {
    ensureChannel();
    importClass(android.app.NotificationManager);
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
    var id = Math.floor(Math.random() * 100000) + 5000;
    nm.notify(id, builder.build());
}

module.exports = { show: show };
