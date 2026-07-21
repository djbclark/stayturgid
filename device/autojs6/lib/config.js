// @generated
"use strict";
/** Shared constants and device profile resolution.
 *
 * The device profile is DATA, not code: Ansible renders
 * /sdcard/stayturgid/state/device.json from the inventory taxonomy
 * (ansible/inventory/hosts.yml + group_vars layers). Nothing in this repo's
 * code names a specific device; without the JSON a generic profile applies
 * (no tap-coordinate fallback, no self-ping — degraded but functional).
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.PROFILE_DEFAULTS =
  exports.AUTOJS6_A11Y =
  exports.NOTIFY_CHANNEL =
  exports.STALE_REPAIR_MS =
  exports.INTERVAL_MS =
  exports.REPAIR_SCRIPT =
  exports.WATCHDOG_LOG =
  exports.DEVICE_JSON =
  exports.ENV_FILE =
  exports.TERMUX_HOME =
  exports.SD_ROOT =
    void 0;
exports.resolveSdRoot = resolveSdRoot;
exports.pathsFor = pathsFor;
exports.parentDir = parentDir;
exports.ensureParentDir = ensureParentDir;
exports.splitStorage = splitStorage;
exports.ensureDirs = ensureDirs;
exports.detectDeviceProfile = detectDeviceProfile;
// Single stayturgid root per filesystem. SD_ROOT is created by the ensureDirs()
// call below so a user-deleted directory self-heals before we read/write.
exports.SD_ROOT = "/sdcard/stayturgid";
exports.TERMUX_HOME = "/data/data/com.termux/files/home";
exports.ENV_FILE = exports.TERMUX_HOME + "/.stayturgid/env";
exports.DEVICE_JSON = exports.SD_ROOT + "/state/device.json";
exports.WATCHDOG_LOG = exports.SD_ROOT + "/logs/watchdog.log";
exports.REPAIR_SCRIPT = exports.TERMUX_HOME + "/.stayturgid/bin/stayturgid_repair.py";
/** Resolve shared-storage root (Fire OS uses ~/.stayturgid/shared). */
function resolveSdRoot() {
  try {
    if (files.exists(exports.ENV_FILE)) {
      const m = String(files.read(exports.ENV_FILE)).match(/STAYTURGID_SD="([^"]+)"/);
      if (m && m[1]) return m[1];
    }
  } catch (_a) {
    /* best effort */
  }
  return exports.SD_ROOT;
}
function pathsFor(profile) {
  const termuxRoot = profile && profile.sdRoot ? profile.sdRoot : resolveSdRoot();
  let root = termuxRoot;
  // AutoJs6 cannot write Termux-private paths (Fire OS shared-storage workaround).
  if (root.indexOf(exports.TERMUX_HOME) === 0) {
    root = exports.SD_ROOT;
  }
  return {
    sdRoot: root,
    termuxSdRoot: termuxRoot,
    deviceJson: root + "/state/device.json",
    watchdogLog: root + "/logs/watchdog.log",
    watchdogJsonl: root + "/logs/watchdog.jsonl",
    watchdogState: root + "/run/state.json",
    watchdogStamp: root + "/run/watchdog.last",
    triggerFile: root + "/run/repair_now",
  };
}
/** Return the directory portion of a file path without relying on AutoJs6 APIs. */
function parentDir(filePath) {
  let path = filePath;
  while (path.length > 1 && path.charAt(path.length - 1) === "/") {
    path = path.substring(0, path.length - 1);
  }
  const slash = path.lastIndexOf("/");
  if (slash < 0) return ".";
  if (slash === 0) return "/";
  return path.substring(0, slash);
}
/** Ensure the parent directory of a file exists, including deleted run/state dirs. */
function ensureParentDir(filePath) {
  const dir = parentDir(filePath);
  files.ensureDir(dir === "/" ? dir : dir + "/");
  return dir;
}
/** Fire OS: Termux state/logs live under private home; AutoJs6 uses /sdcard only. */
function splitStorage(profile) {
  const root = profile && profile.sdRoot ? profile.sdRoot : resolveSdRoot();
  return root.indexOf(exports.TERMUX_HOME) === 0;
}
/** mkdir -p the shared-storage subdirs the watchdog writes (self-healing). */
function ensureDirs(profile) {
  const root = pathsFor(profile || {}).sdRoot;
  for (const d of ["state", "logs", "run", "tmp"]) {
    try {
      files.ensureDir(root + "/" + d + "/");
    } catch (_a) {
      /* best effort */
    }
  }
}
exports.INTERVAL_MS = 20 * 60 * 1000;
exports.STALE_REPAIR_MS = 15 * 60 * 1000;
exports.NOTIFY_CHANNEL = "stayturgid";
exports.AUTOJS6_A11Y = "org.autojs.autojs6/org.autojs.autojs.core.accessibility.AccessibilityServiceUsher";
exports.PROFILE_DEFAULTS = {
  id: "generic",
  label: "unknown device",
  notifyTag: "",
  shizukuPackage: "moe.shizuku.privileged.api",
  shizukuActivity: "moe.shizuku.manager.MainActivity",
  shizukuStartCoords: null,
  tailscaleIp: null,
  tailscaleEnabled: true,
  tailscalePackage: "com.tailscale.ipn",
  tailscaleActivity: "com.tailscale.ipn.MainActivity",
  wirelessDebugUiFallback: false,
};
function readDeviceJson() {
  const candidates = [
    "/sdcard/stayturgid/state/device.json",
    exports.DEVICE_JSON,
    exports.TERMUX_HOME + "/.stayturgid/shared/state/device.json",
  ];
  for (const candidate of candidates) {
    try {
      if (files.exists(candidate)) {
        const parsed = JSON.parse(String(files.read(candidate)));
        return { profile: parsed || {}, source: candidate };
      }
    } catch (e) {
      console.warn("[stayturgid] unreadable " + candidate + ": " + e);
    }
  }
  return { profile: {}, source: "" };
}
function detectDeviceProfile() {
  const { profile, source } = readDeviceJson();
  const use = (key) => {
    const value = profile[key];
    return value !== undefined && value !== null ? value : exports.PROFILE_DEFAULTS[key];
  };
  const merged = {
    id: use("id"),
    label: use("label"),
    notifyTag: use("notifyTag"),
    shizukuPackage: use("shizukuPackage"),
    shizukuActivity: use("shizukuActivity"),
    shizukuStartCoords: use("shizukuStartCoords"),
    tailscaleIp: use("tailscaleIp"),
    tailscaleEnabled: use("tailscaleEnabled"),
    tailscalePackage: use("tailscalePackage"),
    tailscaleActivity: use("tailscaleActivity"),
    wirelessDebugUiFallback: use("wirelessDebugUiFallback"),
    samsungWirelessDebugFallback: false, // set below
    usingGenericDefaults: false, // set below
  };
  if (profile.sdRoot) {
    merged.sdRoot = profile.sdRoot;
  }
  // NOTE: device.json's privilegedShellExpected is intentionally not copied
  // here — this mirrors pre-existing behavior (only sdRoot ever got this
  // post-loop treatment), so comonitor.ts's `profile.privilegedShellExpected`
  // read is always undefined today. Preserved as-is; not this rewrite's call
  // to fix silently.
  merged.usingGenericDefaults = !source || !profile.id;
  if (merged.usingGenericDefaults) {
    console.warn(
      "[stayturgid] device.json missing or incomplete — run Ansible fleet deploy; device=generic (no tap coords)",
    );
  }
  // legacy field name kept for shizuku.js compatibility
  merged.samsungWirelessDebugFallback = merged.wirelessDebugUiFallback;
  return merged;
}
