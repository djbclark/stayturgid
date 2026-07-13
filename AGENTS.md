# stayturgid

Keeps wireless ADB (port 5555), Shizuku, and SSH alive on unrooted Android phones across reboots. Fleet: s24, p7a, hd8 managed via Ansible over Tailscale.

## Quick start

```bash
cd ~/stayturgid && git fetch origin --prune && git pull --ff-only origin master
make health && make firerpa-health
```

## Key commands

| Command | Purpose |
|---------|---------|
| `make deploy [HOSTS=s24]` | Full fleet deploy |
| `make deploy-check [HOSTS=s24]` | Dry-run deploy (CHECK=1) |
| `make verify [HOSTS=s24]` | Device tier checks |
| `make verify-drift [HOSTS=s24]` | Ansible-based drift detect |
| `make verify-heal [HOSTS=s24]` | Verify + auto-heal |
| `make health` | Fleet health summary + device error log |
| `make errors` | Show recent device errors (7 days) |
| `make firerpa-health` | FIRERPA fleet health |
| `make firerpa-heal --host s24` | Repair via FIRERPA gRPC |
| `make test` | Code-only tests (includes healing coverage check) |
| `make deploy-mac` | Mac workstation (brew, launchd) |
| `make ca-status` | SSH CA status/fingerprints |
| `make opencode-web-status` | OpenCode web UI status |
| `make hermes-status` | Hermes worktree status |
| `make vlm-check` | Check VLM server + cloud |
| `make landing-status` | Network landing page status |
| `make secretspec-check` | Verify all required secrets are set |

## Environment

- **Mac shell:** `/bin/bash` (dotfiles: `~/.bash_profile`, `~/.bashrc`)
- **FIRERPA venv:** Python 3.12 at `/tmp/lamda-venv` — `source /tmp/lamda-venv/bin/activate`
- **SSH CA:** `~/.ssh/stayturgid_ca` — `make ca-status`
- **OpenCode web:** http://100.113.53.87:4096
- **Secrets:** managed via `secretspec` (`brew install secretspec`). Spec at `secretspec.toml` (project root). All secrets defined there; run `make secretspec-check` before deploys.

## Fleet (s24, p7a, hd8)

| Device | Tailscale | USB Serial | SSH |
|--------|-----------|------------|-----|
| s24 | 100.123.218.30 | RFCX219CHKA | `ssh s24` |
| p7a | 100.65.230.108 | 35261JEHN12374 | `ssh p7a` |
| hd8 | 100.124.55.39 | GN43T503430603PS | `ssh hd8` |

## Conventions

- Use bash (not zsh). Termux has no zsh by default.
- Announce before device interaction: 🚨📱🚨 USING — host — why — ~N min
- Screen control requires `ScreenControlSession` (fail-closed).
- Accessibility is detection-only. Never `settings put` accessibility services automatically.
- Logging uses syslog severity levels (EMERG..DEBUG). See `control/lib/logging.py`.
- Every desired state gets a unique ID in `tests/healing_registry.json`. Pre-flight
  `make test` fails if a `must_cover` ID is missing from any healing mechanism.
- Follow multi-agent protocol at bottom of AGENTS.md (fetch-pull before edits).
- See full policies at `.cursor/rules/*.md`

## Handoff

Full details: `docs/handoff.md` (cold-start, architecture, known issues)
Ordered current work: `docs/plans/outstanding-fix-priorities-2026-07-13.md`
Open item status: `docs/options.md`
Session history: `docs/history/session-*.md`

## Multi-Agent Protocol

Before any edit: `git fetch origin --prune && git pull --ff-only origin master`.
Always commit and push when done. Leave no uncommitted changes.
If `git pull` fails with a merge conflict, STOP and report it.
Verify changes are yours before editing — if a file has unrelated modifications
from another agent, leave it alone and report it.
