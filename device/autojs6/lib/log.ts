import config = require("./config.js");

import type { DeviceProfile } from "./config.js";

function pad2(n: number): string {
  return (n < 10 ? "0" : "") + n;
}

function pad3(n: number): string {
  return (n < 10 ? "00" : n < 100 ? "0" : "") + n;
}

function ts(): string {
  const d = new Date();
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${months[d.getMonth()]} ${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
}

/** ISO 8601 timestamp for JSONL/OTel schema. */
function tsISO(): string {
  const d = new Date();
  return (
    d.getFullYear() +
    "-" +
    pad2(d.getMonth() + 1) +
    "-" +
    pad2(d.getDate()) +
    "T" +
    pad2(d.getHours()) +
    ":" +
    pad2(d.getMinutes()) +
    ":" +
    pad2(d.getSeconds()) +
    "." +
    pad3(d.getMilliseconds()) +
    "Z"
  );
}

const LOG_KEEP_LINES = 500;
const LOG_TRIM_OVER = 1000;

function trimLogIfNeeded(logPath: string): void {
  try {
    if (!files.exists(logPath)) return;
    const content = String(files.read(logPath));
    const lines = content.split("\n");
    // Drop trailing empty from final newline
    if (lines.length && lines[lines.length - 1] === "") lines.pop();
    if (lines.length <= LOG_TRIM_OVER) return;
    const kept = lines.slice(-LOG_KEEP_LINES);
    files.write(logPath, kept.join("\n") + "\n");
  } catch {
    /* best effort */
  }
}

/**
 * Build a JSONL entry conforming to the universal OTel log schema.
 * Fields: timestamp, level, hostname, tag, pid, tid, message
 */
function buildJsonlEntry(line: string, profile: Pick<DeviceProfile, "id"> | null | undefined): string {
  const hostname = profile && profile.id ? profile.id : "unknown";
  // Extract tag from [tag] pattern at the start of the message if present.
  const tagMatch = line.match(/^\[([^\]]+)\]/);
  const tag = tagMatch ? tagMatch[1] : "watchdog";
  return JSON.stringify({
    timestamp: tsISO(),
    level: "info",
    hostname,
    tag,
    pid: 0,
    tid: 0,
    message: line,
  });
}

export function append(line: string): string {
  const msg = ts() + " " + line;
  console.log(msg);
  try {
    const profile = config.detectDeviceProfile();
    const paths = config.pathsFor(profile);
    const logPath = paths.watchdogLog;
    const logDir = logPath.replace(/\/[^/]+$/, "");
    files.ensureDir(logDir + "/");
    // Dual-write: legacy text format
    files.append(logPath, msg + "\n");
    trimLogIfNeeded(logPath);
    // Dual-write: structured JSONL format
    try {
      files.append(paths.watchdogJsonl, buildJsonlEntry(line, profile) + "\n");
    } catch (je) {
      /* best effort — JSONL write failure must not break legacy logging */
    }
  } catch (e) {
    console.error("log append failed: " + e);
  }
  return msg;
}

/** Namespaced status entry persisted into state.json by writeState(). */
type StateEntry = Record<string, unknown> & { timestamp: string };

/** state.json's shape: one entry per source namespace (e.g. "repair", "comonitor"). */
type WatchdogState = Record<string, StateEntry>;

/**
 * Atomically write or merge a status object into the shared state.json.
 * source: e.g. "repair" or "comonitor"
 * statusObj: key/value status map (port, shizuku, sshd, a11y, shell, wifi, etc.)
 *
 * Atomic write is simulated by writing to state.json.tmp then renaming.
 * In AutoJs6 we do not have fs.rename, so we use files.write directly
 * (best effort — partial writes are an extremely small window vs. the 20-min interval).
 */
export function writeState(source: string, statusObj: Record<string, unknown>): void {
  try {
    const profile = config.detectDeviceProfile();
    const statePath = config.pathsFor(profile).watchdogState;
    config.ensureParentDir(statePath);

    // Read current state (may be empty/missing).
    let current: WatchdogState = {};
    try {
      if (files.exists(statePath)) {
        current = (JSON.parse(String(files.read(statePath))) as WatchdogState) || {};
      }
    } catch {
      current = {};
    }

    // Merge the source namespace with a fresh timestamp.
    current[source] = { ...statusObj, timestamp: tsISO() };

    // Write atomically: write to tmp then overwrite final path.
    const tmpPath = statePath + ".tmp";
    files.write(tmpPath, JSON.stringify(current) + "\n");
    // AutoJs6 `files` has no rename; overwrite directly as best effort.
    files.write(statePath, JSON.stringify(current) + "\n");
  } catch {
    /* best effort — state.json write failure must not break the watchdog */
  }
}

/** Read state.json; return parsed object or null. */
function readState(): WatchdogState | null {
  try {
    const profile = config.detectDeviceProfile();
    const statePath = config.pathsFor(profile).watchdogState;
    if (files.exists(statePath)) {
      return (JSON.parse(String(files.read(statePath))) as WatchdogState) || null;
    }
  } catch {
    /* ignore */
  }
  return null;
}

/** Read watchdog log; prefer a tail when the file is large (FUSE / battery). */
export function readWatchdogLog(): string {
  const profile = config.detectDeviceProfile();
  const logPath = config.pathsFor(profile).watchdogLog;
  if (!files.exists(logPath)) return "";
  try {
    const content = String(files.read(logPath));
    const lines = content.split("\n");
    if (lines.length > LOG_TRIM_OVER) {
      return lines.slice(-LOG_KEEP_LINES).join("\n");
    }
    return content;
  } catch {
    return "";
  }
}

/** A STATUS line parsed from the watchdog log or state.json — fields are free-form parsed text, not verified enum members. */
export interface RepairStatus {
  port: string;
  shizuku: string | null;
  sshd: string | null;
  a11y?: string;
  shell?: string;
  wifi?: string;
}

export function parseStatusLine(line: string): RepairStatus | null {
  const m = line.match(/port=(\S+)\s+shizuku=(\S+)\s+sshd=(\S+)/);
  if (!m) return null;
  const out: RepairStatus = { port: m[1], shizuku: m[2], sshd: m[3] };
  const a11y = line.match(/\ba11y=(\S+)/);
  const shell = line.match(/\bshell=(\S+)/);
  const wifi = line.match(/\bwifi=(\S+)/);
  if (a11y) out.a11y = a11y[1];
  if (shell) out.shell = shell[1];
  if (wifi) out.wifi = wifi[1];
  return out;
}

function lineTimestampMs(line: string): number | null {
  const m = line.match(/^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})/);
  if (!m) return null;
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4]), Number(m[5]), Number(m[6])).getTime();
}

function statusFromState(state: WatchdogState | null): RepairStatus | null {
  const repair = state?.repair;
  if (!repair || !repair.port || typeof repair.port !== "string") return null;
  return {
    port: repair.port,
    shizuku: typeof repair.shizuku === "string" ? repair.shizuku : null,
    sshd: typeof repair.sshd === "string" ? repair.sshd : null,
    a11y: typeof repair.a11y === "string" ? repair.a11y : undefined,
    shell: typeof repair.shell === "string" ? repair.shell : undefined,
    wifi: typeof repair.wifi === "string" ? repair.wifi : undefined,
  };
}

/**
 * Read the latest repair status.
 * Prefers state.json["repair"] for O(1) read; falls back to log-scan for
 * backwards compatibility when the state file is absent or corrupt.
 */
export function latestRepairStatus(): RepairStatus | null {
  // --- Primary: state.json ---
  const fromState = statusFromState(readState());
  if (fromState) return fromState;

  // --- Fallback: legacy log scan ---
  const content = readWatchdogLog();
  if (!content) return null;
  const lines = content.split("\n");
  let comonitorFallback: RepairStatus | null = null;
  for (let i = lines.length - 1; i >= 0; i--) {
    // Prefer Termux [repair] STATUS for bridge decisions. A bad
    // [comonitor] STATUS must not trigger CLOSED_NO_SHELL UI repair.
    if (lines[i].indexOf("[repair]") >= 0 && lines[i].indexOf("STATUS") >= 0) {
      return parseStatusLine(lines[i]);
    }
    if (comonitorFallback === null && lines[i].indexOf("[comonitor]") >= 0 && lines[i].indexOf("STATUS") >= 0) {
      comonitorFallback = parseStatusLine(lines[i]);
    }
  }
  return comonitorFallback;
}

/**
 * Return the millisecond timestamp of the most recent Termux [repair] run.
 * Prefers state.json["repair"].timestamp; falls back to log-scan.
 */
export function latestRepairTimestampMs(): number | null {
  // --- Primary: state.json ---
  const state = readState();
  const repairTimestamp = state?.repair?.timestamp;
  if (typeof repairTimestamp === "string") {
    const t = new Date(repairTimestamp).getTime();
    if (!Number.isNaN(t)) return t;
  }

  // --- Fallback: legacy log scan ---
  const content = readWatchdogLog();
  if (!content) return null;
  const lines = content.split("\n");
  for (let i = lines.length - 1; i >= 0; i--) {
    // Termux [repair] is authoritative freshness; [comonitor] does not
    // count as "Termux alive" (would hide a dead boot loop).
    if (lines[i].indexOf("[repair]") >= 0) {
      const lineTs = lineTimestampMs(lines[i]);
      if (lineTs !== null) return lineTs;
    }
  }
  return null;
}

export function isRepairLoopStale(): boolean {
  const last = latestRepairTimestampMs();
  if (last === null) return true;
  return Date.now() - last > config.STALE_REPAIR_MS;
}
