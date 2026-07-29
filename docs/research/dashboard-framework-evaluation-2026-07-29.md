# Dashboard Framework Evaluation (2026-07-29)

## Executive Summary
After evaluating over a dozen dashboard, portal, and operations frameworks, the recommendation for the stayturgid control node is to **Migrate selected features while retaining the device UI.**

Specifically, adopt **Semaphore UI** (a lightweight, single-binary Ansible runner) to absorb Ansible job execution, scheduling, and history, while **retaining the existing Flask + HTMX dashboard** strictly for device-centric health cards, live telemetry links, and synchronous human-consent workflows (like Shizuku authorization). 

Replacing the entire Flask app with a heavy enterprise framework (AWX, Rundeck) violates the low-operational-burden constraint for a 3-device Apple Silicon fleet. Conversely, trying to force Semaphore or generic portal apps (Homepage) to handle bespoke Android consent flows would require building unwieldy plugins that offer no advantage over the current Python codebase. Composition is the right approach.

## Comparison Table

| Candidate | Category | macOS Support | Footprint | Executes Ansible | Handles Android Workflows | Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Semaphore UI** | Ansible Runner | ✅ Yes | Low (Go binary) | ✅ Yes | ❌ Poor | **Adopt** (for jobs) |
| **AWX** | Ansible Runner | ❌ Poor | High (K8s) | ✅ Yes | ❌ Poor | Reject |
| **Ansible Runner**| CLI / Lib | ✅ Yes | Low | ✅ Yes | ❌ No UI | Reject |
| **Rundeck** | Ops Framework | ✅ Yes (JVM) | High | ✅ Yes | ❌ Poor | Reject |
| **Cockpit** | Ops Framework | ❌ Linux only | Low | ❌ No | ❌ No | Reject |
| **NiceGUI / Dash**| Python UI | ✅ Yes | Medium | ❌ Needs custom | ✅ Yes | Reject |
| **Backstage** | Developer Portal | ✅ Yes | High (Node) | ❌ Needs plugins| ❌ Poor | Reject |
| **Homepage** | Portal | ✅ Yes | Low | ❌ No | ❌ No | Reject |
| **ARA Records** | Ansible History | ✅ Yes | Low | ❌ History only | ❌ No | Reject |

## Detailed Analysis of Strongest Candidates

### Semaphore UI
Semaphore is a modern, open-source web UI for Ansible written in Go and Vue.js. 
- **Strengths:** Single statically-linked binary, natively supports Apple Silicon. Uses an embedded BoltDB by default (or MySQL/PostgreSQL), requiring no heavy database infrastructure. It natively understands Ansible inventory, playbooks, SSH credentials, and vault. It streams progress in real time and maintains job history.
- **Weaknesses:** It is fundamentally a job-centric system, not a device-centric one. It does not natively support rendering custom "device health cards" or handling asynchronous human-in-the-loop workflows (like Android "Allow all the time" prompts) smoothly without halting playbook execution indefinitely.

### NiceGUI
A Python-based UI framework built on FastAPI and Vue.
- **Strengths:** Very easy to write dynamic UIs purely in Python. Handles async operations natively.
- **Weaknesses:** It is just a UI framework. Adopting it means rewriting the entire Flask + HTMX dashboard just to end up with another custom dashboard. It does not provide built-in job execution, scheduling, or audit logs.

## Rejection Rationale
- **AWX / Ansible Rulebook:** AWX fundamentally assumes a Kubernetes/K3s deployment, which is a massive operational burden for a 3-device fleet. 
- **Rundeck:** Runs on the JVM, consuming hundreds of megabytes of idle memory. Its plugin system is robust but overkill compared to a native Ansible runner.
- **Cockpit:** Hard dependency on Linux (systemd, DBus, etc.). Incompatible with a macOS control node.
- **Homepage / Homarr:** These are essentially static landing pages with generic ping/uptime widgets. They cannot execute Ansible jobs or handle interactive approval workflows.
- **Django / Flask-AppBuilder:** Porting the current dashboard to these would require writing massive amounts of custom code to implement async job runners, essentially recreating AWX from scratch.

## Proposed Target Architecture
- **Health / Status Reads:** Flask + HTMX (reading real-time state) and Grafana (O-V-G-O) for long-term telemetry.
- **Historical Data:** Grafana (metrics/logs) and Semaphore (Ansible job logs).
- **Ansible Execution:** Semaphore UI. Scheduled jobs and ad-hoc deployments move here.
- **Custom Android Actions:** Flask + HTMX. Interactive, fast-feedback loops like `rish` testing or accessibility toggling stay here where they can be narrowly scoped.
- **Authentication / Authorization:** Caddy / Tailscale for network boundary; Semaphore UI handles its own RBAC for playbook execution.
- **Approval and Audit History:** Semaphore UI tracks who ran what playbook and when.

## Security Analysis
- **Network Expsoure:** Semaphore binds to localhost and sits behind Caddy/Tailscale, maintaining the existing secure perimeter.
- **Secrets Management:** Semaphore has built-in credential management and integrates with Ansible Vault, improving over plain environment variables or ad-hoc shell execution.
- **Privileged Actions:** Moving playbook execution to Semaphore means the Flask app no longer needs permissions to run arbitrary Ansible playbooks, reducing the blast radius if the Flask app is compromised.

## Operational Burden
Extremely low. Semaphore is a single Go binary that can be managed via a `launchd` plist, just like VictoriaMetrics, OpenObserve, and OliveTin. It uses an embedded BoltDB, meaning no PostgreSQL or Redis is required. It runs natively on Apple Silicon.

## Code Impact
- **Custom Code Reduction:** Deleting custom Python scripts dedicated to cron-like scheduling, job logging, and async subprocess polling (estimated 300-500 LOC).
- **Integration Code Added:** Minor configuration to provision Semaphore via Ansible and a `launchd` plist (estimated 100 LOC).

## Staged Migration / PoC Plan
1. **Deploy Semaphore:** Run Semaphore alongside the current dashboard. Bind to `127.0.0.1:3001` behind Caddy.
2. **Move One Job:** Migrate one non-critical scheduled job (e.g., a periodic health ping) from the Flask dashboard to Semaphore. 
3. **Verify:** Check that Semaphore reliably executes the job, logs the output, and handles timeouts correctly.
4. **Rollback:** If Semaphore proves flaky, disable its `launchd` service and restore the Python scheduled job.

## Criteria for Abandoning
Abandon the migration and stick exclusively to Flask + HTMX if:
- Semaphore struggles to accurately report live playbook output or fails to interrupt hanging ADB connections.
- The overhead of keeping Semaphore's inventory in sync with the repository proves too complex for a single-operator environment.
