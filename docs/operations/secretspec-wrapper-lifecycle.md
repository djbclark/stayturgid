# SecretSpec wrapper lifecycle

The root-owned `stayturgid-secretspec-wrapper.sh` is the controlled API for AI
and operator secret management on this Mac. It prevents callers from passing
arbitrary SecretSpec flags, paths, profiles, providers, or commands.

## Operations

The installed sudoers policy permits the wrapper to run as `root` for these
fixed lifecycle operations:

```text
source-add NAME DESCRIPTION
source-set NAME
source-delete NAME
source-get NAME
source-check
source-export
source-template-check
source-publish
```

`source-add` changes the canonical runtime schema and creates no secret value. It
also prints the required follow-up: mirror the declaration into the tracked
`site-private/secretspec.toml.example` from a task worktree, then release it.
The only live manifest and dotenv provider are under
`/var/db/stayturgid-secrets`; no runtime secret file remains in a Git checkout.
`source-template-check` reports only whether the runtime manifest and tracked
example are byte-identical; it never prints either file. `source-set` prompts
for the value without placing it in chat. `source-delete` removes the provider
value while retaining the declaration. `source-get` and `source-export` are
explicit audited reads. `source-publish` is retained as a compatibility
operation that repairs canonical-store ownership/modes; it no longer copies
between stores.

The wrapper also retains the `_secretspec`-only consumer operations:

```text
automation-env
firerpa-mcp-token
verify-sync DIGEST DIGEST
```

Unknown operations, undeclared names, malformed names, descriptions containing
newlines, caller-selected files/providers/profiles, and arbitrary commands are
rejected. Secret values are never written to logs by the wrapper. SecretSpec's
configured audit facility receives a fixed operation reason.

## Shell interface

The interactive `secretspec` function must call the root-owned wrapper for
lifecycle operations. `secretspec-vault` is reserved for the narrow
`_secretspec` consumer interface, and `secretspec-publish` is a compatibility
alias that validates the canonical store and declaration template.

Declarations and values are therefore changed through the wrapper rather than
by editing `secretspec.toml` or `.env` directly. The wrapper remains the policy
boundary, and `/var/db/stayturgid-secrets` is the single canonical live store.

## Applying safely

1. Install the root-owned wrapper from this repository at
   `/usr/local/libexec/stayturgid-secretspec-wrapper.sh` with mode `0755` and
   owner `root:wheel`.
2. Install `control/config/sudoers.d/secretspec` as `/etc/sudoers.d/secretspec`.
3. Validate with `visudo -c` before replacing the sudoers file.
4. Run focused wrapper tests and `source-check`.

The sudoers rule allows only this root-owned wrapper. It does not allow a
caller to run SecretSpec, a shell, `env`, or another executable as root.
