<!-- historical: production hostnames/IPs in this file are session records; see docs/architecture/multi-site-topology.md §4.1 for current example names -->

# 02-Implementation Plan: On-Device Structured Logging & State (Phase 2)

Transitioning `stayturgid` on-device logging to structured JSON lines (JSONL) and implementing an atomic local state file (`state.json`) as a Single Source of Truth (SSOT). This decouples status monitoring from historical log scraping, resolving performance issues and bug loops.

## User Review Required

> [!IMPORTANT]
> **Dual-Writing for Compatibility:**
> To prevent breaking existing Mac-side scraping and diagnostic scripts, we will **dual-write** log entries:
>
> 1. Continue appending plain-text log lines to `watchdog.log` and `repair.log`.
> 2. Simultaneously append structured JSON lines conforming to the OTel/OpenObserve schema to `watchdog.jsonl` and `repair.jsonl`.
> 3. Tailing will transition to `*.jsonl`, while legacy command-line tools can still query `*.log` safely.

> [!IMPORTANT]
> **State File Atomicity:**
> To ensure the watchdog doesn't read a half-written `state.json` file, we will implement atomic writes:
>
> 1. Write the new state to `state.json.tmp`.
> 2. Perform an atomic rename (`os.replace` in Python, or native file renames in JS) to replace `state.json`.

---

## Proposed Changes

### Component 1: AutoJs6 Logging & State Client (JS)

We will update the AutoJs6 client side to emit JSON lines, support `state.json`, and handle private/shared storage paths.

#### [MODIFY] [log.js](file:///Users/djbclark/ops/stayturgid/device/autojs6/lib/log.js)

- Modify `append(line)` to dual-write logs:
  - Text format to `watchdog.log` (calls `trimLogIfNeeded` to rotate at 1000 lines).
  - JSONL format (using `JSON.stringify` matching the universal schema) to `watchdog.jsonl`.
- Add `writeState(source, statusObj)` to write the status dictionary to `state.json` under the key `source` (e.g. `"repair"` or `"comonitor"`), adding a `timestamp` field.
- Refactor `latestRepairStatus()` and `latestRepairTimestampMs()` to read status from `state.json` under the `"repair"` key, with a graceful fallback to legacy text-log parsing if the state file is missing or corrupt.

---

### Component 2: AutoJs6 Accessibility Watchdog & Co-Monitor (JS)

#### [MODIFY] [comonitor.js](file:///Users/djbclark/ops/stayturgid/device/autojs6/lib/comonitor.js)

- At the end of `run()`, call `log.writeState("comonitor", statusObj)` to save AutoJs6-probed statuses to the shared state file.

---

### Component 3: Termux Self-Healer Daemon (Python)

We will update the Termux repair loop to write JSON logs and update the shared `state.json` file.

#### [MODIFY] [stayturgid_repair.py](file:///Users/djbclark/ops/stayturgid/device/termux/py/stayturgid_repair.py)

- Import `threading` and `json`.
- Modify `log(msg, level)` to write:
  - Standard text logs to `repair.log` and `watchdog.log`.
  - JSON logs (via `json.dumps` matching the OTel schema) to `repair.jsonl` and `watchdog.jsonl` using a helper `log_json()`.
- Refactor `_write_status(status)` to also update `state.json` atomically (via `state.json.tmp` and `os.replace`), writing the status keys under the `"repair"` namespace.

---

### Component 4: Mac-Side Error Scraper (Python)

We will adapt the error scraper to scan both JSON lines and legacy log formats during rollout.

#### [MODIFY] [logging.py](file:///Users/djbclark/ops/stayturgid/control/lib/logging.py)

- Import `json`.
- Update `_REPAIR_LOG_GREP` to search both `*.log` and `*.jsonl` files on the device.
- Refactor `scrape_errors(text)` to attempt JSON-parsing on each line first. If it is a valid JSON log entry, parse the level/message, filter on errors, format as `"TIMESTAMP [TAG] LEVEL: message"`, and fallback to standard regex-grep matching if the line is not valid JSON.

---

### Component 5: Test Suites

We will update tests to cover the new structured configurations and state properties.

#### [MODIFY] [log.test.js](file:///Users/djbclark/ops/stayturgid/tests/js/log.test.js)

- Add unit test cases to verify JSON log line parsing and `writeState()` file operations.

#### [MODIFY] [comonitor.test.js](file:///Users/djbclark/ops/stayturgid/tests/js/comonitor.test.js)

- Update mock `files` object to simulate `state.json` read/write capabilities.

---

## Verification Plan

### Automated Tests

- Run JS unit tests:
  ```bash
  node tests/js/log.test.js
  node tests/js/comonitor.test.js
  ```
- Run Python self-heal unit tests:
  ```bash
  pytest tests/python/test_stayturgid_repair.py
  ```
- Run full suite:
  ```bash
  just test
  just check
  just lint-offline
  ```

### Manual Verification

1. Verify `watchdog.jsonl` and `repair.jsonl` are populated on-device with valid JSON payloads.
2. Verify `state.json` contains valid atomic updates from both the Python repair run and AutoJs6 comonitor run.
3. Run `just health` and confirm the Mac control node correctly scrapes errors from both JSONL and legacy log files.
