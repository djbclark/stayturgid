# UI-TARS-1.5-7B — local vision gates for Android screenshots

stayturgid uses **UI-TARS-1.5-7B** (ByteDance’s GUI-focused vision-language model) as an
**optional Mac-side screenshot verifier** during device QA. It does not drive phones
autonomously. It answers yes/no questions about PNGs from `adb exec-out screencap`
*before* or *after* high-stakes steps — for example: “Is Play Store set to **Don’t
auto-update apps**?” or “Is Aurora on do-not-auto-update?”

**Design principle:** Handsets + hierarchy selectors remain primary; VLM is the
**safety net** for brittle OEM screens (Fire Play Store account drawer, Aurora update
dialogs). Not used on Termux/AutoJs6 self-heal hot paths.

Related: [docs/research/mac-android-ui-automation.md](docs/research/mac-android-ui-automation.md) ·
[docs/research/fire-os-google-play.md](docs/research/fire-os-google-play.md) ·
`shared/mac/vlm_gate.py` · `mac/verify_play_autoupdate.py`

---

## When to use it

| Good fit | Poor fit |
|----------|----------|
| Confirm Play Store auto-update is off (hd8) | Every navigation tap in deploy |
| Disambiguate Aurora auto-update screenshot | Sub-second real-time control loops |
| Gate before typing in a filter/composer (future) | Termux repair / fleet_health_monitor |
| One screenshot → one JSON verdict (~10–20s Metal) | Unattended multi-step “agent” |

---

## Requirements

| Resource | Notes |
|----------|-------|
| **macOS** (recommended) | Apple Silicon uses Metal via `llama-server -ngl 99` |
| **RAM** | ~6 GB for Q4_K_M + mmproj; **16 GB** minimum; close heavy apps |
| **Disk** | ~6 GB under `~/.config/stayturgid/models/ui-tars-1.5-7b/` |
| **Homebrew** | `llama.cpp` (required), `ollama` (optional convenience) |
| **ADB + Handsets** | Play Store navigation uses `~/.handsets/hs` |

Pure CPU (`STAYTURGID_VLM_NGL=0`) works but is **very slow** (minutes per image).

---

## Quick start

### 1. One-time install

```bash
make vlm-install
```

Downloads GGUF + mmproj from [adriabama06/UI-TARS-1.5-7B-GGUF](https://huggingface.co/adriabama06/UI-TARS-1.5-7B-GGUF) (~5.9 GB).

### 2. Start the server (dedicated terminal)

```bash
make vlm-server
```

Wait for `UI-TARS server ready.` (20–60 s first load).

```bash
make vlm-check
curl -sf http://127.0.0.1:8081/health
```

Stop: `make vlm-stop`

### 3. Verify Play Store auto-update (hd8)

```bash
# terminal 1: make vlm-server
STAYTURGID_VLM=1 make verify-play-autoupdate HOSTS=hd8
```

Or after Google stack repair:

```bash
STAYTURGID_VLM=1 python3 mac/fix_hd8_google_stack.py hd8 --verify-autoupdate
```

Artifacts: `~/.config/stayturgid/artifacts/vlm-verify/<YYYY-MM-DD>/<host>/`

---

## How screenshots reach the model

```
device                         Mac
──────                         ───
adb exec-out screencap -p  →  PNG on disk
Handsets (parallel)        →  navigation only
                              │
                              ▼
                         sips -Z 720  (downscale)
                              │
                              ▼
                    POST /v1/chat/completions
                    (OpenAI-compatible llama-server :8081)
                              │
                              ▼
                         JSON { ok, confidence, notes }
```

Play Store navigation intentionally **does not** use `ScreenControlSession` — the
account drawer Settings row is unreliable under display inversion. Aurora checks in
`gui_audit.py` capture inside quiet screen-control sessions; VLM reads the PNG only.

---

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `STAYTURGID_VLM` | `0` | Enable vision gates |
| `STAYTURGID_VLM_STRICT` | `0` | Exit non-zero when server down or check fails |
| `STAYTURGID_VLM_PORT` | `8081` | `llama-server` port (`QSS_VLM_PORT` alias) |
| `STAYTURGID_VLM_TIMEOUT` | `900` | Seconds per inference |
| `STAYTURGID_VLM_MAX_WIDTH` | `720` | Downscale before encode |
| `STAYTURGID_VLM_NGL` | `99` on Darwin | Metal GPU layers |
| `STAYTURGID_VLM_MODEL_DIR` | `~/.config/stayturgid/models/ui-tars-1.5-7b` | Weights |

Logs: `~/.config/stayturgid/logs/ui-tars-server.log`

---

## Built-in check types

Defined in `shared/mac/vlm_gate.py` → `CHECK_PROMPTS`:

| Check | Use |
|-------|-----|
| `play_autoupdate_dont` | Play Store → Auto-update apps → Don’t auto-update selected |
| `aurora_autoupdate_dont` | Aurora Settings → Automatic updates → off |
| `no_gms_crash_dialog` | No GSF/GMS/Play “has stopped” dialog visible |

### Call sites

| Script | When |
|--------|------|
| `mac/verify_play_autoupdate.py` | Manual / `make verify-play-autoupdate` |
| `mac/fix_hd8_google_stack.py --verify-autoupdate` | After pin repair |
| `mac/gui_audit.py` | On `14_aurora_auto_updates.png` when `STAYTURGID_VLM=1` |

---

## Programmatic usage

```python
from pathlib import Path
import sys
sys.path.insert(0, "shared/mac")
import vlm_gate as vlm

gate = vlm.VlmGate(autostart=False)
ok, detail = gate.verify(Path("/tmp/shot.png"), "play_autoupdate_dont")
```

Smoke test: `make vlm-check`

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `vlm_unavailable` | `make vlm-server` in dedicated terminal |
| Navigation fails | Handsets up; scroll account drawer before Settings (see `play_store_autoupdate.py`) |
| Inference timeout | Metal on Mac; lower `STAYTURGID_VLM_MAX_WIDTH`; raise timeout |
| False negative | Read `notes` in JSON; retake after UI settle |

---

## Files

| Path | Role |
|------|------|
| `shared/mac/vlm_gate.py` | `VlmGate`, prompts, HTTP client |
| `shared/mac/play_store_autoupdate.py` | Play Store nav to auto-update screen |
| `mac/ui_tars_server.sh` | Start `llama-server` |
| `mac/vlm_install.sh` | Brew + model download |
| `mac/vlm_check.py` | Health smoke test |
| `mac/verify_play_autoupdate.py` | hd8 / Play auto-update CLI |

Model weights (not in git):

```
~/.config/stayturgid/models/ui-tars-1.5-7b/
  ByteDance-Seed_UI-TARS-1.5-7B-Q4_K_M.gguf
  mmproj-ByteDance-Seed_UI-TARS-1.5-7B.gguf
```

---

## Adding a new check

1. Add a prompt to `CHECK_PROMPTS` in `shared/mac/vlm_gate.py` (JSON-only reply).
2. Add validation in `VlmGate.verify()` if needed.
3. Capture a PNG from a known-good device state; test with `ask_image()` before live QA.
4. Document the check in this file.

Keep checks **narrow** — one screenshot, one question.
