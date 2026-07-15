# OpenObserve + Netdata + Grafana + Aurora + OliveTin Rollout Plan

Here is the complete chronological rollout plan for the **OpenObserve + Netdata + Grafana + Aurora + OliveTin** stack, entirely rewritten to utilize the lightweight, native macOS toolchain (`brew`, `uv`, `bun`, and raw binaries) instead of Docker.

---

## Phase 1: The Core Backend (Ingestion & Storage)

Before touching a single Android device, establish the databases that will catch the data natively on your M1 Mac.

1. **Spin up OpenObserve (Logs & Traces):** Download the M1 (`arm64`) binary directly from their GitHub releases. Extract it and simply run `./openobserve` in your terminal. It will bind to its port and start writing Parquet files directly to your local disk. Take note of the HTTP `/_json` endpoint.
2. **Spin up Netdata (Metrics & ML):** Install via Homebrew using `brew install netdata`. It runs bare-metal, hooking directly into macOS system metrics, and immediately starts baselining its own host using its unsupervised k-means machine learning models.
3. **Network Routing:** Ensure both OpenObserve and Netdata are reachable by the Tailscale IPs or LAN IPs of your Android fleet.

## Phase 2: The Control Plane (OliveTin)

Next, build the execution interface so you have a way to control the fleet before you start monitoring it.

1. **Install OliveTin:** Download the `OliveTin-darwin-arm64.tar.gz` release. Because it is a raw binary downloaded outside the App Store, clear the Apple quarantine flag and run it:

```bash
xattr -dr com.apple.quarantine ./OliveTin
./OliveTin
```

2. **Map the `stayturgid` Commands:** Create the `config.yaml` file for OliveTin. Map your core `just` recipes (e.g., `just deploy-fleet --host {{host}}` or `just heal-firerpa {{host}}`) to OliveTin web actions.
3. **Test Execution:** Open the OliveTin web UI and manually trigger a targeted deployment to a single test Pixel to verify that the web button successfully spawns the local Python virtual environments and runs the Ansible playbook.

## Phase 3: The Edge Rollout (Android/Termux)

Now you modify your `stayturgid` Ansible playbooks to instrument the fleet. Pick 2–3 test devices first.

1. **Apply Android Mitigations:** Add an Ansible task that executes the ADB command to disable the Phantom Process Killer (`adb shell device_config put activity_manager max_phantom_processes 2147483647`) and ensures Termux battery optimization is set to "Unrestricted."
2. **Deploy the Logcat Loop:** Write an Ansible task that drops a simple shell script into Termux. This script should use `shizuku exec` to stream `logcat` to a local file (e.g., `termux.log`) and handle rotation (keeping the files small so they don't eat device storage). Wrap this script in a Termux-service so it starts on boot.
3. **Deploy Vector (`aarch64`):** Use Ansible to download the statically compiled Rust binary of Vector into Termux.
4. **Configure Vector:** Push a `vector.toml` config file that:
   - Tails the `logcat` file you created in step 2.
   - Runs a `scheduled` `exec` script every 60 seconds to grab Termux battery/thermal metrics.
   - Enables local `filesystem` buffering (capped at ~500MB).
   - Routes logs to the OpenObserve HTTP endpoint and metrics to the Netdata parent.
5. **Simulate an Outage:** Disconnect a test Pixel from Wi-Fi/Tailscale for an hour. Reconnect it and verify that Vector successfully flushes its disk buffer to OpenObserve without dropping data.

## Phase 4: Visualization & Human Action (Grafana)

With data flowing and ML baselining in the background, you build your visual command center.

1. **Deploy Grafana:** Install via Homebrew using `brew install grafana` and start the service. Connect Grafana to OpenObserve (via the official plugin) and Netdata (via the Prometheus data source compatibility layer).
2. **Build the Fleet Dashboard:** Create a matrix showing the online/offline status, battery thermals, and error-log rates for every Android device.
3. **Close the Loop (The Click-to-Heal):** Inside your Grafana dashboard panels, use Data Links. Format the links so that clicking on a failing device's hostname dynamically opens your OliveTin UI with that specific hostname pre-populated in the action bar (e.g., `http://mac-ip:5000/?action=HealDevice&host=${__field.labels.host}`).

## Phase 5: The AIOps Brain (Aurora SRE)

Let the system run for 3–5 days so OpenObserve and Netdata can establish statistical ML baselines. Once the baseline is set, introduce the AI investigator using your preferred modern toolchain.

1. **Deploy Local LLM:** Install Ollama natively via `brew install ollama` and pull a highly capable open-weights reasoning model (like `llama3.1` or `qwen2.5-coder`).
2. **Deploy Aurora SRE Backend (Python):** Clone the Aurora repository and navigate to the backend directory. Use `uv` to instantly create the virtual environment and install the LangGraph/LLM dependencies:

```bash
uv venv
uv pip install -r requirements.txt
```

3. **Deploy Aurora SRE Frontend (Next.js):** Navigate to the frontend directory. Use `bun` for near-instant installation and local server execution:

```bash
bun install
bun run dev
```

4. **Connect the Senses:** Provide Aurora with API access to OpenObserve, Netdata, and Grafana so it has permission to autonomously query the data when an incident occurs.
5. **Configure the Triggers:** Set up webhooks in OpenObserve and Netdata. When their ML engines detect a statistical anomaly (e.g., a sudden spike in AutoJs6 UI crashes on the `s24` host), they ping Aurora.
6. **The Autonomous Handoff:** Aurora will wake up, read the anomaly, query the logs to find the exact stack trace, query the metrics to see if the device was overheating, and output a human-readable Root Cause Analysis with a recommendation to run your `just heal-firerpa` script.
