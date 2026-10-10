# Free FireRPA-like tools for agent control of Android (research, 2026-10-09)

Scope: tools that let an AI agent (ideally over MCP) drive a remote Android device: screen, input,
UI tree, shell, apps. Compared against FireRPA/lamda (github.com/firerpa/lamda: MIT, 8,557 stars,
v10.9 released 2026-09-27) as it runs on s24 / hd8 / p7a behind `stayturgid control/bin/firerpa_mcp.py`.
Stars and release dates come from the GitHub API, read 2026-10-09. No installs and no config changes were made.

## A. Local findings (what is already on this machine)

1. **Maestro (maestro.dev) is installed and registered as an MCP server.** `~/.maestro/bin/maestro`
   v2.6.1, installed 2026-06-29; its PATH entry is at `~/.bashrc:297`. `~/.claude.json` has
   `projects["/Users/djbclark"].mcpServers.maestro = {stdio: "maestro mcp"}`. The server's instruction
   text, which cites `https://docs.maestro.dev/llms.txt`, appears in many `~/.claude/projects/-Users-djbclark/*.jsonl`
   sessions dated 2026-09-20 through 2026-10-08. `site-private/memory/project_shared_mcp_servers_http.md`
   notes the maestro JVM MCP costs about 192 MB per home-dir session and says to "scope it to the mobile
   repo". Upstream is now cli-2.11.0 (2026-09-29), so the local copy is stale.
2. **uiautomator2 3.7.0** is installed through pipx (`~/.local/bin/uiautomator2`). Homebrew has `scrcpy`,
   `android-platform-tools` and `android-commandlinetools`.
3. Nothing was found for gbox, droidrun/mobilerun, mobile-mcp, Android-MCP, uiautodev, Midscene, DroidMind,
   minitap, AutoGLM, agent-device or limrun:
   a. not installed (brew, uv tool, npm -g or pipx);
   b. no dotdirs such as `~/.gbox`, `~/.mobilerun` or `~/.cache/uiautodev`;
   c. no shell history;
   d. no notes in `~/ops/*` or `~/src/one-offs`;
   e. no real mentions in Claude or Codex transcripts. A raw search for "droidrun" returns many hits,
   but they are false positives from "AndroidRuntime" in logcat output. With word boundaries
   (`\bdroidrun\b`), the only hits are this session's own.
   `~/src/mobile` is lichess-mobile and is unrelated.
4. Prior research in stayturgid:
   a. `docs/research/mac-android-ui-automation.md` and `ui-automation.md` rank **Handsets** (`hs` +
   on-device jar) first, then raw `uiautomator dump` + `adb shell input`, then uiautomator2
   ("one-off debug only, never alongside Handsets: exclusive UiAutomation"). They list Maestro and
   Appium under "Avoid as core".
   b. `firerpa-nonroot-research-2026-07-10.md` and the related FireRPA evaluations are under
   `docs/research/evaluations/`.
5. **Policy constraint** (`site-private/memory/feedback_stayturgid_no_screen_control_vlm.md`, 2026-07-25):
   stayturgid retired coordinate-tap and VLM screen control (UI-TARS was removed as "too error prone").
   Vision-agent frameworks below (mobilerun, AutoGLM, mobile-use, Midscene) clash with that rule for fleet
   use. They suit ad-hoc, agent-driven sessions only.

## B. Candidates

Legend: **Root** = needs root. **Device agent** = an APK or server pushed to or installed on the device.
**MCP**: native = maintained by the project itself.

### 1. mobile-mcp (Mobile Next) — github.com/mobile-next/mobile-mcp

- **License / free:** Apache-2.0, fully free locally. Mobile Next Cloud (hosted devices) is the only paid part.
- **Root:** no. **Device agent:** works over adb (built on `mobilecli`). I did not confirm from the README
  whether it pushes a helper APK for Android.
- **Local or cloud:** local. **MCP:** native. stdio by default; `--listen 0.0.0.0:3000` gives streamable
  HTTP at `/mcp`, the same shape as firerpa_mcp.py on the tailnet.
- **Tools:**
  a. devices: list devices, orientation, location, clipboard;
  b. apps: list, launch, terminate, install, uninstall;
  c. screen: screenshot, `mobile_list_elements_on_screen` (accessibility tree), tap, double-tap,
  long-press, swipe, type, press buttons, open URL;
  d. screen recording, device logs and crash reports, batch commands.
  There is no generic shell tool.
- **Fire OS:** no specific concern. It is adb-based, and hd8 already has working wireless adb
  (`project_fireos8_adb_wireless_debugging.md`).
- **Maturity:** 8,801 stars; release 1.0.8 on 2026-10-02; pushed 2026-10-09.
- **Verdict:** the closest drop-in for "an agent drives a device over HTTP MCP" without anything installed
  on the phone. It lacks FireRPA's shell, file and proxy surface.

### 2. Android Remote Control MCP — github.com/danielealbano/android-remote-control-mcp

- **License / free:** MIT, fully free (APK from GitHub Releases).
- **Root:** no. **Device agent:** yes. The APK is itself the MCP server (Ktor/Netty on the phone, default
  port 8080, optional HTTPS). It needs the Accessibility Service enabled; that can be granted with
  `adb shell settings put secure enabled_accessibility_services`.
- **Local or cloud:** local, on the device. Optional Cloudflare Quick Tunnel or ngrok.
- **MCP:** native, streamable HTTP at `/mcp`.
  a. Auth: a bearer token and/or a built-in OAuth 2.1 server with on-device approval.
  b. 57 tools in 14 categories, which can be enabled or disabled per tool and per parameter.
  c. Multi-device tool prefixes (`android_pixel7_tap`).
  d. Camera, clipboard, files and downloads.
  e. Optional on-device PII redaction (about a 150 MB model).
  The author's table claims 10–100 ms actions against 1–4 s for adb-based servers.
- **Fire OS:** untested. The accessibility-service model normally works on Fire OS 8 (Android 11), but
  the PII model is a RAM concern on the hd8.
- **Maturity:** 692 stars; v1.12.0 on 2026-08-19; pushed 2026-08-26. Single maintainer.
- **Verdict:** **architecturally the most FireRPA-like**: a server on the device, reachable over the
  network with token auth, with no Mac-side adb hop. It is non-root, so it is weaker than lamda for shell
  and system access.

### 3. Android-MCP (CursorTouch) — github.com/CursorTouch/Android-MCP

- **License / free:** MIT, fully free.
- **Root:** no. **Device agent:** yes, indirectly. It depends on `uiautomator2>=3.3.1`, which installs
  the u2 agent APK and server.
- **Local or cloud:** local. **MCP:** native, stdio via `uvx --python 3.13 android-mcp`. WiFi adb is
  supported with `ANDROID_MCP_CONNECTION=wifi` and `ANDROID_MCP_HOST`.
- **Tools:** taps, swipes, text, key presses, view-hierarchy capture, device state and **shell commands**.
  Latency is about 2–4 s.
- **Fire OS:** needs Android 10+, which Fire OS 8 meets. u2 conflicts with Handsets (exclusive
  UiAutomation), per the stayturgid notes.
- **Maturity:** 888 stars; v0.2.0 on 2026-05-14; pushed 2026-10-07.
- **Verdict:** a solid, simple u2-backed MCP. It is stdio only, so the tailnet needs an HTTP wrapper.

### 4. Maestro MCP — maestro.dev (github.com/mobile-dev-inc/Maestro)

- **License / free:** Apache-2.0. The CLI and local MCP are free. Maestro Cloud is paid; the
  `list_cloud_devices`, `run_on_cloud` and `get_cloud_run_status` tools need a Cloud login or API key.
- **Root:** no. **Device agent:** yes. Maestro installs its driver/instrumentation APKs on the device.
- **Local or cloud:** local, with a cloud option. **MCP:** native, stdio (`maestro mcp`). Tools:
  `list_devices`, `inspect_screen`, `take_screenshot`, `run` (YAML flows), `cheat_sheet`, `open_maestro_viewer`.
- **Fire OS:** supports physical Android devices. It uses UiAutomation, so it conflicts with
  Handsets and u2.
- **Maturity:** 15,994 stars; cli-2.11.0 on 2026-09-29.
- **Verdict:** **already set up here.** It is built for test flows rather than general remote control:
  there is no shell or file tool, and the JVM is heavy. stayturgid notes rate it "avoid as core".

### 5. Mobilerun (formerly DroidRun) — mobilerun.ai / droidrun.ai (github.com/droidrun/mobilerun)

- **License / free:**
  a. The framework is MIT and fully free locally (bring your own LLM key).
  b. **The Portal APK is AGPL-3.0** (github.com/droidrun/mobilerun-portal).
  c. Mobilerun Cloud free plan: $0, 1 concurrent phone, 60 device-min/month pooled, 500 credits ($5),
  1 GB residential traffic. Paid plans are $20, $99 and $299 a month.
  d. "Connect your phone" to the cloud is a paid add-on (about $4–5 a month).
- **Root:** no. **Device agent:** yes, the Portal APK with its Accessibility Service. Portal exposes local
  HTTP, WebSocket JSON-RPC (port 8081, with a token) and a ContentProvider, plus reverse WebSocket for cloud.
- **Local or cloud:** both.
- **MCP:** **none native.** They ship a `mobile-harness` skill instead (github.com/droidrun/mobile-harness:
  MIT, 395 stars). The only MCP wrapper is community-built and abandoned
  (chukfinley/droidrun-mcp-server, 0 stars).
- **Fire OS:** Portal supports API 26+ (Android 8 is a "compatibility tier"; file operations need
  Android 11+). Fire OS 8 is Android 11, so it should work.
- **Maturity:** 9,597 stars; v0.6.22 on 2026-10-05; Portal v0.7.25 on 2026-08-18.
- **Verdict:** a strong LLM-agent framework, but an agent loop rather than a control plane. The Portal's
  local WebSocket API could be bridged to MCP, but that is DIY.

### 6. GBOX — gbox.ai (github.com/babelcloud/gbox)

- **License / free:** the CLI and MCP are Apache-2.0. **MCP use requires a gbox.ai login** ("Login
  required"). I found no public pricing page (`gbox.ai/pricing` returns 404), so free-tier limits are
  unverified.
- **Root:** no. **Device agent:** yes. A local device is registered over **USB** to a Mac with
  `gbox device-connect` and installs **GBOXKeyboard**.
- **Local or cloud:** cloud virtual devices, cloud physical devices, or your own local device registered
  to the gbox.ai account.
- **MCP:** native (`npx @gbox.ai/mcp-server@latest`, stdio); Android only.
- **Fire OS:** unknown.
- **Maturity:** 181 stars; v0.1.20 on 2026-02-10; pushed 2026-07-16. The gbox-mcp-server repo has 3
  stars, last pushed 2025-11.
- **Verdict:** the account-bound cloud dependency and thin maintenance make it a poor FireRPA substitute.

### 7. uiautodev — uiauto.dev (github.com/codeskyblue/uiautodev)

- **License / free:** MIT, free. By the author of uiautomator2. The web UI is `https://web.uiauto.dev`,
  backed by a local server binary on port 20242; `--offline` mode is available.
- **Root:** no. **Device agent:** yes (u2 driver by default).
- **Local or cloud:** local server with a hosted web front-end.
- **MCP:** none. It is a UI inspector (hierarchy, XPath, script generation) plus a remote screen, not an
  agent API.
- **Fire OS:** same as u2.
- **Maturity:** 543 stars; v0.15.0 on 2026-10-07.
- **Verdict:** this is a human inspector companion. It does not replace FireRPA.

### 8. Appium MCP — github.com/appium/appium-mcp

- **License / free:** Apache-2.0, free.
- **Root:** no. **Device agent:** yes (Appium UiAutomator2 driver APKs, plus a Node Appium server).
- **Local or cloud:** local, or a remote Appium or device-cloud grid.
- **MCP:** native, official Appium project. Includes AI-assisted locator finding.
- **Maturity:** 490 stars; v1.95.3 on 2026-10-04.
- **Verdict:** a test-automation stack. Heavy, and rated "avoid as core" in the stayturgid notes.

### 9. DroidMind — github.com/hyperb1iss/droidmind

- **License / free:** Apache-2.0, free.
- **Root:** no. **Device agent:** none; it is pure adb.
- **MCP:** native, with stdio or SSE transport (`droidmind --transport sse`, default `localhost:4256`).
- **Tools:** device management over USB or TCP, logs, files, apps, APK install, UI taps, swipes and text,
  and **shell with command validation and risk assessment**.
- **Maturity:** 435 stars; v0.4.0 on 2026-01-07, with no pushes since.
- **Verdict:** a good adb-shell-centric MCP with guardrails and no device install, but upkeep has gone quiet.

### 10. agent-device (Callstack) — github.com/callstack/agent-device

- **License / free:** MIT, free.
- **MCP:** native, stdio (`agent-device mcp`). It also has a CLI and a typed Node API. It reads
  accessibility snapshots, refs and selectors, and React Native trees.
- **Maturity:** 4,945 stars; v0.21.22 on 2026-10-06; very active.
- **Verdict:** aimed at app developers verifying their own apps, not fleet or remote control. Its
  internals for physical Android devices are unverified.

### 11. Vision/LLM agent frameworks

These are free and open source, but they are agent loops that need a model key. They also clash with the
stayturgid no-screen-control rule.

- **Open-AutoGLM** (github.com/zai-org/Open-AutoGLM): Apache-2.0, 26,367 stars, last push 2026-03-06.
  adb plus the ADB Keyboard APK; Android 7+; no native MCP.
- **mobile-use (Minitap)** (github.com/minitap-ai/mobile-use, minitap.ai): Apache-2.0, 3,235 stars,
  v3.3.0 on 2026-01-12. adb and Docker. The MCP docs link 404s now, so MCP status is unverified.
- **Midscene.js** (midscenejs.com): MIT, 15,121 stars, v1.14.0 on 2026-09-29. **MCP was retired**:
  "pin Midscene to 1.9.8 … the final version that includes MCP support". It is now skills plus CLI.

### 12. Remote device-farm UIs (no MCP)

- **STF / DeviceFarmer** (github.com/DeviceFarmer/stf): 4,592 stars, v3.8.0 on 2026-09-23.
  a. Its license field reads NOASSERTION on GitHub; it is historically Apache-2.0.
  b. The README says it "Supports Fire OS" and "root is not required".
  c. It provides a browser remote screen at 30–40 fps (minicap), adb over network and APK install.
  d. There is no MCP and no AI layer.
  It is the most proven option for fleet screen access, but no agent can use it without a bridge.
- **scrcpy** (151,655 stars, v5.0.1 on 2026-10-08) is installed already. Community scrcpy-MCP wrappers
  exist, but none stood out.

### Excluded or not verified

- Limrun (limrun.com) and VibeView are cloud emulators only; they cannot drive your own phones.
- Hamibot (hamibot.com) is a cloud-managed Auto.js-style service. A community MCP is listed on mcpmarket,
  but I did not verify its free tier or license.
- AutoJs6 (MPL-2.0, 6,450 stars) is on-device JS automation with no MCP. `kkevsekk1/AutoX` now returns 404.

## C. Ranked top 3 (versus FireRPA, for agent use on s24 / hd8 / p7a)

1. **mobile-mcp.**
   a. Free and Apache-2.0, with the most active upstream (8.8k stars, release on 2026-10-02).
   b. Native **streamable HTTP** (`--listen`), so it can sit on the tailnet exactly like
   firerpa_mcp.py, talking to devices over the wireless adb that already exists.
   c. Gaps against lamda: no shell, files or proxy tools.
2. **Android Remote Control MCP.**
   a. The only candidate that mirrors FireRPA's on-device-server model.
   b. Bearer/OAuth auth, per-tool permissions, files and clipboard, and fast actions, with no root and no
   Mac in the path.
   c. Risks: a single maintainer, and Fire OS is untested. Bind it to the tailnet and never use its
   public tunnels.
3. **DroidMind or Android-MCP (tie), with Maestro MCP as the already-installed fallback.**
   a. DroidMind gives shell plus guardrails over plain adb, with SSE transport.
   b. Android-MCP is the u2 route and has a shell tool.
   c. Maestro is already wired up but is test-flow-shaped.
   d. All three except DroidMind take the exclusive UiAutomation slot, so they cannot run beside
   Handsets, u2 or FireRPA's own UI layer at the same time.

## D. Best guess at the "short domain" service

1. **maestro.dev (Maestro).** Most likely, because it is the only one actually set up: installed
   2026-06-29, registered as the `maestro` MCP in `~/.claude.json`, and its server text citing
   `docs.maestro.dev` appears in many sessions. It is not truly FireRPA-like, though.
2. **uiauto.dev (uiautodev).** Plausible if the memory is of a FireRPA-like _web console_ with a live
   screen and hierarchy. It comes from the uiautomator2 author, and u2 is installed. No local trace of
   uiautodev itself.
3. **gbox.ai.** Plausible if it was "meant to set up": the shortest .ai brand pitched exactly as
   "let Claude Code control Android". No local trace.

Lower odds: droidrun.ai / mobilerun.ai and minitap.ai. Neither has any local trace.

## E. Notes and caveats

DECIDED: I treated "free" as either fully open source or open source with an optional paid cloud.
gbox stays in the list but is flagged, because its MCP requires an account and its pricing is unpublished.

DECIDED: I did not install anything to test Fire OS compatibility. Every "Fire OS" line is inferred
from the tool's minimum Android version and its mechanism (adb, accessibility service or UiAutomation).

UNVERIFIED:

1. whether mobile-mcp/mobilecli pushes a helper APK on Android;
2. gbox free-tier limits;
3. minitap's MCP status;
4. Hamibot's licensing.

Sources:

1. github.com/mobile-next/mobile-mcp
2. github.com/danielealbano/android-remote-control-mcp
3. github.com/CursorTouch/Android-MCP (pyproject: uiautomator2 dependency)
4. docs.maestro.dev/get-started/maestro-mcp
5. github.com/droidrun/mobilerun, github.com/droidrun/mobilerun-portal (LICENSE: AGPL-3.0), mobilerun.ai (pricing)
6. github.com/babelcloud/gbox, docs.gbox.ai/cli/register-local-device
7. github.com/codeskyblue/uiautodev
8. github.com/appium/appium-mcp
9. github.com/hyperb1iss/droidmind
10. github.com/callstack/agent-device
11. github.com/zai-org/Open-AutoGLM, github.com/minitap-ai/mobile-use
12. midscenejs.com/mcp (MCP retired)
13. github.com/DeviceFarmer/stf
14. limrun.com
15. Stars and releases: GitHub REST API, 2026-10-09.

## Outcome (2026-10-09)

djbclark kept the remote `firerpa` MCP as the primary and set up the `maestro` MCP
as the fallback (see `AGENTS.md`, "Driving a device from an agent"). The
uiauto.dev and gbox.ai options were declined, and none of the other candidates
were installed.
