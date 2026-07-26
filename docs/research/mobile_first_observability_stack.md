<!-- historical: production hostnames/IPs in this file are session records; see docs/architecture/multi-site-topology.md §4.1 for current example names -->

# Mobile-First Observability Stack & stayturgid Platform Context

## 1. stayturgid Platform Context & Current Implementation Details

This document integrates the **Mobile-First Observability Stack** design with the specific runtime environment and constraints of the **stayturgid** fleet.

### Current Architecture Details

- **Fleet Overview:** Consists of three primary Android devices: `s24` (Samsung Galaxy S24, running Android 16), `p7a` (Pixel 7a, running Android 16), and `hd8` (Fire OS, Amazon Fire HD8).
- **Network & Management:** Managed using Tailscale VPN and orchestrated from a Mac control node using Ansible playbooks, a central `justfile`, and launchd services.
- **On-Device Daemons:**
  - **Primary (Termux):** Runs a 5-minute background loop (`stayturgid_repair.py`) initiated by `start_adb.py` to handle routine self-healing (SSHD, Shizuku servers, ADB port `5555`).
  - **Secondary (AutoJs6):** Runs a 20-minute accessibility watchdog (`main.js` + `watchdog.js` / `comonitor.js`) to provide UI-based catastrophic recovery (Accessibility-based Shizuku Start button tapping) and local alerting.
- **Log System & Issues:**
  - Currently, logging uses unstructured plain text files located on-device under `/sdcard/stayturgid/logs/watchdog.log` and `/data/data/com.termux/files/home/.stayturgid/logs/`.
  - The Mac control node periodically runs a daemon (`fleet_health_monitor.py`) which SSHs/ADBs into the devices, grep-scrapes logs, and parses the tail using regular expressions and indices.
  - **Recent Bug:** The log parsing logic in the AutoJs6 watchdog was searching for `indexOf("[repair] STATUS")`. However, the Python repair daemon logged status lines as `[repair] INFO: STATUS port=open...`. This format mismatch caused the watchdog to fail to find fresh status lines, fall back to stale status history, and repeatedly trigger redundant, foreground-stealing repair intents.

---

# The Mobile-First Observability Stack

**Comprehensive Implementation Guide: Termux, OpenTelemetry, Vector, & OpenObserve**

**TARGET AUDIENCE CONTEXT (CODING AI):** This document contains validated configurations and source code for deploying a mobile-first logging pipeline. When utilizing this guide to generate project files, you must strictly adhere to the provided JSON formats, Android XML security exceptions, and YAML configurations. Do not substitute JSON string formats unless explicitly requested. When editing these configurations (e.g., utilizing Helix or standard text editors), ensure strict YAML and JSON syntax is maintained.

## 1. Architectural Overview

This architecture decouples log generation from network transmission. Mobile applications act as lightweight clients that immediately offload data to a central, shared daemon (Termux) via `localhost`. Termux acts as the heavy-lifting gateway, batching, buffering, and routing data to an external Vector aggregator over the internet. Vector then sanitizes, buffers, and pipes the data into OpenObserve.

### The Universal JSON Payload

To ensure native compatibility with Vector and OpenObserve without complex regex parsing, **every service must emit logs as structured JSON**. The payload must map standard UNIX Syslog and Android Logcat metadata.

| Data Point         | JSON Key     | Example                                |
| ------------------ | ------------ | -------------------------------------- |
| **Time**           | `timestamp`  | "2026-07-15T09:28:34Z" (ISO 8601)      |
| **Severity**       | `level`      | "info", "error", "debug"               |
| **Device/Host**    | `hostname`   | "pixel-7a-xyz" or "node-server-01"     |
| **Identifier**     | `tag`        | "auth_module" or "my_application"      |
| **Process/Thread** | `pid`, `tid` | 10423, 592                             |
| **Payload**        | `message`    | "Application initialized successfully" |

---

## 2. Log Generators (First-Party Applications)

### 2.1 Node.js Generator (`pino`)

For Node.js backend services, `pino` is the native standard for high-performance, structured JSON logging.

```javascript
const pino = require("pino");
const os = require("os");
const { isMainThread, threadId } = require("worker_threads");

const logger = pino({
  level: "info",
  timestamp: pino.stdTimeFunctions.isoTime,
  base: {
    hostname: os.hostname(),
    pid: process.pid,
    tid: isMainThread ? 0 : threadId,
    tag: "node_backend",
  },
});
logger.info({ user_id: "8472" }, "User authentication successful");
```

### 2.2 Python Generator (`structlog`)

Use `structlog` to bind system context globally in Python environments.

```python
import structlog
import socket
import os
import threading


def add_process_info(logger, method_name, event_dict):
    event_dict["hostname"] = socket.gethostname()
    event_dict["pid"] = os.getpid()
    event_dict["tid"] = threading.get_native_id()
    event_dict["tag"] = logger.name or "root"
    return event_dict


structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        add_process_info,
        structlog.processors.JSONRenderer(),
    ]
)
logger = structlog.get_logger("my_python_app")
logger.info("Application initialized")
```

### 2.3 Android Native Integration (OpenTelemetry SDK)

Android applications push data to the local Termux daemon. Because this traffic routes over `127.0.0.1`, you must bypass Android's Cleartext Traffic restrictions.

**Critical Step 1: Cleartext Traffic Exception**
Create `res/xml/network_security_config.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <domain-config cleartextTrafficPermitted="true">
        <domain includeSubdomains="true">127.0.0.1</domain>
        <domain includeSubdomains="true">localhost</domain>
    </domain-config>
</network-security-config>

```

Apply it in `AndroidManifest.xml`: `<application android:networkSecurityConfig="@xml/network_security_config" ...>`

**Critical Step 2: OpenTelemetry Initialization**
Configure the HTTP exporter to point directly to the local Termux listener. Leave local SDK buffering enabled as a failsafe if Termux is temporarily killed by the OS.
_(Note: If the application minSdk is < 26, ensure corelib desugaring is enabled in the AGP configuration.)_

```kotlin
// OpenTelemetry OTLP Configuration
httpExport {
    baseUrl = "http://127.0.0.1:4318"
}

```

---

## 3. The Termux Gateway (Device-Level Daemon)

This daemon centralizes the network footprint, saves battery, captures third-party logs, and handles offline buffering for the entire Android device.

### 3.1 Installation & Device Persistence

When provisioning the gateway on modern Android hardware, aggressive OS battery management will kill the daemon unless explicitly handled. Termux does not auto-start on device reboot natively.

1. **Install OpenTelemetry Collector:**

```bash
pkg update && pkg install wget -y
wget https://github.com/open-telemetry/opentelemetry-collector-releases/releases/latest/download/otelcol_linux_arm64.tar.gz
tar -xvf otelcol_linux_arm64.tar.gz
chmod +x otelcol

```

2. **Surviving Reboots (`Termux:Boot`):** Install the `Termux:Boot` APK. Create a script at `~/.termux/boot/start-otelcol.sh`:

```bash
#!/data/data/com.termux/files/usr/bin/sh
termux-wake-lock
/data/data/com.termux/files/home/otelcol --config=/data/data/com.termux/files/home/config.yaml &

```

3. **Battery Whitelist:** Exempt Termux from Doze mode:

```bash
dumpsys deviceidle whitelist +com.termux

```

### 3.2 Capturing Third-Party App Logs

To capture system-wide third-party data, Termux requires elevated permissions. Connect via ADB from a primary workstation or execute on-device using a Shizuku terminal interface to run:

```bash
pm grant com.termux android.permission.READ_LOGS

```

Run a background process to buffer system logcat to a rotating file so the Collector can safely tail it:

```bash
logcat -v threadtime -f /data/data/com.termux/files/home/logcat_buffer.txt -r 10240 -n 4 &

```

### 3.3 Termux OpenTelemetry Configuration (`config.yaml`)

This configuration handles local ingestion, third-party log parsing, strict memory limits (critical to avoid the Android OOM killer), and aggressive mobile batching.

```yaml
receivers:
  # 1. Local OTLP Receiver for First-Party Apps
  otlp:
    protocols:
      http:
        endpoint: "127.0.0.1:4318"

  # 2. Tail the elevated local logcat buffer (Third-Party logs)
  filelog/logcat:
    include:
      - /data/data/com.termux/files/home/logcat_buffer.txt
    operators:
      - type: regex_parser
        regex: '^(?P<date>\d{2}-\d{2})\s+(?P<time>\d{2}:\d{2}:\d{2}\.\d{3})\s+(?P<pid>\d+)\s+(?P<tid>\d+)\s+(?P<level>[VDIWEF])\s+(?P<tag>.*?)\s*:\s+(?P<message>.*)$'
      - type: add
        field: attributes.source
        value: "system_logcat"

processors:
  # Protect Android Memory (Max ~100MB footprint)
  memory_limiter:
    check_interval: 1s
    limit_mib: 100
    spike_limit_mib: 20

  # Append Gateway Identifier
  attributes/gateway_context:
    actions:
      - key: gateway
        value: "termux_daemon"
        action: insert

  # Aggressive Batching for Mobile Radio Efficiency
  batch:
    send_batch_size: 1000
    timeout: 30s
    send_batch_max_size: 1500

exporters:
  otlphttp/vector:
    endpoint: "https://your-vector-server.com" # Exclude /v1/logs path here
    headers:
      "Authorization": "Bearer YOUR_SECURE_INGESTION_TOKEN"
    retry_on_failure:
      enabled: true
      initial_interval: 5s
      max_elapsed_time: 5m

service:
  pipelines:
    logs:
      receivers: [otlp, filelog/logcat]
      processors: [memory_limiter, attributes/gateway_context, batch]
      exporters: [otlphttp/vector]
```

---

## 4. Vector Aggregator Configuration (Remote Server)

Vector sits on a remote cloud server, receiving batched OTLP data from mobile gateways and raw JSON from Node.js/Python servers. It authenticates the traffic, buffers it to survive mobile reconnect bursts, and routes it to OpenObserve.

### 4.1 Implementation Details

- **Security:** The OTLP endpoint must be secured via Bearer Token to prevent public ingestion spam.
- **The Thundering Herd:** Mobile devices frequently lose and regain connectivity simultaneously. The `buffer: type: disk` directive is mandatory to prevent the Vector server from running out of RAM during a mass reconnect.
- **OpenObserve Routing:** Logs must explicitly route to the `/_json` endpoint, and healthchecks must point to `/healthz`.

```yaml
sources:
  termux_gateways:
    type: opentelemetry
    http:
      address: "0.0.0.0:4318"
      auth:
        type: "bearer"
        token: "YOUR_SECURE_INGESTION_TOKEN"

  node_servers:
    type: file
    include: ["/var/log/node_apps/*.json"]

sinks:
  openobserve_logs:
    type: http
    inputs: ["termux_gateways", "node_servers"]
    uri: "https://your-openobserve-instance.com/api/default/android_logs/_json"
    method: post
    auth:
      strategy: basic
      user: "root@example.com"
      password: "YOUR_OPENOBSERVE_PASSWORD"
    encoding:
      codec: json
      timestamp_format: rfc3339

    # Critical: Disk buffering to survive 'Thundering Herd' mobile reconnects
    buffer:
      type: disk
      max_size: 1073741824 # 1 GB disk buffer
      when_full: block

    healthcheck:
      enabled: true
      uri: "https://your-openobserve-instance.com/healthz"
```

---

## 5. Fleet Provisioning Strategy

Deploying this Termux setup manually across multiple devices is inefficient. For fleet provisioning without requiring a constant physical computer connection, leverage local automation utilities like Tasker, paired with Shizuku, to broadcast setup intents natively.

**Example Tasker/Shell Intent Broadcast:**

```bash
# Force Termux to execute the config download without user interaction
am broadcast --user 0 -a com.termux.RUN_COMMAND \
    --es com.termux.RUN_COMMAND.PATH "/data/data/com.termux/files/usr/bin/wget" \
    --es com.termux.RUN_COMMAND.ARGUMENTS "https://your-server.com/provisioning/otel-config.yaml -O /data/data/com.termux/files/home/config.yaml"

```

---

## Input from the Junior Developer AI

### Step-by-Step Implementation Plan

1. **Step 1: Refactor Codebase Log Structures to JSONL**
   - Update logging methods in `device/autojs6/lib/log.js` to log JSON structures rather than plain text strings.
   - Update the log function in `device/termux/py/stayturgid_repair.py` to write JSON-structured lines to `repair.log`.
   - Keep a backwards-compatible parser in the health check systems that can parse both JSON format and legacy plain-text lines during roll-out.

2. **Step 2: Introduce Local State File ("Single Source of Truth")**
   - Create a state file directory `/sdcard/stayturgid/run/` and write a single, atomic `state.json` file containing the active STATUS keys (port, shizuku, sshd, a11y, etc.) instead of parsing historically written text files.
   - Update both `stayturgid_repair.py` and `comonitor.js` to read and write from this file.

3. **Step 3: Setup OpenTelemetry Collector on Devices**
   - Package OpenTelemetry Collector binaries for target `arm64` architecture (Android devices S24, P7a, HD8).
   - Integrate OTel collector execution into the `Termux:Boot` lifecycle script (`start-adb.sh`).
   - Author a provisioning YAML configuration (`config.yaml`) for each device mapping to a local listener `http://127.0.0.1:4318`.

4. **Step 4: Provision Vector Aggregator**
   - Deploy a Vector server on the control/remote server node.
   - Apply the configuration utilizing disk buffering to tolerate thundering herd reconnects.
   - Secure Vector ingress using a token.

5. **Step 5: Setup OpenObserve Destination**
   - Configure Vector to route ingested payloads to OpenObserve instance endpoints (`/_json`).
   - Setup dashboards in OpenObserve for visualizing mobile fleet availability, logs, and drift stats.
