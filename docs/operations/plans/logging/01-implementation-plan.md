<!-- historical: production hostnames/IPs in this file are session records; see docs/architecture/multi-site-topology.md §4.1 for current example names -->

# 01-Implementation Plan: Mobile-First Observability Logging Pipeline

Migration of the `stayturgid` Android phone fleet and macOS control node to a structured JSON-based pipeline using OpenTelemetry and Vector. Vector and OpenObserve will run natively on the macOS control node (no Docker), managed via Ansible and Homebrew.

## User Review & Decision Summary

- **Android Background Thread Mitigation:** Decoupled File-to-Collector Tailing Pattern. AutoJs6 and Termux write logs to local JSONL files, and the local OTel Collector (wake-locked) tails them.
- **Service Hosting:** Vector (Homebrew) and OpenObserve (macOS native binary) running locally on the Mac, managed via Ansible and launchd.
- **Email/Admin Username:** `djbclark@gmail.com`
- **Default Ports:** Vector (`4318` for OTLP HTTP) and OpenObserve (`5080` for UI/API) are accepted.
- **Passwords:** A high-security random password and vector bearer token will be generated and stored securely in `secretspec.toml` and local files, never committed to Git.

---

## Proposed Changes

### Component 1: macOS Observability Infrastructure (Ansible & Launchd)

We will install and configure Vector and OpenObserve natively on the Mac control node.

#### [NEW] [observability.yml](file:///Users/djbclark/ops/stayturgid/ansible/playbooks/control_node/observability.yml)

- Ansible playbook for the Mac control node:
  1. Installs Vector via Homebrew (`brew install vector`).
  2. Downloads the macOS OpenObserve binary (matching Mac architecture: `darwin-arm64` or `darwin-amd64`).
  3. Creates a macOS launchd agent configuration (`com.openobserve.plist`) and starts the service.
  4. Deploys the Vector YAML configuration.

#### [NEW] [com.openobserve.plist.j2](file:///Users/djbclark/ops/stayturgid/ansible/roles/control_node/templates/com.openobserve.plist.j2)

- Jinja2 template for the OpenObserve launchd service, setting environment variables for root email, password, and binding interface.

#### [NEW] [vector.yaml.j2](file:///Users/djbclark/ops/stayturgid/ansible/roles/control_node/templates/vector.yaml.j2)

- Jinja2 template for Vector on the Mac, receiving OTLP JSON logs from the fleet devices over Tailscale and forwarding them to local OpenObserve (`http://127.0.0.1:5080/api/default/android_logs/_json`).

---

### Component 2: On-Device Log Refactoring (Roll-Your-Own JSON)

We will transition all logging to structured JSON.

#### [MODIFY] [log.js](file:///Users/djbclark/ops/stayturgid/device/autojs6/lib/log.js)

- Roll a custom JSON formatter inside AutoJs6.
- Format logs conforming to the payload schema and write synchronously to `/sdcard/stayturgid/logs/watchdog.jsonl` (or Fire OS equivalent).
- Refactor status indicators (`latestRepairStatus` and `latestRepairTimestampMs`) to read state from the new local `state.json` file.

#### [MODIFY] [logging.py](file:///Users/djbclark/ops/stayturgid/control/lib/logging.py)

- Refactor the Python logging utilities (`log`) to format entries as JSON lines when writing to `repair.jsonl`.
- Maintain backwards compatibility in `scrape_errors` to parse both JSON and legacy text logs.

#### [NEW] [state.json](file:///Users/djbclark/ops/stayturgid/device/autojs6/run/state.json)

- Introduce a structured state file (Single Source of Truth) shared between Termux and AutoJs6 to avoid regex parsing of log files.

---

### Component 3: Termux OpenTelemetry Collector Deployment

We will deploy the OTel Collector to tail the local log files.

#### [NEW] [otel-config.yaml.j2](file:///Users/djbclark/ops/stayturgid/ansible_collections/stayturgid/android_common/roles/otelcol/templates/otel-config.yaml.j2)

- Configure `filelog` receivers to tail `watchdog.jsonl` and `repair.jsonl`.
- Configure `filelog/logcat` receiver to tail the system logcat buffer.
- Configure `memory_limiter` (100MB limit) and `batch` processors (30s timeout).
- Export via `otlphttp` to the Mac control node's Tailscale IP address on port `4318`.

#### [NEW] [deploy-otelcol.yml](file:///Users/djbclark/ops/stayturgid/ansible/playbooks/fleet/deploy-otelcol.yml)

- Ansible playbook to push OTel Collector binaries (`arm64-v8a` for `s24`/`p7a`, `armeabi-v7a` / 32-bit arm for `hd8`).
- Configure `Termux:Boot` supervisor scripts to keep the OTel Collector process and logcat buffer background loops running.

---

## Verification Plan

### Automated Tests

- Run `just check` to verify Ansible linting and syntax check.
- Run `just test` to run device-free unit tests.

### Manual Verification

1. **Mac Services Audit:** Verify Vector and OpenObserve are running natively on the Mac:
   ```bash
   brew services list | grep vector
   launchctl list | grep openobserve
   ```
2. **Localhost Ingestion Check:** POST a mock OTLP log to the Mac's Vector port `4318` and verify it flows to OpenObserve.
3. **Pilot Device Deploy:** Deploy to `s24` and verify logs are written to `.jsonl` files and immediately forwarded to OpenObserve.
4. **Offline Durability Test:** Disconnect `s24` Tailscale. Generate logs in AutoJs6 and Termux. Verify files are updated. Reconnect Tailscale and confirm all buffered logs populate OpenObserve.
