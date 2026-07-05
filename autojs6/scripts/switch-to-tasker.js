/**
 * Switch automation mode back to Tasker+AutoInput. Run once from AutoJs6 app
 * (or push mode file via adb). Stop the stayturgid main.js script first.
 */
var config = require("../lib/config.js");
var guard = require("../lib/guard.js");
var notify = require("../lib/notify.js");

files.write(config.MODE_FILE, "tasker\n");

var msg = "Mode → tasker. Stop this AutoJs6 script, re-enable Tasker+AutoInput "
    + "accessibility, disable AutoJs6 a11y, re-enable stayturgid Tasker profiles.";
toast(msg);
notify.show("stayturgid → Tasker mode", msg);
console.log(JSON.stringify(guard.statusReport(), null, 2));
exit();
