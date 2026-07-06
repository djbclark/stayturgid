# stayturgid

Keeps wireless ADB (port 5555), Shizuku, and SSH alive on **unrooted Android phones** across reboots, and makes them reachable over Tailscale via **ADB + SSH**. Each piece below is a **separate module** — use only what you need.

**Production stacks (2026-07-05):** Galaxy S24 — **AutoJs6** (`mode=autojs6`). Pixel 7a — **Tasker+AutoInput** (`mode=tasker`). Never run both automation stacks on one device.

---

## Modules (pick one or combine)

| Module | Path | Standalone? | README |
|--------|------|-------------|--------|
| **Termux scripts** | `termux/` | Yes — repair, boot loop, presence | [termux/README.md](termux/README.md) |
| **Ansible deploy** | `ansible/` | Yes — Termux over SSH only | [ansible/README.md](ansible/README.md) |
| **Mac ADB keepalive** | `mac/` | Yes — launchd reconnect + outage alert | [mac/README.md](mac/README.md) |
| **Tasker watchdog** | `tasker/` | Yes — needs Termux bridge + Shizuku | [tasker/README.md](tasker/README.md) |
| **Tasker import tool** | `tasker-io/` | Yes — any Tasker project | [tasker-io/README.md](tasker-io/README.md) |
| **AutoJs6 watchdog** | `autojs6/` | Yes — needs Termux repair scripts | [autojs6/README.md](autojs6/README.md) |
| **Obtainium catalogs** | `obtainium/` | Yes — any Obtainium user | [obtainium/README.md](obtainium/README.md) |

**Also:** [tasker/auto-update/](tasker/auto-update/README.md) (GitHub `version.json` updates) · [autojs6/COMPARISON.md](autojs6/COMPARISON.md) (Tasker vs AutoJs6)

---

## All documentation

| Document | Purpose |
|----------|---------|
| [docs/README.md](docs/README.md) | **Documentation index** — every README and guide |
| [HACKING.md](HACKING.md) | Developer setup, clean install, Tasker XML, Termux swap |
| [HANDOFF.md](HANDOFF.md) | Maintainer / AI handoff — state, roadmap, tooling rules |
| [version.json](version.json) | Tasker auto-update version source (GitHub raw) |

---

## Full stack (quick path)

If you want the whole system on a new phone, read [HACKING.md](HACKING.md). Short outline:

1. Shizuku (thedjchi fork) — TCP mode, wireless debugging
2. Termux + Termux:Boot + Termux:API — [termux/README.md](termux/README.md) or `./ansible/mac/deploy-termux.sh <host>`
3. Watchdog — **either** [tasker/](tasker/README.md) **or** [autojs6/](autojs6/README.md)
4. Obtainium catalog — [obtainium/README.md](obtainium/README.md)
5. Mac — [mac/README.md](mac/README.md) (ADB reconnect + access monitor)

---

## How it works (integrated)

After each cold reboot and PIN unlock:

1. **Shizuku** auto-starts via Wireless Debugging (TCP mode → port 5555).
2. **Termux:Boot** runs `~/.termux/boot/start-adb.sh` → `sshd` + 5-min self-heal.
3. **Watchdog** (Tasker *or* AutoJs6) every 20 min → `stayturgid-repair.sh`, notifications, Shizuku UI repair if needed.

---

## TaskerNet (optional)

One-click Tasker project import (manual discovery; auto-update uses GitHub):

https://taskernet.com/shares/?user=AS35m8lVOCqN0zylSnJKY8pBzCqkgDU8h624gr9CWqSAxD9myEt6n3OjyI4TtJhMtMw%2B&id=Project%3Astayturgid

---

## SSH to Termux

```bash
ssh s24    # or: ssh p7a
```

Requires `~/.ssh/termux_key` in Termux `authorized_keys` and Tailscale (or `adb forward tcp:8022 tcp:8022`). See [HACKING.md](HACKING.md) for `~/.ssh/config` (`IdentityAgent none` on phone hosts).

---

## Repo layout

```
stayturgid/
  README.md              ← you are here
  docs/README.md         ← doc index
  HACKING.md  HANDOFF.md
  termux/    ansible/    mac/
  tasker/    tasker-io/  autojs6/    obtainium/
  version.json
```

---

## Tested on

- Google Pixel 7a, Samsung Galaxy S24 (SM-S921U1), Android 16
- Shizuku thedjchi fork · Tasker 6.7.5-beta · AutoJs6 6.7.0 · Termux GitHub-debug stack
