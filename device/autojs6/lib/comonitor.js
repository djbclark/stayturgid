// @generated
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.probeA11y = probeA11y;
exports.probeSshd = probeSshd;
exports.probeShizuku = probeShizuku;
exports.run = run;
// @heals: SSHD-RUNNING PORT5555-OPEN SHIZUKU-HEADLESS A11Y-AUTOJS6
/**
 * AutoJs6 co-monitor — redundant health probes via Shizuku when Termux is
 * stale, hung, or skipped (Fire OS / NO_LOCAL_ADB).
 *
 * Mirrors the Termux stayturgid_repair STATUS surface (sshd, shizuku, a11y,
 * shell/5555, wifi) using AutoJs6's privileged shizuku() API, which still
 * works when Termux cannot reach localhost:5555.
 *
 * Does NOT replace Termux-primary repair when the boot loop is healthy.
 */
const config = require("./config.js");
const log = require("./log.js");
const notify = require("./notify.js");
const shizukuShell = require("./shizuku_shell.js");
const repair = require("./repair.js");
const A11Y_SVC = config.AUTOJS6_A11Y;
function sh(cmd) {
  const r = shizukuShell.exec(cmd);
  return { code: r.code, result: r.result.replace(/\r/g, "").trim() };
}
// Notify at most once per engine process that a11y looks sticky (Settings ON,
// auto.service null) — a module-level flag replaces the original's
// probeA11y._stickyLogged function-property hack.
let stickyA11yLogged = false;
function probeA11y(split) {
  // Prefer live bind (auto.service). Settings-list alone false-positives sticky ON.
  try {
    if (typeof auto !== "undefined" && auto.service) {
      notify.clear("a11y-blocked");
      notify.clear("a11y-stale");
      return "up";
    }
  } catch (_a) {
    /* fall through */
  }
  const r = sh("settings get secure enabled_accessibility_services");
  const list = r.result.trim();
  const listed = Boolean(list && list !== "null" && list.indexOf(A11Y_SVC) >= 0);
  // Sticky candidate: Settings ON but auto.service null. On some builds/devices
  // auto.service flickers null even while the engine is mid-cycle and listed
  // (s24 noise after debug APK). Treat as degraded, not hard FAILED, and notify
  // at most once per engine process so STATUS stays operational for health scrapes.
  if (listed && typeof auto !== "undefined") {
    try {
      if (!auto.service) {
        if (!stickyA11yLogged) {
          stickyA11yLogged = true;
          log.append("[comonitor] A11Y STICKY candidate — listed ON but auto.service null (notify once; not FAILED)");
          notify.show(
            "AutoJs6 accessibility may be sticky",
            "If Task is empty or UI automations fail: Settings → Accessibility → AutoJs6 OFF then ON, then re-run main.js.",
            "a11y-stale",
          );
        }
        return "degraded";
      }
    } catch (_b) {
      /* fall through */
    }
  }
  if (listed) {
    // Outside AutoJs6 engine context: cannot confirm bind; treat listed as up.
    return "up";
  }
  if (split && !shizukuShell.isOperational()) {
    return "unknown";
  }
  // Detection only — no automatic repair (policy G3: never settings put a11y).
  log.append("[comonitor] A11Y OFF — AutoJs6 accessibility disabled; re-enable in Settings");
  notify.show(
    "AutoJs6 accessibility disabled",
    "Open Settings > Accessibility > AutoJs6: if already ON, turn OFF then ON again.",
    "a11y-blocked",
  );
  return "down";
}
function probeSshd() {
  const r = sh("pgrep -x sshd >/dev/null 2>&1 || pgrep -f '[s]shd' >/dev/null 2>&1");
  return r.code === 0 ? "up" : "down";
}
function restartSshd() {
  // Remove stale runit down file that silently blocks sshd from starting.
  sh("rm -f /data/data/com.termux/files/usr/var/service/sshd/down 2>/dev/null; true");
  sh(
    "export PATH=/data/data/com.termux/files/usr/bin:$PATH; " +
      "pgrep -x sshd >/dev/null 2>&1 || " +
      "/data/data/com.termux/files/usr/bin/sshd || true",
  );
  sleep(1500);
  return probeSshd();
}
function probeShizuku() {
  if (shizukuShell.isOperational()) return "up";
  const r = sh("am broadcast -a moe.shizuku.privileged.api.HEADLESS_STATUS 2>/dev/null");
  if (r.code === 0 && r.result.indexOf("result=1") >= 0) return "up";
  // Samsung freezes the Java receiver; fall back to pgrep.
  const p = sh("pgrep -f '[s]hizuku_server' >/dev/null 2>&1");
  if (p.code === 0) return "up";
  return "down";
}
function probeShell5555(split, termuxStatus) {
  if (split) return { port: "skip", shell: "no" };
  // Prefer fresh Termux STATUS — AutoJs6 shizuku() often lacks a working
  // `adb` binary/PATH, so a live adb probe false-fires CLOSED_NO_SHELL.
  if (termuxStatus && termuxStatus.port) {
    const p = termuxStatus.port;
    if (p === "open") return { port: "open", shell: "yes" };
    if (p === "skip") return { port: "skip", shell: "no" };
    if (p === "CLOSED_NO_SHELL") return { port: "CLOSED_NO_SHELL", shell: "no" };
  }
  // Live listen check (no adb client required).
  const nc = sh("toybox nc -z 127.0.0.1 5555 >/dev/null 2>&1 || nc -z 127.0.0.1 5555 >/dev/null 2>&1");
  if (nc.code === 0) return { port: "open", shell: "yes" };
  // Shizuku API up ⇒ privileged shell available even if adbd TCP is odd.
  if (shizukuShell.isOperational()) {
    return { port: "open", shell: "yes" };
  }
  return { port: "CLOSED_NO_SHELL", shell: "no" };
}
function probeWifi(split, shellProbe) {
  if (split) return "skip";
  const r = sh("settings get global adb_wifi_enabled");
  const v = r.result.trim();
  if (v === "1" || v === "true") return "up";
  // Samsung: adb_wifi_enabled reads 0 but port 5555 works (Shizuku opens it).
  // Pixel Android 16: settings put blocked on this key. If shell works, skip write.
  if (shellProbe.port === "open") return "up";
  sh("settings put global adb_wifi_enabled 1");
  sleep(1000);
  const r2 = sh("settings get global adb_wifi_enabled");
  const v2 = r2.result.trim();
  if (v2 === "1" || v2 === "true") return "repaired";
  return "FAILED";
}
/** Run co-monitor probes. Returns a STATUS-like object, or null when deferred. */
function run(profile, opts) {
  const resolvedProfile = profile || config.detectDeviceProfile();
  const split = config.splitStorage(resolvedProfile);
  const reason =
    (opts === null || opts === void 0 ? void 0 : opts.reason) || (split ? "split-storage" : "termux-stale");
  if (
    !(opts === null || opts === void 0 ? void 0 : opts.force) &&
    !log.isRepairLoopStale() &&
    !config.splitStorage(resolvedProfile)
  ) {
    // Callers normally pass force=true (periodic fleet parity). Keep the
    // defer path for unit tests / ad-hoc imports.
    return null;
  }
  log.append("[comonitor] start reason=" + reason + " shizuku_api=" + (shizukuShell.isOperational() ? "yes" : "no"));
  let sshd = probeSshd();
  // Shizuku pgrep is unreliable when the AutoJs6↔Shizuku binder is broken
  // (s24 "Unable to use Shizuku service") or on Fire split-storage. Prefer a
  // fresh Termux STATUS before restarting or notifying.
  if (sshd === "down" && !log.isRepairLoopStale()) {
    const earlyTrust = log.latestRepairStatus();
    if (earlyTrust && earlyTrust.sshd === "up") {
      log.append("[comonitor] trusting fresh [repair] sshd=up over shizuku pgrep");
      sshd = "up";
    }
  }
  if (sshd === "down" && !split) {
    log.append("[comonitor] sshd down — restarting via shizuku/shell");
    sshd = restartSshd();
    if (sshd === "up") sshd = "restarted";
  } else if (sshd === "down" && split) {
    log.append("[comonitor] sshd probe down on split-storage — leave to Termux (no shizuku restart)");
  }
  let shizukuStatus = probeShizuku();
  let termuxStatus = null;
  try {
    if (!log.isRepairLoopStale()) {
      termuxStatus = log.latestRepairStatus();
    }
  } catch (_a) {
    /* best effort */
  }
  let shellProbe = probeShell5555(split, termuxStatus);
  const wifi = probeWifi(split, shellProbe);
  const a11y = probeA11y(split);
  // Trust fresh Termux [repair] port=open over a flaky nc/adb probe.
  if (!split && shellProbe.port === "CLOSED_NO_SHELL" && !log.isRepairLoopStale()) {
    const trust = log.latestRepairStatus();
    if (trust && trust.port === "open") {
      shellProbe = { port: "open", shell: trust.shell === "no" ? "no" : "yes" };
      log.append("[comonitor] trusting fresh [repair] port=open over shell probe");
    }
  }
  // Catastrophic: no shell on stock Android, or Shizuku dead on phones that
  // expect privileged shell. Only escalate CLOSED_NO_SHELL when Termux is also
  // stale/unknown — avoid fighting a healthy Termux repair with UI taps every 20 min.
  //
  // Fire OS / split-storage: Termux cannot drive Shizuku the same way; co-monitor
  // used to call repairCatastrophic every cycle → "shizuku headless start failed"
  // + Mac "excessive catastrophic" spam while sshd was fine via Termux.
  if (!split && shellProbe.port === "CLOSED_NO_SHELL" && log.isRepairLoopStale()) {
    log.append("[comonitor] CLOSED_NO_SHELL — catastrophic repair");
    notify.show(
      "⚠ ADB 5555 down — co-monitor repairing",
      "Termux repair stale/hung; AutoJs6 co-monitor running Shizuku repair.",
      "adb5555",
    );
    try {
      repair.repairCatastrophic(resolvedProfile);
    } catch (e) {
      log.append("[comonitor] catastrophic error: " + e);
    }
    shellProbe = probeShell5555(false, null);
    shizukuStatus = probeShizuku();
  } else if (shizukuStatus === "down" && !split && resolvedProfile.privilegedShellExpected !== false) {
    log.append("[comonitor] shizuku_server down — catastrophic Start path");
    try {
      repair.repairCatastrophic(resolvedProfile);
    } catch (e) {
      log.append("[comonitor] shizuku start error: " + e);
    }
    shizukuStatus = probeShizuku();
  } else if (shizukuStatus === "down" && (split || resolvedProfile.privilegedShellExpected === false)) {
    log.append("[comonitor] shizuku down — skip catastrophic on split/no-privileged-shell host (Termux is primary)");
  }
  // Trust fresh Termux [repair] sshd=up over a flaky shizuku pgrep (s24 spam).
  if (sshd === "down" && !log.isRepairLoopStale()) {
    const trustSsh = log.latestRepairStatus();
    if (trustSsh && trustSsh.sshd === "up") {
      log.append("[comonitor] trusting fresh [repair] sshd=up over shizuku pgrep");
      sshd = "up";
    }
  }
  if (sshd === "down") {
    notify.show(
      "⚠ SSH daemon down (co-monitor)",
      "sshd still down after AutoJs6 restart attempt — check Termux.",
      "sshd",
    );
  } else {
    notify.clear("sshd");
  }
  if (a11y === "up" || a11y === "degraded") {
    // degraded = sticky candidate already notified once under a11y-stale
    notify.clear("a11y-blocked");
    if (a11y === "up") {
      notify.clear("a11y-stale");
    }
  }
  if (shellProbe.port === "open" || shellProbe.port === "skip") {
    notify.clear("adb5555");
  }
  const status =
    "STATUS port=" +
    shellProbe.port +
    " shizuku=" +
    shizukuStatus +
    " sshd=" +
    sshd +
    " a11y=" +
    a11y +
    " shell=" +
    shellProbe.shell +
    " wifi=" +
    wifi;
  log.append("[comonitor] " + status + " reason=" + reason);
  // Persist status to shared state.json so latestRepairStatus() can do an O(1) read.
  try {
    log.writeState("comonitor", {
      port: shellProbe.port,
      shizuku: shizukuStatus,
      sshd,
      a11y,
      shell: shellProbe.shell,
      wifi,
      reason,
    });
  } catch (_b) {
    /* best effort — state.json write failure must not break comonitor */
  }
  return {
    port: shellProbe.port,
    shizuku: shizukuStatus,
    sshd,
    a11y,
    shell: shellProbe.shell,
    wifi,
    reason,
  };
}
