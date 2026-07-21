// @generated
"use strict";
// @ts-nocheck
// @heals: A11Y-AUTOJS6
var config = require("./config.js");
var notify = require("./notify.js");
var termux = require("./termux.js");
var log = require("./log.js");
// Authoritative, permission-free check: AutoJs6's own accessibility service
// instance is non-null exactly when the service is enabled AND bound.
//
// Important: when `auto` exists but `auto.service` is null, do NOT fall back to
// `settings get secure enabled_accessibility_services`. Android can leave the
// component listed (Settings switch ON) while the service is not bound — the
// sticky/malfunctioning state. Trusting the settings list false-positives "up"
// and skips the user OFF→ON notification.
function autoJs6AccessibilityEnabled() {
  try {
    if (typeof auto !== "undefined") {
      if (auto.service) return true;
      // Engine present: bound service is the only truth. Settings-list fallback
      // would hide sticky ON (enabled but not running).
      return false;
    }
  } catch (e) {
    /* fall through to the settings probe only when `auto` is unavailable */
  }
  // Fallback (best effort): if a privileged read happens to work, use it.
  // Run in a thread with a timeout to avoid blocking the watchdog cycle
  // if the settings daemon hangs (observed on Fire OS).
  try {
    var shellResult = { code: -1, result: "" };
    var t = threads.start(function () {
      try {
        var r = shell("settings get secure enabled_accessibility_services", false);
        shellResult.code = r.code;
        shellResult.result = String(r.result || "");
      } catch (e) {
        /* thread-local failure */
      }
    });
    t.join(5000);
    if (shellResult.code === 0) {
      var list = shellResult.result.trim();
      return list && list !== "null" && list.indexOf(config.AUTOJS6_A11Y) >= 0;
    }
  } catch (e2) {
    /* ignore */
  }
  return false;
}
/** True when Settings lists AutoJs6 but `auto.service` is not bound (sticky). */
function isMalfunctioning() {
  try {
    if (typeof auto === "undefined" || auto.service) return false;
  } catch (e) {
    return false;
  }
  try {
    var shellResult = { code: -1, result: "" };
    var t = threads.start(function () {
      try {
        var r = shell("settings get secure enabled_accessibility_services", false);
        shellResult.code = r.code;
        shellResult.result = String(r.result || "");
      } catch (e) {
        /* ignore */
      }
    });
    t.join(5000);
    if (shellResult.code !== 0) return false;
    var list = shellResult.result.trim();
    return !!(list && list !== "null" && list.indexOf(config.AUTOJS6_A11Y) >= 0);
  } catch (e2) {
    return false;
  }
}
var A11Y_TOGGLE_MSG =
  "Open Settings > Accessibility > AutoJs6: if already ON, turn OFF then ON again. " +
  "sshd/Tailscale self-heal still runs without a11y.";
/**
 * Best-effort accessibility check for the watchdog — DEGRADES, never blocks.
 *
 * When accessibility is off or sticky: on split-storage, co-monitor probes via
 * Shizuku. On normal hosts, invokes Termux repair to check status. The watchdog
 * cycle always proceeds (sshd/Tailscale/comonitor still run without a11y).
 *
 * Never `settings put` accessibility automatically (policy G3). User must
 * enable or cycle AutoJs6 in Settings. AutoJs6 fork may rebind via privileged
 * restartService when WRITE_SECURE_SETTINGS is granted.
 */
function enforce(profile) {
  profile = profile || config.detectDeviceProfile();
  if (autoJs6AccessibilityEnabled()) {
    notify.clear("a11y-blocked");
    notify.clear("a11y-stale");
    return;
  }
  var sticky = isMalfunctioning();
  if (sticky) {
    log.append("[watchdog] accessibility STICKY (Settings ON, service not bound) — user must toggle OFF then ON");
  }
  if (config.splitStorage(profile)) {
    log.append("[watchdog] split-storage: a11y off/sticky — co-monitor will probe via Shizuku");
    try {
      var comonitor = require("./comonitor.js");
      comonitor.run(profile, { force: true, reason: sticky ? "a11y-sticky-split" : "a11y-off-split" });
    } catch (e) {
      log.append("[watchdog] comonitor a11y attempt failed: " + e);
    }
    if (autoJs6AccessibilityEnabled()) {
      notify.clear("a11y-blocked");
      notify.clear("a11y-stale");
      return;
    }
  } else {
    log.append(
      sticky
        ? "[watchdog] accessibility sticky — checking repair status"
        : "[watchdog] accessibility disabled — checking repair status",
    );
    // Check if Termux repair already detected and logged this.
    termux.invokeRepair(profile);
    var deadline = Date.now() + 20000;
    while (Date.now() < deadline && !autoJs6AccessibilityEnabled()) {
      sleep(2000);
    }
    if (autoJs6AccessibilityEnabled()) {
      log.append("[watchdog] accessibility restored by user");
      notify.clear("a11y-blocked");
      notify.clear("a11y-stale");
      return;
    }
  }
  // Still off or sticky — user must enable / cycle manually.
  if (sticky) {
    log.append("[watchdog] accessibility still sticky — user must toggle OFF then ON");
    notify.show("AutoJs6 accessibility stuck (ON but not bound)", A11Y_TOGGLE_MSG, "a11y-stale");
  } else {
    log.append("[watchdog] accessibility still off — user must re-enable in Settings");
    notify.show("AutoJs6 accessibility disabled", A11Y_TOGGLE_MSG, "a11y-blocked");
  }
}
function statusReport() {
  return {
    autojs6A11y: autoJs6AccessibilityEnabled(),
    autojs6A11yMalfunctioning: isMalfunctioning(),
  };
}
module.exports = {
  enforce: enforce,
  statusReport: statusReport,
  autoJs6AccessibilityEnabled: autoJs6AccessibilityEnabled,
  isMalfunctioning: isMalfunctioning,
};
