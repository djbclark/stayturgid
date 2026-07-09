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
var config = require("./config.js");
var log = require("./log.js");
var notify = require("./notify.js");
var shizukuShell = require("./shizuku_shell.js");
var repair = require("./repair.js");

var A11Y_SVC = config.AUTOJS6_A11Y;

function sh(cmd) {
    var r = shizukuShell.exec(cmd);
    if (!r) return { code: -1, result: "" };
    return {
        code: typeof r.code === "number" ? r.code : -1,
        result: String(r.result || r.stdout || "").replace(/\r/g, "").trim(),
    };
}

function parseA11yList(raw) {
    var text = String(raw || "").trim();
    if (!text || text === "null") return [];
    var out = [];
    var seen = {};
    var parts = text.split(":");
    for (var i = 0; i < parts.length; i++) {
        var svc = String(parts[i]).trim();
        if (svc && !seen[svc]) {
            seen[svc] = true;
            out.push(svc);
        }
    }
    return out;
}

function mergeA11y(current, add) {
    var merged = parseA11yList(current);
    var seen = {};
    for (var i = 0; i < merged.length; i++) seen[merged[i]] = true;
    for (var j = 0; j < add.length; j++) {
        if (add[j] && !seen[add[j]]) {
            seen[add[j]] = true;
            merged.push(add[j]);
        }
    }
    return merged.join(":");
}

function probeSshd() {
    var r = sh("pgrep -x sshd >/dev/null 2>&1 || pgrep -f '[s]shd' >/dev/null 2>&1");
    return r.code === 0 ? "up" : "down";
}

function restartSshd() {
    sh("export PATH=/data/data/com.termux/files/usr/bin:$PATH; "
        + "pgrep -x sshd >/dev/null 2>&1 || "
        + "/data/data/com.termux/files/usr/bin/sshd || true");
    sleep(1500);
    return probeSshd();
}

function probeShizuku() {
    if (shizukuShell.isOperational()) return "up";
    var r = sh("pgrep -f shizuku_server >/dev/null 2>&1");
    return r.code === 0 ? "up" : "down";
}

function probeShell5555(split, termuxStatus) {
    if (split) return { port: "skip", shell: "no" };
    // Prefer fresh Termux STATUS — AutoJs6 shizuku() often lacks a working
    // `adb` binary/PATH, so a live adb probe false-fires CLOSED_NO_SHELL.
    if (termuxStatus && termuxStatus.port) {
        var p = termuxStatus.port;
        if (p === "open") return { port: "open", shell: "yes" };
        if (p === "skip") return { port: "skip", shell: "no" };
        if (p === "CLOSED_NO_SHELL") return { port: "CLOSED_NO_SHELL", shell: "no" };
    }
    // Live listen check (no adb client required).
    var nc = sh(
        "toybox nc -z 127.0.0.1 5555 >/dev/null 2>&1 || "
            + "nc -z 127.0.0.1 5555 >/dev/null 2>&1"
    );
    if (nc.code === 0) return { port: "open", shell: "yes" };
    // Shizuku API up ⇒ privileged shell available even if adbd TCP is odd.
    if (shizukuShell.isOperational()) {
        return { port: "open", shell: "yes" };
    }
    return { port: "CLOSED_NO_SHELL", shell: "no" };
}

function probeWifi(split) {
    if (split) return "skip";
    var r = sh("settings get global adb_wifi_enabled");
    var v = (r.result || "").trim();
    if (v === "1" || v === "true") return "up";
    sh("settings put global adb_wifi_enabled 1");
    sleep(1000);
    var r2 = sh("settings get global adb_wifi_enabled");
    var v2 = (r2.result || "").trim();
    if (v2 === "1" || v2 === "true") return "repaired";
    return "FAILED";
}

function probeAndRepairA11y(split) {
    // Prefer AutoJs6's own service binding when available.
    try {
        if (typeof auto !== "undefined" && auto.service) {
            return "up";
        }
    } catch (e) { /* fall through */ }

    var r = sh("settings get secure enabled_accessibility_services");
    var list = (r.result || "").trim();
    if (list && list !== "null" && list.indexOf(A11Y_SVC) >= 0) {
        return "up";
    }
    if (split && !shizukuShell.isOperational()) {
        return "unknown";
    }
    var merged = mergeA11y(list, [A11Y_SVC]);
    sh("settings put secure enabled_accessibility_services '" + merged + "'");
    sh("settings put secure accessibility_enabled 1");
    sleep(500);
    var re = sh("settings get secure enabled_accessibility_services");
    var after = (re.result || "").trim();
    if (after.indexOf(A11Y_SVC) >= 0) return "repaired";
    return "FAILED";
}

/**
 * Run co-monitor probes. Returns a STATUS-like object.
 * @param {object} profile
 * @param {{force?: boolean, reason?: string}} opts
 */
function run(profile, opts) {
    opts = opts || {};
    profile = profile || config.detectDeviceProfile();
    var split = config.splitStorage(profile);
    var reason = opts.reason || (split ? "split-storage" : "termux-stale");

    if (!opts.force && !log.isRepairLoopStale() && !config.splitStorage(profile)) {
        // Callers normally pass force=true (periodic fleet parity). Keep the
        // defer path for unit tests / ad-hoc imports.
        return null;
    }

    log.append("[comonitor] start reason=" + reason
        + " shizuku_api=" + (shizukuShell.isOperational() ? "yes" : "no"));

    var sshd = probeSshd();
    if (sshd === "down") {
        log.append("[comonitor] sshd down — restarting via shizuku/shell");
        sshd = restartSshd();
        if (sshd === "up") sshd = "restarted";
    }

    var shizuku = probeShizuku();
    var termuxStatus = null;
    try {
        if (!log.isRepairLoopStale()) {
            termuxStatus = log.latestRepairStatus();
        }
    } catch (e) { /* best effort */ }
    var shellProbe = probeShell5555(split, termuxStatus);
    var wifi = probeWifi(split);
    var a11y = probeAndRepairA11y(split);

    // Catastrophic: no shell on stock Android, or Shizuku dead on any host.
    // Only escalate CLOSED_NO_SHELL when Termux is also stale/unknown — avoid
    // fighting a healthy Termux repair with UI taps every 20 min.
    if (!split && shellProbe.port === "CLOSED_NO_SHELL" && log.isRepairLoopStale()) {
        log.append("[comonitor] CLOSED_NO_SHELL — catastrophic repair");
        notify.show(
            "⚠ ADB 5555 down — co-monitor repairing",
            "Termux repair stale/hung; AutoJs6 co-monitor running Shizuku repair.",
            "adb5555"
        );
        try {
            repair.repairCatastrophic(profile);
        } catch (e) {
            log.append("[comonitor] catastrophic error: " + e);
        }
        shellProbe = probeShell5555(false, null);
        shizuku = probeShizuku();
    } else if (shizuku === "down") {
        log.append("[comonitor] shizuku_server down — catastrophic Start path");
        try {
            repair.repairCatastrophic(profile);
        } catch (e) {
            log.append("[comonitor] shizuku start error: " + e);
        }
        shizuku = probeShizuku();
    }

    if (sshd === "down" || sshd === "FAILED") {
        notify.show(
            "⚠ SSH daemon down (co-monitor)",
            "sshd still down after AutoJs6 restart attempt — check Termux.",
            "sshd"
        );
    } else {
        notify.clear("sshd");
    }

    if (a11y === "FAILED") {
        notify.show(
            "stayturgid AutoJs6 degraded",
            "Co-monitor could not re-enable accessibility — enable AutoJs6 a11y.",
            "a11y-blocked"
        );
    } else if (a11y === "up" || a11y === "repaired") {
        notify.clear("a11y-blocked");
    }

    if (shellProbe.port === "open" || shellProbe.port === "skip") {
        notify.clear("adb5555");
    }

    var status = "STATUS port=" + shellProbe.port
        + " shizuku=" + shizuku
        + " sshd=" + sshd
        + " a11y=" + a11y
        + " shell=" + shellProbe.shell
        + " wifi=" + wifi;
    log.append("[comonitor] " + status + " reason=" + reason);
    return {
        port: shellProbe.port,
        shizuku: shizuku,
        sshd: sshd,
        a11y: a11y,
        shell: shellProbe.shell,
        wifi: wifi,
        reason: reason,
    };
}

module.exports = {
    run: run,
    probeSshd: probeSshd,
    probeShizuku: probeShizuku,
    parseA11yList: parseA11yList,
    mergeA11y: mergeA11y,
};
