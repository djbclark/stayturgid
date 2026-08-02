<!-- historical: production hostnames/IPs in this file are session records; see docs/architecture/multi-site-topology.md §4.1 for current example names -->

# Incubator — parked side projects

**Agents: do not implement anything under this tree** unless the operator
explicitly asks to revive a named project. These are not OPTIONS tracks and
must not appear in suggested agent order.

## What belongs here

Speculative or alternate architectures that are **interesting but not
production stayturgid**:

| Kind                              | Examples                                        |
| --------------------------------- | ----------------------------------------------- |
| Alternate control planes          | Inferno/Styx namespace, Plan 9port experiments  |
| Optional intelligence             | On-device / cloud LLM escalation (shell-gpt)    |
| Rejected-but-documented redesigns | “Replace Ansible with Fabric”, always-on Ollama |
| External idea dumps               | Operator uploads, Grok plans, one-off sketches  |

Each project gets a **subdirectory** (or a single note if tiny) with:

1. `README.md` or `analysis.md` — stayturgid verdict (worth it? battery? gaps)
2. Optional `plan-original.md` — unmodified source plan
3. Status line: **parked** / **rejected** / **revive only on ask**

## What does _not_ belong here

| Keep in…                              | Content                                                                                             |
| ------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `docs/research/`                      | Production-adjacent findings that agents **should** read (Handsets, Fire OS ADB, UI driver benches) |
| `docs/architecture/adr/`              | Accepted architectural decisions                                                                    |
| `docs/options.md` / `docs/handoff.md` | Active or latent fleet work                                                                         |
| `examples/`                           | Consumer Ansible playbooks (shipping patterns, not speculation)                                     |
| `human/`                              | Operator checklists and credentials notes                                                           |

## Layout

```
docs/research/experiments/
  README.md                 ← this file
  on-device-llm.md          ← track E research (parked spike; OPTIONS may still list 54)
  tablet-control-phone.md   ← hd8→s24 Termux:X11 + scrcpy native-res proposal (parked)
  inferno-styx/
    analysis.md             ← integration + battery verdict
    plan-original.md        ← full Inferno Termux fleet plan (do not execute)
```

| Note                                               | Status                                                                                |
| -------------------------------------------------- | ------------------------------------------------------------------------------------- |
| [tablet-control-phone.md](tablet-control-phone.md) | **Parked proposal** — control s24 from hd8 at tablet native res (Termux:X11 + scrcpy) |

## Candidates to add later (empty until real notes exist)

- `python-orchestrator/` — HANDOFF track D (Fabric/Invoke instead of Ansible)
- `plan9port/` — if anyone explores 9P without full Inferno
- `mdm-rejected/` — only if documenting _why_ MDM stays rejected (not a how-to)

Do not create empty folders in advance.

## Revive protocol

1. Operator names the project and asks to unpark.
2. Move or copy the note back toward `docs/research/` only if it becomes
   production-adjacent; otherwise keep working under `incubator/<name>/`.
3. Add an OPTIONS ID only after operator approval.
