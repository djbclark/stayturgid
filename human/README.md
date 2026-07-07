# Human handoff directory

This folder is for **tasks only a human can do** — credentials, on-device taps,
purchases, and go/no-go decisions. Agents should read `HANDOFF-HUMAN.md` before
asking you to do something, and read `RESPONSES.md` after you fill it in.

**Device preference for agents:** when picking one test host, use **s24** first,
**hd8** second, **p7a** third (see [HANDOFF.md](../HANDOFF.md) § Agent conventions).

## Workflow

1. Agent (or you) opens **`HANDOFF-HUMAN.md`** — current open items, prioritized.
2. You complete items and record outcomes in **`RESPONSES.md`** (create from
   `RESPONSES.md.example` if missing).
3. Tell the agent: *"Read human/RESPONSES.md"* — it continues automation.

For **what to do next** (agent work menus), see [OPTIONS.md](../OPTIONS.md) at repo root.

Do not put secrets in git. Use env vars, `~/.config/`, or placeholders in
`RESPONSES.md` and paste real values only in local files the agent is told to read.

## Files

| File | Who edits |
|------|-----------|
| `HANDOFF-HUMAN.md` | Agent maintains the task list |
| `RESPONSES.md.example` | Template (committed) |
| `RESPONSES.md` | **You** — gitignored if it contains secrets |
