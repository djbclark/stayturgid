package org.stayturgid.agent;

/**
 * Shizuku UserService surface for stayturgid-agent.
 *
 * destroy() transaction code is required by Shizuku (see Shizuku.bindUserService docs).
 * Implement destroy() with System.exit(0) after cleanup.
 */
interface IStayTurgidService {

    void destroy() = 16777114;

    /** Inject a silent input event to reset app-level idle timers (Phase 1). */
    void pingAwake() = 1;

    /**
     * Phase 2 co-monitor: run probes and return a single STATUS line
     * (also appended to /sdcard/stayturgid/logs/agent.log).
     */
    String runComonitor() = 2;

    /**
     * Phase 3: shell-first catastrophic repair (wireless ADB + HEADLESS_START).
     * Returns a short result string; does not use Accessibility.
     */
    String repairCatastrophic() = 3;

    /**
     * Restore the Tailscale runtime through its public receiver, with an
     * activity fallback. Success means the tunnel was re-probed as healthy.
     */
    String repairTailscale() = 4;

    /**
     * Idempotently ensure development_settings_enabled/adb_enabled stay on,
     * independent of CLOSED_NO_SHELL. Wireless ADB can't always be forced
     * back open in software on every ROM (see CatastrophicRepair docs), but
     * keeping USB debugging enabled means a physical USB reconnect always
     * works without needing to dig into Developer Options by hand. Cheap,
     * called on every co-monitor tick.
     */
    String ensureAdbBaseline() = 5;
}
