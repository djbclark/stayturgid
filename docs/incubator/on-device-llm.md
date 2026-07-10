# On-device LLM for stayturgid (shell-gpt / local models)

**Status:** Incubator note (2026-07-09) — optional future spike; not implemented.  
**Location:** `docs/incubator/` (speculative). Production-adjacent UI/ADB notes
stay in `docs/research/`.  
**Audience:** [OPTIONS.md](../../OPTIONS.md) item **54** / track **E** when
deliberately picked — not default agent work.

## Recommendation

| Approach | Verdict for stayturgid |
|----------|------------------------|
| **shell-gpt + cloud API** (OpenAI/Anthropic) | Best *quality* for rare escalation; needs network + key; cost per call |
| **shell-gpt + local Ollama on phone** | Feasible on s24/p7a; **marginally useful** for short shell suggestions; not smart enough to own repair |
| **aider-chat on Termux** | **Reject** for this use case — tree-sitter aarch64 install pain; wrong tool (repo editing, not device shell) |

**Do not** put any LLM in the 5-minute Termux repair hot path. Deterministic `stayturgid-repair` + AutoJs6 catastrophic tap stay primary. LLM is an optional **escalation** after N failed STATUS cycles, with allowlisted commands and screen-control consent for any `input`.

## Would a local model actually be useful?

### Hardware budget (this fleet)

| Host | SoC | Typical RAM | Realistic local model |
|------|-----|-------------|------------------------|
| s24 (SM-S921U1) | Snapdragon 8 Gen 3 | 8 GB | Qwen2.5-Coder **1.5B–3B** Q4, or Llama 3.2 **3B** Q4 |
| p7a | Tensor G2 | 8 GB | Prefer **1.5B–3B**; 7B will thrash under daily-driver load |
| hd8 | Fire OS mid-range | low | **Skip** — no Termux→5555 loopback; keep Mac path |

Expect ~2–4 GB OS/apps already in use. A 3B Q4 model needs ~2 GB weights + KV; usable but competes with AutoJs6, Termux, and the user’s apps. Thermal throttling on long generations is normal.

### What phone-class models can do well

- Turn a **short, structured** prompt (“STATUS line + one dumpsys snippet → one `adb shell` command”) into a plausible next step
- Explain a failed command’s stderr in plain language
- Suggest which of a **fixed allowlist** to try next (`settings get`, `dumpsys`, `input keyevent HOME`, …)

Reported mobile speeds (order of magnitude, CPU/Adreno): **1–1.5B ~30+ tok/s**, **3B ~15–20 tok/s** — fine for a 1–3 command escalation, not for multi-minute agent loops.

### What they cannot reliably do

- Replace the deterministic repair checklist (sshd, 5555, a11y merge, Shizuku)
- Invent safe OEM-specific UI flows without hallucinated taps
- Run unattended multi-step “fix the phone” agents without a human in the loop
- Survive catastrophic path (5555 closed) — no shell for the model to use; AutoJs6 a11y remains mandatory

**Bottom line:** A **1.5B–3B coder/instruct** model on s24/p7a is smart enough to be a **bounded advisor** (propose allowlisted shell after deterministic heal fails). It is **not** smart enough to own self-heal or GUI automation. Prefer cloud models if you want higher-quality escalation; prefer local only for offline/privacy experiments.

## Suggested future spike (when track E is picked)

1. Termux: `pip install "shell-gpt[litellm]"`; optional `pkg install ollama` + `ollama pull qwen2.5-coder:1.5b`.
2. Dry-run: feed a captured unhealthy `STATUS` + dumpsys; require **propose-only** output.
3. If useful: `repair_escalate` flag → max 3 allowlisted commands → log to `~/.stayturgid/logs/`; never bypass `ScreenControlSession` for `input`.
4. Keep Mac/cloud as an alternative backend so phones are not required to host Ollama.

## Non-goals

- aider-chat as fleet heal
- Always-on Ollama in Termux:Boot (battery + RAM)
- LLM-driven Obtainium/Aurora/AutoJs6 drawer flows (deterministic on-device scripts own those)

**Mac vision gates (UI-TARS)** are separate from on-device LLM: see [VLM.md](../../VLM.md).
Screenshot verification on the Mac; not a replacement for Handsets navigation.
