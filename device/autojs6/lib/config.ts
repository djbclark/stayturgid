/** Shared constants and device profile resolution.
 *
 * The device profile is DATA, not code: Ansible renders
 * /sdcard/stayturgid/state/device.json from the inventory taxonomy
 * (ansible/inventory/hosts.yml + group_vars layers). Nothing in this repo's
 * code names a specific device; without the JSON a generic profile applies
 * (no tap-coordinate fallback, no self-ping — degraded but functional).
 */

/** A resolved device profile: PROFILE_DEFAULTS merged with device.json, if present. */
export interface DeviceProfile {
  id: string;
  label: string;
  notifyTag: string;
  shizukuPackage: string;
  shizukuActivity: string;
  shizukuStartCoords: unknown;
  tailscaleIp: string | null;
  tailscaleEnabled: boolean;
  tailscalePackage: string;
  tailscaleActivity: string;
  wirelessDebugUiFallback: boolean;
  /** Legacy field name kept for shizuku.js compatibility; mirrors wirelessDebugUiFallback. */
  samsungWirelessDebugFallback: boolean;
  /** True when device.json expects a privileged (Shizuku) shell; absent means "assume yes". */
  privilegedShellExpected?: boolean;
  /** Present only when device.json overrides the shared-storage root (Fire OS). */
  sdRoot?: string;
  usingGenericDefaults: boolean;
}

/** Shared-storage paths derived from a DeviceProfile, resolved once per cycle. */
export interface DevicePaths {
  sdRoot: string;
  termuxSdRoot: string;
  deviceJson: string;
  watchdogLog: string;
  watchdogJsonl: string;
  watchdogState: string;
  watchdogStamp: string;
  triggerFile: string;
}

// Single stayturgid root per filesystem. SD_ROOT is created by the ensureDirs()
// call below so a user-deleted directory self-heals before we read/write.
export const SD_ROOT = "/sdcard/stayturgid";
export const TERMUX_HOME = "/data/data/com.termux/files/home";
export const ENV_FILE = TERMUX_HOME + "/.stayturgid/env";
export const DEVICE_JSON = SD_ROOT + "/state/device.json";
export const WATCHDOG_LOG = SD_ROOT + "/logs/watchdog.log";
export const REPAIR_SCRIPT = TERMUX_HOME + "/.stayturgid/bin/stayturgid_repair.py";

/** Resolve shared-storage root (Fire OS uses ~/.stayturgid/shared). */
export function resolveSdRoot(): string {
  try {
    if (files.exists(ENV_FILE)) {
      const m = String(files.read(ENV_FILE)).match(/STAYTURGID_SD="([^"]+)"/);
      if (m && m[1]) return m[1];
    }
  } catch {
    /* best effort */
  }
  return SD_ROOT;
}

export function pathsFor(profile: Pick<DeviceProfile, "sdRoot"> | null | undefined): DevicePaths {
  const termuxRoot = profile && profile.sdRoot ? profile.sdRoot : resolveSdRoot();
  let root = termuxRoot;
  // AutoJs6 cannot write Termux-private paths (Fire OS shared-storage workaround).
  if (root.indexOf(TERMUX_HOME) === 0) {
    root = SD_ROOT;
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
export function parentDir(filePath: string): string {
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
export function ensureParentDir(filePath: string): string {
  const dir = parentDir(filePath);
  files.ensureDir(dir === "/" ? dir : dir + "/");
  return dir;
}

/** Fire OS: Termux state/logs live under private home; AutoJs6 uses /sdcard only. */
export function splitStorage(profile: Pick<DeviceProfile, "sdRoot"> | null | undefined): boolean {
  const root = profile && profile.sdRoot ? profile.sdRoot : resolveSdRoot();
  return root.indexOf(TERMUX_HOME) === 0;
}

/** mkdir -p the shared-storage subdirs the watchdog writes (self-healing). */
export function ensureDirs(profile?: Pick<DeviceProfile, "sdRoot"> | null): void {
  const root = pathsFor(profile || {}).sdRoot;
  for (const d of ["state", "logs", "run", "tmp"]) {
    try {
      files.ensureDir(root + "/" + d + "/");
    } catch {
      /* best effort */
    }
  }
}

export const INTERVAL_MS = 20 * 60 * 1000;
export const STALE_REPAIR_MS = 15 * 60 * 1000;
export const NOTIFY_CHANNEL = "stayturgid";

export const AUTOJS6_A11Y = "org.autojs.autojs6/org.autojs.autojs.core.accessibility.AccessibilityServiceUsher";

export const PROFILE_DEFAULTS: Omit<DeviceProfile, "usingGenericDefaults" | "samsungWirelessDebugFallback"> = {
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

/** Parsed shape of device.json — a subset of DeviceProfile, all fields optional. */
type DeviceJson = Partial<DeviceProfile>;

function readDeviceJson(): { profile: DeviceJson; source: string } {
  const candidates = [
    "/sdcard/stayturgid/state/device.json",
    DEVICE_JSON,
    TERMUX_HOME + "/.stayturgid/shared/state/device.json",
  ];
  for (const candidate of candidates) {
    try {
      if (files.exists(candidate)) {
        const parsed = JSON.parse(String(files.read(candidate))) as DeviceJson;
        return { profile: parsed || {}, source: candidate };
      }
    } catch (e) {
      console.warn("[stayturgid] unreadable " + candidate + ": " + e);
    }
  }
  return { profile: {}, source: "" };
}

export function detectDeviceProfile(): DeviceProfile {
  const { profile, source } = readDeviceJson();
  const use = <K extends keyof typeof PROFILE_DEFAULTS>(key: K): (typeof PROFILE_DEFAULTS)[K] => {
    const value = profile[key];
    return value !== undefined && value !== null ? value : PROFILE_DEFAULTS[key];
  };

  const merged: DeviceProfile = {
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
