import config = require("./config.js");
import log = require("./log.js");
import shizukuShell = require("./shizuku_shell.js");

import type { DeviceProfile } from "./config.js";

const TERMUX_PKG = "com.termux";
const RUN_SERVICE = "com.termux.app.RunCommandService";
const RUN_ACTION = "com.termux.RUN_COMMAND";

/** Outcome of invokeRepair(): either a fresh STATUS was observed, or every path timed out. */
export type InvokeRepairResult =
  | {
      ok: true;
      fresh: true;
      method: "shizuku_shell" | "trigger_file" | "run_command";
      beforeMs: number;
      afterMs: number;
    }
  | { ok: false; fresh: false; method: "trigger_file" | "run_command" };

function tryTriggerFile(triggerFile: string): void {
  try {
    config.ensureParentDir(triggerFile); // self-heal if run/ was deleted
    files.write(triggerFile, String(Date.now()));
  } catch (e) {
    log.append("[watchdog] trigger file write failed: " + e);
  }
}

interface RunCommandOutcome {
  started: boolean;
  error?: string;
}

function tryRunCommand(): RunCommandOutcome {
  try {
    app.startService({
      action: RUN_ACTION,
      packageName: TERMUX_PKG,
      className: RUN_SERVICE,
      extras: {
        "com.termux.RUN_COMMAND_PATH": config.REPAIR_SCRIPT,
        "com.termux.RUN_COMMAND_BACKGROUND": "true",
        "com.termux.RUN_COMMAND_WORKDIR": config.TERMUX_HOME,
      },
    });
    return { started: true };
  } catch (e) {
    return { started: false, error: String(e) };
  }
}

/**
 * Invoke stayturgid_repair.py in Termux.
 *
 * Primary: RUN_COMMAND intent (needs AutoJs6 v6.4.1+ with
 * com.termux.permission.RUN_COMMAND granted + allow-external-apps=true).
 * Fallback: touch <sd>/run/repair_now for bridges.py --mode repair (2s poll).
 */
export function invokeRepair(profile?: DeviceProfile): InvokeRepairResult {
  const resolvedProfile = profile || config.detectDeviceProfile();
  const paths = config.pathsFor(resolvedProfile);
  const triggerFile = paths.triggerFile;
  const beforeMs = log.latestRepairTimestampMs() || 0;
  let triggeredViaShizuku = false;

  // 1. Always arm the trigger file immediately (non-intrusive)
  tryTriggerFile(triggerFile);

  // 2. Try direct background execution via Shizuku shell if operational
  if (shizukuShell.isOperational()) {
    try {
      const cmd =
        "run-as com.termux /data/data/com.termux/files/usr/bin/bash -c '" +
        "export PATH=/data/data/com.termux/files/usr/bin:/data/data/com.termux/files/usr/sbin:$PATH; " +
        "export HOME=/data/data/com.termux/files/home; " +
        "export PREFIX=/data/data/com.termux/files/usr; " +
        "export TMPDIR=/data/data/com.termux/files/usr/tmp; " +
        "python3 " +
        config.REPAIR_SCRIPT +
        " " +
        "&'";
      shizukuShell.exec(cmd);
      triggeredViaShizuku = true;
      log.append("[watchdog] termux bridge: triggered repair directly via Shizuku shell");
    } catch (e) {
      log.append("[watchdog] termux bridge: Shizuku direct trigger failed: " + e);
    }
  }

  // 3. Loop and wait to see if the background/Shizuku execution succeeds
  const deadline = Date.now() + 12000;
  while (Date.now() < deadline) {
    sleep(500);
    const afterMs = log.latestRepairTimestampMs();
    if (afterMs !== null && afterMs > beforeMs) {
      return {
        ok: true,
        fresh: true,
        method: triggeredViaShizuku ? "shizuku_shell" : "trigger_file",
        beforeMs,
        afterMs,
      };
    }
  }

  // 4. Fallback: Only use com.termux.RUN_COMMAND intent as a last resort
  log.append("[watchdog] termux bridge: background triggers timed out. Falling back to RUN_COMMAND.");
  const runCommand = tryRunCommand();
  if (runCommand.started) {
    const fallbackDeadline = Date.now() + 8000;
    while (Date.now() < fallbackDeadline) {
      sleep(500);
      const afterMsFallback = log.latestRepairTimestampMs();
      if (afterMsFallback !== null && afterMsFallback > beforeMs) {
        return {
          ok: true,
          fresh: true,
          method: "run_command",
          beforeMs,
          afterMs: afterMsFallback,
        };
      }
    }
  }

  log.append(
    "[watchdog] termux bridge timeout method=" +
      (runCommand.started ? "run_command" : "trigger_file") +
      (runCommand.error ? " err=" + runCommand.error : ""),
  );
  return { ok: false, fresh: false, method: runCommand.started ? "run_command" : "trigger_file" };
}

export function bridgeFailed(invokeResult: InvokeRepairResult | null | undefined): boolean {
  if (!invokeResult || !invokeResult.fresh) return true;
  return log.latestRepairStatus() === null;
}
