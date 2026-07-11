# Research — Handsets under Termux (on-device)

Date: 2026-07-09. Live probes on **s24** (Termux + `localhost:5555`).
hd8 noted as out of scope for this path (no Termux→5555).

## Architecture today (Mac)

```
Mac hs (Mach-O / Linux host binary)
  └─ adb push hs.jar
  └─ adb shell app_process … Main --port=N
  └─ adb forward tcp:N → device 127.0.0.1:N
  └─ length-prefixed binary wire
```

- Daemon: `hs.jar` via `app_process` as **shell UID** — binds **`127.0.0.1:N` only**.
- Client: host `hs` CLI (or PyPI `handsets`, which **subprocess-wraps `hs`**).
- Fleet: `control/lib/ui_driver.py` — ports s24 9013 / hd8 9012 / p7a 9014.

## What Termux can do (proven)

| Step | Result |
|------|--------|
| TCP to `127.0.0.1:9013` from Termux Python | **OK** (same loopback as shell daemon) |
| Start daemon via `adb -s localhost:5555 shell app_process …` | **OK** (`hsd ready`, `listening on 127.0.0.1:9013`) |
| Wire `ping` → `pong` | **OK** (~180 ms cold) |
| Wire `dump_active` → JSON hierarchy | **OK** (~24 KB, **~267 ms**) |
| Wire `info` → `1080 2340` | **OK** |

Wire framing (from upstream README + MITM of Mac `hs`):

```
→  [u32 BE len][ascii verb…]
←  [u32 BE len][body] … optionally [u32 BE 0] EOS
←  or body starting with ERR:…
```

`ping` returns one frame **without** a trailing EOS; clients must not block forever waiting for len=0 (use a short read timeout after the first frame).

## What Termux cannot do (without new work)

| Approach | Blocker |
|----------|---------|
| Run Mac `~/.handsets/hs` on device | Wrong OS/arch (host Mach-O / Linux amd64/arm64, not Android) |
| `pip install handsets` as-is | Pure-Python wheel that **shells out to `hs`** — no Android `hs` binary |
| Stock `hs use` from Termux | Needs host adb + `hs` binary; rejects crowded `ip:5555` lists anyway |
| hd8 on-device Handsets | No Termux→`localhost:5555`; cannot start `app_process` as shell from Termux |

## Options

### A — Thin Termux wire client (recommended if we want on-device Handsets)

~50–150 LOC Python in `device/termux/py/`:

1. Ensure `/data/local/tmp/hs.jar` (Ansible deploy from Mac jar).
2. Start/stop daemon via `adb -s localhost:5555 shell`.
3. Speak wire for `ping`, `dump_active`, `tap x=… y=…`, and whatever verbs we need.
4. Parse `dump_active` JSON (or call higher-level wire verbs if documented) for find/tap-by-text.

**Pros:** Reuses proven daemon; ~10× faster hierarchy than raw dump on-device; no host binary; fits SSH-first post-UI on s24/p7a.  
**Cons:** Must maintain wire verbs; no free CSS selectors unless we implement or call them over wire (`find` / `tap` with selector strings — Mac `hs` does this client-side or via wire; needs a quick verb inventory).  
**Risk:** Medium — protocol is simple and versioned via `info`.

### B — Android build of `hs` CLI

Cross-compile / ship aarch64-linux-android `hs` into Termux `$PREFIX/bin`, then use PyPI bindings or subprocess.

**Pros:** Full selector surface.  
**Cons:** Upstream may not ship Android builds; NDK/CI burden; still need jar + daemon lifecycle.  
**Risk:** High / latent until upstream supports it.

### C — Status quo (Mac Handsets + Termux raw dump)

**Pros:** Already green; Mac path is 17–42× faster than dump; Termux dump is “good enough” for infrequent SSH post-UI.  
**Cons:** On-device scripts stay slow (~0.5–2.5 s per dump); dual code paths remain.  
**Risk:** Low.

### D — Always Mac-only for Handsets; drop Termux UI twins

Route all post-UI through Mac `ui_driver.py` even when SSH is up.

**Pros:** One driver.  
**Cons:** Breaks “phone self-heal without Mac” story; contradicts SSH-first ADR for s24/p7a.  
**Risk:** Product/ops — usually wrong for this fleet.

## Recommendation — **DONE** (2026-07-09)

Spike **A** shipped and switched on:

| Item | Status |
|------|--------|
| `device/termux/py/stayturgid_handsets.py` | Wire client + Session |
| Ansible deploy `hs.jar` → `~/.stayturgid/lib/hs.jar` | `termux_userland` |
| Bench s24 (n=8) | `dump_active` p50 **243 ms** vs raw dump p50 **2979 ms** (~**12×**) |
| `stayturgid_enable_autojs6.py` | Handsets-primary; probe `operational=true` |
| `stayturgid_configure_aurora.py` | Handsets-primary; dump fallback |
| `stayturgid_import_catalog.py` | Handsets-primary; dump fallback |
| Disable | `STAYTURGID_HANDSETS=0` or `STAYTURGID_NO_LOCAL_ADB=1` (hd8) |

**Do not** treat PyPI `handsets` as an on-device solution — it is a host CLI wrapper.

**hd8:** Handsets via **peer bootstrap** (SSH → s24/p7a → adb `app_process`) when
`STAYTURGID_NO_LOCAL_ADB=1`. See [`fire-os-local-adb.md`](fire-os-local-adb.md).
Disable with `STAYTURGID_PEER_BOOTSTRAP=0`.

**rish:** installed by default (`stayturgid_rish.py` / Ansible) to `~/.stayturgid/bin/rish`.
On Fire, Termux↔Shizuku binder often times out — peer ADB is the Handsets starter.

## Non-goals

- Running Mac `hs` under Termux proot/QEMU.
- Replacing AutoJs6 a11y watchdog with Handsets.
- Concurrent Handsets + uiautomator2 (still exclusive UiAutomation).
