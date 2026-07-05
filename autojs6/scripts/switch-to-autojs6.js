/**
 * Switch automation mode to AutoJs6. Run once from AutoJs6 app.
 * After this: disable Tasker + AutoInput accessibility, enable AutoJs6's,
 * disable stayturgid Tasker profiles, then run main.js.
 */
var config = require("../lib/config.js");
var guard = require("../lib/guard.js");
var notify = require("../lib/notify.js");

files.write(config.MODE_FILE, "autojs6\n");

var report = guard.statusReport();
var msg = "Mode → autojs6. Next: disable Tasker+AutoInput a11y, enable AutoJs6 a11y, "
    + "disable stayturgid Tasker profiles, run main.js.";
toast(msg);
notify.show("stayturgid → AutoJs6 mode", msg);
console.log(JSON.stringify(report, null, 2));
