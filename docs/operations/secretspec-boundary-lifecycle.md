# SecretSpec boundary lifecycle

The `sudo-secretspec` companion is the controlled API for AI and operator secret
management on this Mac. It prevents callers from passing arbitrary SecretSpec
flags, paths, profiles, providers, or commands.

Secrets live in the canonical vault at `/var/db/sudo-secretspec`, owned by the
`_sudo_secretspec` service identity with mode `0700`. No runtime secret file
remains in a Git checkout.

## Operations

Every operation takes a short operational `--reason`. The protected audit ledger
stores only its SHA-256 digest, never the text and never a secret value.

```text
sudo-secretspec add NAME --reason WHY
sudo-secretspec set NAME --reason WHY
sudo-secretspec delete NAME --reason WHY
sudo-secretspec get NAME --reason WHY
sudo-secretspec check --reason WHY
sudo-secretspec export --reason WHY
sudo-secretspec template-check --reason WHY
sudo-secretspec run --reason WHY -- COMMAND [ARGS...]
sudo-secretspec doctor
```

`add` changes the runtime schema and creates no secret value; mirror the
declaration into the tracked `site-private/secretspec.toml.example` from a task
worktree, then release it. `set` prompts for the value without placing it in
chat. `delete` removes the provider value while retaining the declaration.
`get` and `export` are explicit audited reads. `template-check` reports only
whether the runtime manifest and the tracked declaration template are
byte-identical; it never prints either file. `doctor` verifies the boundary
itself — vault ownership and mode, sudoers policy, installed-artifact hashes —
and needs no reason because it reads no secret.

**Do not wrap these in `sudo`.** The companion elevates itself through the
NOPASSWD broker path. Wrapping it would run the _client_ as root, so a `run`
target would inherit root's environment and HOME instead of the caller's.

**`check` is not read-only.** With a missing secret it drops into the engine's
interactive value-entry prompt. Redirect stdin from `/dev/null` in any script,
or it blocks invisibly when stdout is redirected.

**`run` targets are audited by basename** and the broker refuses an argument
containing a path separator. Pass `python3 script.py`, not `./script.py`.

Unknown operations, undeclared names, malformed names, caller-selected
files/providers/profiles, and arbitrary commands are rejected.

## Retired: the `_secretspec` wrapper

Until 2026-08-15 this role was filled by a root-owned
`stayturgid-secretspec-wrapper.sh` running as a separate `_secretspec` service
account against a separate vault at `/var/db/stayturgid-secrets`, exposing
`source-*` lifecycle operations plus `automation-env`, `firerpa-mcp-token` and
`verify-sync`.

It was retired rather than repointed at the canonical vault, because it could
not have worked there: `_secretspec` cannot read a vault owned by
`_sudo_secretspec` with mode `0700`, and the wrapper's `sync_source` would have
chowned that vault away from its owner on the first `source-publish` — which
`publish_secrets.sh` called as its first action.

Consumers now build their argv through `control/lib/secretspec_exec.py`, which
still admits only `run -- ansible-playbook ...` and one named token fetch.

## Applying safely

1. Install the companion: `brew install djbclark/sudo-secretspec/sudo-secretspec`.
2. Install the boundary from a real TTY:
   `sudo-secretspec install --declarations <path>`. It authenticates every time
   (`timestamp_timeout=0`) and cannot prompt from a backgrounded process.
3. Confirm with `sudo-secretspec doctor` (expect exit 0, no findings).
4. Run `control/bin/publish_secrets.sh` to verify the boundary, the declared
   values, and the tracked schema together.

The sudoers rule allows only this project's root-owned broker. It does not allow
a caller to run SecretSpec, a shell, `env`, or another executable as root.
