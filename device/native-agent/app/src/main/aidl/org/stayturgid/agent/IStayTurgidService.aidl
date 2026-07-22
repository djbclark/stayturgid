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
}
