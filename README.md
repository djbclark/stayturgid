# stayturgid

Keeps wireless ADB (port 5555), Shizuku, and SSH alive on **unrooted Android phones** across reboots, and makes them reachable over Tailscale via **ADB + SSH**. Each piece below is a **separate module** — use only what you need.

---

## Modules

| Module | Path | Standalone? | README |
|--------|------|-------------|--------|
| **Termux scripts** | `termux/` | Yes — repair, boot loop, presence | [termux/README.md](termux/README.md) |
| **Ansible deploy** | `ansible/` | Yes — Termux over SSH only | [ansible/README.md](ansible/README.md) |
| **Mac ADB keepalive** | `mac/` | Yes — launchd reconnect + outage alert | [mac/README.md](mac/README.md) |
| **AutoJs6 watchdog** | `autojs6/` | Yes — needs Termux repair scripts | [autojs6/README.md](autojs6/README.md) |
| **Obtainium catalogs** | `obtainium/` | Yes — any Obtainium user | [obtainium/README.md](obtainium/README.md) |
| **F-Droid / Neo Store** (side) | `fdroid/` + `ansible/roles/fdroid_repos` | fdroidcl + Ansible for repos + Neo Store GUI setup (with Shizuku) | [fdroid/README.md](fdroid/README.md) |
| **Play / Aurora Store** (side) | `ansible/roles/play_store` | `./mac/deploy-play.sh` — Shizuku grant for Aurora | [ansible/roles/play_store/README.md](ansible/roles/play_store/README.md) |
| **Shared Mac helpers** | `shared/` | Yes — `resolve-adb` only | [shared/README.md](shared/README.md) |

---

## Documentation

| Document | Purpose |
|----------|---------|
| [docs/README.md](docs/README.md) | Documentation index |
| [HACKING.md](HACKING.md) | Developer setup, clean install, Obtainium, Termux swap |
| [HANDOFF.md](HANDOFF.md) | Maintainer / AI handoff — state, roadmap, device fleet |
| [version.json](version.json) | Repo release version (Ansible / manual deploy) |

---

## Full stack (quick path)

1. Shizuku (thedjchi fork) — TCP mode, wireless debugging
2. Termux + Termux:Boot + Termux:API — [termux/README.md](termux/README.md) or `./ansible/mac/deploy-termux.sh <host>`
3. AutoJs6 watchdog — [autojs6/README.md](autojs6/README.md) (`setup-autojs6.sh`, `set-automation-mode.sh`, `start-watchdog.sh`)
4. Obtainium catalog — [obtainium/README.md](obtainium/README.md)
5. Mac — [mac/README.md](mac/README.md) (ADB reconnect + access monitor)

**One command (fleet):** `./mac/deploy-fleet.sh` — Ansible Termux deploy, restart boot loop, AutoJs6 deploy + start watchdog.

**Side projects (optional):** `./mac/deploy-fdroid.sh [host]` · `./mac/deploy-play.sh [host]`

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
