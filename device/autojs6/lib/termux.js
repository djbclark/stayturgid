// @generated
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.tryRunCommand = tryRunCommand;
exports.invokeRepair = invokeRepair;
exports.bridgeFailed = bridgeFailed;
// Rhino gotchas (redeclaration collisions, for...of, exports stamp, Java-string coercion): see docs/architecture/components/autojs6.md "Rhino JS-engine gotchas" before editing.
const termuxConfig = require("./config.js");
const termuxLog = require("./log.js");
const termuxShizukuShell = require("./shizuku_shell.js");
const TERMUX_PKG = "com.termux";
const RUN_SERVICE = "com.termux.app.RunCommandService";
const RUN_ACTION = "com.termux.RUN_COMMAND";
function tryTriggerFile(triggerFile) {
  try {
    termuxConfig.ensureParentDir(triggerFile); // self-heal if run/ was deleted
    files.write(triggerFile, String(Date.now()));
  } catch (e) {
    termuxLog.append("[watchdog] trigger file write failed: " + e);
  }
}
function tryRunCommand() {
  try {
    // Built via raw Intent (not app.startService()'s extras, which can only
    // send string values) so RUN_COMMAND_BACKGROUND reaches Termux as a real
    // boolean. Termux's RunCommandService reads it with getBooleanExtra(),
    // which silently falls back to its default (false) — running the command
    // in the foreground and popping Termux to the front — when the extra was
    // sent as a String instead of a boolean. See stayturgid#34.
    const intent = new android.content.Intent(RUN_ACTION);
    intent.setClassName(TERMUX_PKG, RUN_SERVICE);
    intent.putExtra("com.termux.RUN_COMMAND_PATH", termuxConfig.REPAIR_SCRIPT);
    intent.putExtra("com.termux.RUN_COMMAND_BACKGROUND", true);
    intent.putExtra("com.termux.RUN_COMMAND_WORKDIR", termuxConfig.TERMUX_HOME);
    context.startService(intent);
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
function invokeRepair(profile) {
  const resolvedProfile = profile || termuxConfig.detectDeviceProfile();
  const paths = termuxConfig.pathsFor(resolvedProfile);
  const triggerFile = paths.triggerFile;
  const beforeMs = termuxLog.latestRepairTimestampMs() || 0;
  let triggeredViaShizuku = false;
  // 1. Always arm the trigger file immediately (non-intrusive)
  tryTriggerFile(triggerFile);
  // 2. Try direct background execution via Shizuku shell if operational
  if (termuxShizukuShell.isOperational()) {
    try {
      const cmd =
        "run-as com.termux /data/data/com.termux/files/usr/bin/bash -c '" +
        "export PATH=/data/data/com.termux/files/usr/bin:/data/data/com.termux/files/usr/sbin:$PATH; " +
        "export HOME=/data/data/com.termux/files/home; " +
        "export PREFIX=/data/data/com.termux/files/usr; " +
        "export TMPDIR=/data/data/com.termux/files/usr/tmp; " +
        "python3 " +
        termuxConfig.REPAIR_SCRIPT +
        " " +
        "&'";
      termuxShizukuShell.exec(cmd);
      triggeredViaShizuku = true;
      termuxLog.append("[watchdog] termux bridge: triggered repair directly via Shizuku shell");
    } catch (e) {
      termuxLog.append("[watchdog] termux bridge: Shizuku direct trigger failed: " + e);
    }
  }
  // 3. Loop and wait to see if the background/Shizuku execution succeeds
  const deadline = Date.now() + 12000;
  while (Date.now() < deadline) {
    sleep(500);
    const afterMs = termuxLog.latestRepairTimestampMs();
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
  termuxLog.append("[watchdog] termux bridge: background triggers timed out. Falling back to RUN_COMMAND.");
  const runCommand = tryRunCommand();
  if (runCommand.started) {
    const fallbackDeadline = Date.now() + 8000;
    while (Date.now() < fallbackDeadline) {
      sleep(500);
      const afterMsFallback = termuxLog.latestRepairTimestampMs();
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
  termuxLog.append(
    "[watchdog] termux bridge timeout method=" +
      (runCommand.started ? "run_command" : "trigger_file") +
      (runCommand.error ? " err=" + runCommand.error : ""),
  );
  return { ok: false, fresh: false, method: runCommand.started ? "run_command" : "trigger_file" };
}
function bridgeFailed(invokeResult) {
  if (!invokeResult || !invokeResult.fresh) return true;
  return termuxLog.latestRepairStatus() === null;
}
