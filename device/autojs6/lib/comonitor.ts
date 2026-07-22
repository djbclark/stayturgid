// Rhino gotchas (redeclaration collisions, for...of, exports stamp, Java-string coercion): see docs/architecture/components/autojs6.md "Rhino JS-engine gotchas" before editing.
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
import comonitorConfig = require("./config.js");
import comonitorLog = require("./log.js");
import comonitorNotify = require("./notify.js");
import comonitorShizukuShell = require("./shizuku_shell.js");
import comonitorRepair = require("./repair.js");

import type { DeviceProfile } from "./config.js";

const A11Y_SVC = comonitorConfig.AUTOJS6_A11Y;

type SshdStatus = "up" | "down" | "restarted";
type ShizukuStatus = "up" | "down";
/** unknown = split-storage without Shizuku operational (cannot probe). */
type A11yStatus = "up" | "down" | "degraded" | "unknown";
type PortStatus = "open" | "skip" | "CLOSED_NO_SHELL";
type ShellFlag = "yes" | "no";
type WifiStatus = "up" | "repaired" | "FAILED" | "skip";

export interface ComonitorStatus {
  port: PortStatus;
  shizuku: ShizukuStatus;
  sshd: SshdStatus;
  a11y: A11yStatus;
  shell: ShellFlag;
  wifi: WifiStatus;
  reason: string;
}

export interface ComonitorOptions {
  force?: boolean;
  reason?: string;
}

function sh(cmd: string): ShellResult {
  const r = comonitorShizukuShell.exec(cmd);
  return { code: r.code, result: r.result.replace(/\r/g, "").trim() };
}

// Notify at most once per engine process that a11y looks sticky (Settings ON,
// auto.service null) — a module-level flag replaces the original's
// probeA11y._stickyLogged function-property hack.
let stickyA11yLogged = false;

export function probeA11y(split: boolean): A11yStatus {
  // Prefer live bind (auto.service). Settings-list alone false-positives sticky ON.
  try {
    if (typeof auto !== "undefined" && auto.service) {
      comonitorNotify.clear("a11y-blocked");
      comonitorNotify.clear("a11y-stale");
      return "up";
    }
  } catch {
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
          comonitorLog.append(
            "[comonitor] A11Y STICKY candidate — listed ON but auto.service null (notify once; not FAILED)",
          );
          comonitorNotify.show(
            "AutoJs6 accessibility may be sticky",
            "If Task is empty or UI automations fail: Settings → Accessibility → AutoJs6 OFF then ON, then re-run main.js.",
            "a11y-stale",
          );
        }
        return "degraded";
      }
    } catch {
      /* fall through */
    }
  }

  if (listed) {
    // Outside AutoJs6 engine context: cannot confirm bind; treat listed as up.
    return "up";
  }
  if (split && !comonitorShizukuShell.isOperational()) {
    return "unknown";
  }

  // Detection only — no automatic repair (policy G3: never settings put a11y).
  comonitorLog.append("[comonitor] A11Y OFF — AutoJs6 accessibility disabled; re-enable in Settings");
  comonitorNotify.show(
    "AutoJs6 accessibility disabled",
    "Open Settings > Accessibility > AutoJs6: if already ON, turn OFF then ON again.",
    "a11y-blocked",
  );
  return "down";
}

export function probeSshd(): "up" | "down" {
  const r = sh("pgrep -x sshd >/dev/null 2>&1 || pgrep -f '[s]shd' >/dev/null 2>&1");
  return r.code === 0 ? "up" : "down";
}

function restartSshd(): "up" | "down" {
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

export function probeShizuku(): ShizukuStatus {
  if (comonitorShizukuShell.isOperational()) return "up";
  const r = sh("am broadcast -a moe.shizuku.privileged.api.HEADLESS_STATUS 2>/dev/null");
  if (r.code === 0 && r.result.indexOf("result=1") >= 0) return "up";
  // Samsung freezes the Java receiver; fall back to pgrep.
  const p = sh("pgrep -f '[s]hizuku_server' >/dev/null 2>&1");
  if (p.code === 0) return "up";
  return "down";
}

interface ShellProbe {
  port: PortStatus;
  shell: ShellFlag;
}

function probeShell5555(split: boolean, termuxStatus: comonitorLog.RepairStatus | null): ShellProbe {
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
  if (comonitorShizukuShell.isOperational()) {
    return { port: "open", shell: "yes" };
  }
  return { port: "CLOSED_NO_SHELL", shell: "no" };
}

function probeWifi(split: boolean, shellProbe: ShellProbe): WifiStatus {
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
export function run(profile: DeviceProfile, opts?: ComonitorOptions): ComonitorStatus | null {
  const resolvedProfile = profile || comonitorConfig.detectDeviceProfile();
  const split = comonitorConfig.splitStorage(resolvedProfile);
  const reason = opts?.reason || (split ? "split-storage" : "termux-stale");

  if (!opts?.force && !comonitorLog.isRepairLoopStale() && !comonitorConfig.splitStorage(resolvedProfile)) {
    // Callers normally pass force=true (periodic fleet parity). Keep the
    // defer path for unit tests / ad-hoc imports.
    return null;
  }

  comonitorLog.append(
    "[comonitor] start reason=" + reason + " shizuku_api=" + (comonitorShizukuShell.isOperational() ? "yes" : "no"),
  );

  let sshd: SshdStatus = probeSshd();
  // Shizuku pgrep is unreliable when the AutoJs6↔Shizuku binder is broken
  // (s24 "Unable to use Shizuku service") or on Fire split-storage. Prefer a
  // fresh Termux STATUS before restarting or notifying.
  if (sshd === "down" && !comonitorLog.isRepairLoopStale()) {
    const earlyTrust = comonitorLog.latestRepairStatus();
    if (earlyTrust && earlyTrust.sshd === "up") {
      comonitorLog.append("[comonitor] trusting fresh [repair] sshd=up over shizuku pgrep");
      sshd = "up";
    }
  }
  if (sshd === "down" && !split) {
    comonitorLog.append("[comonitor] sshd down — restarting via shizuku/shell");
    sshd = restartSshd();
    if (sshd === "up") sshd = "restarted";
  } else if (sshd === "down" && split) {
    comonitorLog.append("[comonitor] sshd probe down on split-storage — leave to Termux (no shizuku restart)");
  }

  let shizukuStatus = probeShizuku();
  let termuxStatus: comonitorLog.RepairStatus | null = null;
  try {
    if (!comonitorLog.isRepairLoopStale()) {
      termuxStatus = comonitorLog.latestRepairStatus();
    }
  } catch {
    /* best effort */
  }
  let shellProbe = probeShell5555(split, termuxStatus);
  const wifi = probeWifi(split, shellProbe);
  const a11y = probeA11y(split);

  // Trust fresh Termux [repair] port=open over a flaky nc/adb probe.
  if (!split && shellProbe.port === "CLOSED_NO_SHELL" && !comonitorLog.isRepairLoopStale()) {
    const trust = comonitorLog.latestRepairStatus();
    if (trust && trust.port === "open") {
      shellProbe = { port: "open", shell: trust.shell === "no" ? "no" : "yes" };
      comonitorLog.append("[comonitor] trusting fresh [repair] port=open over shell probe");
    }
  }

  // Catastrophic: no shell on stock Android, or Shizuku dead on phones that
  // expect privileged shell. Only escalate CLOSED_NO_SHELL when Termux is also
  // stale/unknown — avoid fighting a healthy Termux repair with UI taps every 20 min.
  //
  // Fire OS / split-storage: Termux cannot drive Shizuku the same way; co-monitor
  // used to call repairCatastrophic every cycle → "shizuku headless start failed"
  // + Mac "excessive catastrophic" spam while sshd was fine via Termux.
  if (!split && shellProbe.port === "CLOSED_NO_SHELL" && comonitorLog.isRepairLoopStale()) {
    comonitorLog.append("[comonitor] CLOSED_NO_SHELL — catastrophic repair");
    comonitorNotify.show(
      "⚠ ADB 5555 down — co-monitor repairing",
      "Termux repair stale/hung; AutoJs6 co-monitor running Shizuku repair.",
      "adb5555",
    );
    try {
      comonitorRepair.repairCatastrophic(resolvedProfile);
    } catch (e) {
      comonitorLog.append("[comonitor] catastrophic error: " + e);
    }
    shellProbe = probeShell5555(false, null);
    shizukuStatus = probeShizuku();
  } else if (shizukuStatus === "down" && !split && resolvedProfile.privilegedShellExpected !== false) {
    comonitorLog.append("[comonitor] shizuku_server down — catastrophic Start path");
    try {
      comonitorRepair.repairCatastrophic(resolvedProfile);
    } catch (e) {
      comonitorLog.append("[comonitor] shizuku start error: " + e);
    }
    shizukuStatus = probeShizuku();
  } else if (shizukuStatus === "down" && (split || resolvedProfile.privilegedShellExpected === false)) {
    comonitorLog.append(
      "[comonitor] shizuku down — skip catastrophic on split/no-privileged-shell host (Termux is primary)",
    );
  }

  // Trust fresh Termux [repair] sshd=up over a flaky shizuku pgrep (s24 spam).
  if (sshd === "down" && !comonitorLog.isRepairLoopStale()) {
    const trustSsh = comonitorLog.latestRepairStatus();
    if (trustSsh && trustSsh.sshd === "up") {
      comonitorLog.append("[comonitor] trusting fresh [repair] sshd=up over shizuku pgrep");
      sshd = "up";
    }
  }

  if (sshd === "down") {
    comonitorNotify.show(
      "⚠ SSH daemon down (co-monitor)",
      "sshd still down after AutoJs6 restart attempt — check Termux.",
      "sshd",
    );
  } else {
    comonitorNotify.clear("sshd");
  }

  if (a11y === "up" || a11y === "degraded") {
    // degraded = sticky candidate already notified once under a11y-stale
    comonitorNotify.clear("a11y-blocked");
    if (a11y === "up") {
      comonitorNotify.clear("a11y-stale");
    }
  }

  if (shellProbe.port === "open" || shellProbe.port === "skip") {
    comonitorNotify.clear("adb5555");
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
  comonitorLog.append("[comonitor] " + status + " reason=" + reason);
  // Persist status to shared state.json so latestRepairStatus() can do an O(1) read.
  try {
    comonitorLog.writeState("comonitor", {
      port: shellProbe.port,
      shizuku: shizukuStatus,
      sshd,
      a11y,
      shell: shellProbe.shell,
      wifi,
      reason,
    });
  } catch {
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
