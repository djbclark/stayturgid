# Human handoff directory

Tasks **only a human can do** — credentials, on-device confirmation, deploy
approval. Agents read **`HANDOFF-HUMAN.md`** before asking you to act; you record
outcomes in **`RESPONSES.md`**.

**Device preference for agents:** **s24** → **hd8** → **p7a** when one host suffices
([docs/handoff.md](../docs/handoff.md) § Agent conventions).

## Workflow

1. Open **`HANDOFF-HUMAN.md`** — prioritized operator checklist + session notes.
2. Complete items; record in **`RESPONSES.md`** (from `RESPONSES.md.example`).
3. Tell the agent: *"Read human/RESPONSES.md"* — it continues automation.

Agent work menu: [docs/options.md](../docs/options.md). Do not put secrets in git.

## Files

| File | Who edits | In git |
|------|-----------|--------|
| `HANDOFF-HUMAN.md` | Agent (task list, session notes) | yes |
| `RESPONSES.md.example` | Template | yes |
| `RESPONSES.md` | **You** (outcomes, approvals) | gitignored |
