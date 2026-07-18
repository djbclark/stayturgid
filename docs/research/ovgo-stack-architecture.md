<!-- historical: production hostnames/IPs in this file are session records; see docs/architecture/multi-site-topology.md §4.1 for current example names -->

# The Hardened "O-V-G-O" Stack Architecture

```text
[Android Fleet (Termux)]
   └── Logcat Daemon Script ──> local file ──> Vector (aarch64)
   └── Scheduled exec (Battery/WiFi) ────────┘
                                                │ (Intermittent Connection / Gzip JSON)
                                                ▼
[Central Infrastructure]
   ├── Ingestion ──> OpenObserve (Logs/Traces) & VictoriaMetrics (Metrics)
   └── Read UI   ──> Grafana (Unified Dashboards)
   └── Write UI  ──> OliveTin (Web buttons calling local Mac 'just' recipes)
```

---

### 1. The Hardened Edge (Inside Termux)

To keep the footprint minimal and protect against Android 14's background killing, we use a single binary but separate the log collection strategy as recommended.

- **The Shipper:** **Vector (`aarch64-unknown-linux-musl`)** running natively inside Termux. Configured with a conservative local disk buffer (`storage.type = "filesystem"`, capped at `1GiB`) inside Termux's private app directory to withstand days of offline state.
- **The Logcat Strategy (Mitigation applied):** Do _not_ stream `logcat` directly inside a Vector `exec` block. Instead, deploy a tiny, native Termux background service (using Termux-services or a boot hook) running a robust loop:

```bash
# Simple continuous rotation script running locally
shizuku exec logcat -v time -f /data/data/com.termux/files/home/logs/logcat.log -r 2048 -n 3
```

Point Vector's robust `file` source directly at this log file. It handles file rotations, pointers, and crashes perfectly.

- **The Metrics Strategy:** Use Vector's `scheduled` `exec` sources to run periodic lightweight Termux CLI commands (e.g., `termux-battery-status` or checking `/proc/net/dev`) every 30–60 seconds, using Vector Remap Language (VRL) to format them into metrics objects before shipping.
- **Keep-Alive Guardrails:** Ensure your device onboarding script sets battery optimization to "Unrestricted" and runs the ADB command to maximize the phantom process limit.

---

### 2. The Burst-Tolerant Core (Central Server)

When your Pixels regain a solid cellular or Tailscale connection, they will dump a massive backlog of compressed JSON payloads.

- **Logs & Traces Engine:** **OpenObserve**. It skips the rigid chronological constraints of Grafana Loki, meaning a flood of 3-day-old logs arriving simultaneously from a reconnected device won't cause out-of-order rejection errors. It writes directly to highly efficient Parquet files on disk.
- **Metrics Engine:** **VictoriaMetrics**. A single-binary time-series database that accepts metrics exported from Vector. It speaks native PromQL, meaning it drops seamlessly into Grafana dashboards while using negligible RAM.

---

### 3. The Read UI (Observability)

- **The Dashboard:** **Grafana**. You connect it to VictoriaMetrics (via Prometheus data source) and OpenObserve. You build a single, unified "Fleet Control Room" dashboard showing device state, battery thermals, and real-time log counts.

---

### 4. The Write UI & Control Plane (Execution)

Because `stayturgid` uses a central Mac control node executing Python wrappers and `just` commands, **OliveTin** is the ultimate lightweight operational interface.

- **The Controller:** **OliveTin (Go single-binary)** running on your Mac manager.
- **Why it beats Semaphore here:** OliveTin doesn't care about static Ansible host reachability. It provides a clean web UI where clicking a button simply fires off your existing `just` commands locally on the Mac. The Mac node then uses your local virtual environments (`.venv-test` or `/tmp/lamda-venv`) to handle the heavy lifting, network fallbacks, and gRPC execution to the devices.
- **The Interface Integration:** In your Grafana device health dashboards, you can embed clean markdown links or variables that point directly to your OliveTin web interface, automatically passing the exact `host` string (e.g., `s24` or `hd8`) into OliveTin's execution execution bar.

---

### 5. Integration with the `stayturgid` Codebase

The O-V-G-O stack maps perfectly to the `stayturgid` operational model and provides a direct replacement for several legacy custom tools and monitors.

#### 5.1 Completely Deprecate the Flask/HTMX Dashboard

**Current State:** The project currently maintains a custom Flask + HTMX web UI (`control/bin/dashboard.py`) that runs on port 4097 via a Mac launchd agent (`dashboard.plist.j2`). It functions by regex-parsing flat log files (`fleet-health.log`, `firerpa-health.log`, `errors.log`).
**Integration Plan:** Retire `dashboard.py` and its launchd agent.

- **Grafana** natively replaces the Read UI by visualizing metrics stored in VictoriaMetrics and OpenObserve.
- **OliveTin** natively replaces the Write UI. You can use Grafana Data Links to hyperlink device-specific status panels directly to OliveTin execution endpoints (e.g., clicking on a failing "s24" in Grafana opens the OliveTin action for `just --set hosts s24 verify-heal`).

#### 5.2 Shift from "Mac Polling" to "Android Push" (Monitor Scripts)

**Current State:** The Mac control node uses launchd to constantly poll the devices using custom Python scripts (`access_monitor.py`, `fleet_health_monitor.py`, `firerpa_health_monitor.py`). These scripts connect via SSH/ADB to check `termux-battery-status`, sshd state, and Shizuku availability, appending strings to flat files.
**Integration Plan:** The O-V-G-O architecture allows us to invert this.

- **Vector on the Edge:** Vector's `scheduled` exec blocks running inside Termux can execute `termux-battery-status` and check Shizuku themselves, formatting the output via VRL and pushing it to VictoriaMetrics.
- **Retire Mac Pollers:** We can safely retire or heavily scale back `fleet_health_monitor.py` and `access_monitor.py`. A device's health is simply defined by the freshness of its metrics in VictoriaMetrics (`up == 1`). This is far more resilient to the "intermittent connection" problem than the Mac failing to connect over SSH.

#### 5.3 Modernize Log Aggregation (`check_fleet_health.py`)

**Current State:** To view errors, the operator runs `just errors`, which triggers `check_fleet_health.py --hours 168` to grep and parse flat files on the Mac.
**Integration Plan:** By utilizing **Vector** to ship `logcat` directly to **OpenObserve**, we eliminate the need for custom Python log parsing. Grafana can query OpenObserve directly, allowing visual alerts for specific Android-level crashes (e.g., UI Automator crashes or Shizuku disconnects) across the entire fleet instantly, without SSH-ing into devices or relying on Mac-side flat files.

#### 5.4 OliveTin's Execution Environment Constraints

**Current State:** Operators run `just` commands in a macOS Terminal session where Homebrew paths, `STAYTURGID_ADB`, and virtual environments (`.venv-test`, `/tmp/lamda-venv`) are properly initialized.
**Integration Plan:** When configuring OliveTin to execute `just` recipes, ensure the OliveTin daemon runs under a context that mirrors the Mac user's environment. The `stayturgid` deployment heavily relies on absolute paths to Homebrew (`/opt/homebrew/bin/adb`) and specific Python virtualenvs for FIRERPA gRPC commands. The OliveTin `config.yaml` should explicitly source these before running `just deploy`.

#### 5.5 Ansible Provisioning for the Edge (Vector)

**Current State:** `termux-userland.yml` manages Termux packages and boot hooks.
**Integration Plan:** Extend the existing Ansible `termux_userland` role to deploy the Vector `aarch64` binary and the `logcat` daemon rotation script. This maintains the "Codebase Harmony" philosophy, ensuring that a new device can be fully provisioned with the O-V-G-O edge components by simply running `just deploy`.

---

### Why This Complete Stack Wins for `stayturgid`

1. **Zero Resource Waste:** Vector (Rust), OpenObserve (Rust), VictoriaMetrics (Go), and OliveTin (Go) are all single-binary, high-performance engines. You completely avoid the massive JVM memory footprints of traditional setups like ELK or Rundeck.
2. **Android Resilient:** It isolates the fragile `logcat` stream to a native file wrapper, uses local storage buffering to survive cellular dead zones, and gracefully accepts chunked, back-dated data dumps at the core backend.
3. **Codebase Harmony:** It doesn't force you to rewrite your codebase. It wraps around your existing `justfile`, leverages the central Mac node setup you already built, and leaves your Ansible logic completely intact.
