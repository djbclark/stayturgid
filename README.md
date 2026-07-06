# stayturgid

Keeps wireless ADB (port 5555), Shizuku, and SSH alive on **unrooted Android phones** across reboots, and makes them reachable over Tailscale via **ADB + SSH**. Each piece below is a **separate module** — use only what you need.

**Watchdog (2026-07-06):** **AutoJs6 only** on both fleet phones. Tasker, AutoInput, Termux:Tasker, and `tasker-io` were removed from this repo; stayturgid no longer installs or configures them.

---

## Modules

| Module | Path | Standalone? | README |
|--------|------|-------------|--------|
| **Termux scripts** | `termux/` | Yes — repair, boot loop, presence | [termux/README.md](termux/README.md) |
| **Ansible deploy** | `ansible/` | Yes — Termux over SSH only | [ansible/README.md](ansible/README.md) |
| **Mac ADB keepalive** | `mac/` | Yes — launchd reconnect + outage alert | [mac/README.md](mac/README.md) |
| **AutoJs6 watchdog** | `autojs6/` | Yes — needs Termux repair scripts | [autojs6/README.md](autojs6/README.md) |
| **Obtainium catalogs** | `obtainium/` | Yes — any Obtainium user | [obtainium/README.md](obtainium/README.md) |
| **Shared Mac helpers** | `shared/` | Yes — `resolve-adb` only | [shared/README.md](shared/README.md) |

---

## Documentation

| Document | Purpose |
|----------|---------|
| [docs/README.md](docs/README.md) | Documentation index |
| [HACKING.md](HACKING.md) | Developer setup, clean install, Obtainium, Termux swap |
| [HANDOFF.md](HANDOFF.md) | Maintainer / AI handoff — state, roadmap, Tasker removal notes |
| [version.json](version.json) | Repo release version (Ansible / manual deploy) |

---

## Full stack (quick path)

1. Shizuku (thedjchi fork) — TCP mode, wireless debugging
2. Termux + Termux:Boot + Termux:API — [termux/README.md](termux/README.md) or `./ansible/mac/deploy-termux.sh <host>`
3. AutoJs6 watchdog — [autojs6/README.md](autojs6/README.md) (`setup-autojs6.sh`, `start-watchdog.sh`)
4. Obtainium catalog — [obtainium/README.md](obtainium/README.md)
5. Mac — [mac/README.md](mac/README.md) (ADB reconnect + access monitor)

---

## How it works

After each cold reboot and PIN unlock:

1. **Shizuku** auto-starts via Wireless Debugging (TCP mode → port 5555).
2. **Termux:Boot** runs `~/.termux/boot/start-adb.sh` → `sshd` + 5-min self-heal + repair loop.
3. **AutoJs6** `main.js` (20 min + boot via `boot-launcher.js`) → `stayturgid-repair.sh`, notifications, Shizuku UI repair if needed.

---

## SSH to Termux

```bash
ssh s24    # or: ssh p7a
```

Requires `~/.ssh/termux_key` in Termux `authorized_keys` and Tailscale (or `adb forward tcp:8022 tcp:8022`). See [HACKING.md](HACKING.md).

---

## Repo layout

```
stayturgid/
  README.md  docs/README.md  HACKING.md  HANDOFF.md
  termux/  ansible/  mac/  shared/  autojs6/  obtainium/
  version.json
```

---

## Tested on

- Google Pixel 7a, Samsung Galaxy S24 (SM-S921U1), Android 16
- Shizuku thedjchi fork · AutoJs6 6.7.0 · Termux GitHub-debug stack
