# Secretspec Secrets Management

This document outlines the `secretspec` enforcement architecture for the `stayturgid` fleet automation. Built across PRs [#244](https://github.com/djbclark/stayturgid/pull/244), [#245](https://github.com/djbclark/stayturgid/pull/245), [#246](https://github.com/djbclark/stayturgid/pull/246), and [#247](https://github.com/djbclark/stayturgid/pull/247), this system ensures that automation scripts and background tasks access secrets reliably and strictly through the `secretspec` API boundary.

> [!IMPORTANT]
> **The `_secretspec` wrapper described in sections 1-2 and 7 was retired on
> 2026-08-15.** Its role is now filled by the `sudo-secretspec` companion
> against the canonical vault at `/var/db/sudo-secretspec`. Sections 3-5 have
> been updated to the current architecture; sections 1-2 and 7 are kept as the
> historical design record and describe a boundary that no longer exists.
>
> For day-to-day operation see
> [`secretspec-boundary-lifecycle.md`](secretspec-boundary-lifecycle.md).

## 1. Rationale & Problem Statement

Historically, `secretspec.toml` was merely documentation for the `stayturgid` repository. Real code (like `site_contract/serverapps.py` or `reingest_soft_health.py`) bypassed it completely, manually parsing a legacy file located at `~/.config/stayturgid/observability.env`.

This caused several issues:

- **Silently Empty Secrets:** Nothing automatically exported `secretspec` values into the ambient shell environment. If the legacy file went missing or was malformed, commands like `site-serverapps apply` could silently render and deploy empty passwords.
- **Architectural Drift:** Scripts directly accessed the file instead of honoring the `secretspec` contract, making secret rotation and auditing impossible.
- **Accidental Reads & Lack of Auditing:** The legacy `.env` file was readable by any ordinary process running as the `operator` user with zero friction and zero logging.

**Important Threat Model Note:** This design does _not_ protect against a compromised or malicious `djbclark` session. A same-UID process can invoke any operation granted to that UID, and the operator can use broader administrative access outside this boundary. The enforceable guarantee is that the passwordless wrapper is a fixed, audited SecretSpec lifecycle API rather than a general CLI passthrough. It validates names and descriptions, fixes all paths/providers, rejects arbitrary commands and caller-selected selectors, and separates root lifecycle operations from `_secretspec` consumer operations.

What this architecture actually achieves is:

1. Preventing **accidental** or routine direct reads by ordinary, non-sudo processes.
2. Enforcing a narrow operation boundary for the passwordless wrapper rather than forwarding arbitrary SecretSpec arguments.
3. Creating an audit trail via `secretspec`'s own audit logging for deliberate access.
4. Keeping the residual same-UID limitation explicit instead of claiming process-level isolation that UNIX credentials cannot provide.

## 2. Design Alternatives Considered

When designing this boundary, we evaluated several approaches. The core constraint is that **no UNIX permission scheme can protect a secret from arbitrary code running as the same admin who has full `sudo` privileges to bypass it.** We optimized for architectural enforcement and accidental-read protection, rather than an impossible comprehensive security guarantee against the operator.

- **1Password Service Account / Vault (Rejected):** While highly secure, moving to a 1Password Service Account replaces the `.env` file with a Service Account token on disk. This just moves the "confused deputy" problem rather than solving it. Additionally, it injects network latency and relies on 1Password uptime, which breaks local testing during network partitions.
- **SETENV Sudoers Rule (Rejected):** We considered allowing `operator` to run `secretspec` via `sudo` with the `SETENV` privilege to inject necessary variables. This was rejected because it allows the caller to inject arbitrary, potentially dangerous environment variables into the privileged `secretspec` process.
- **Whitelisting `env` in Sudoers (Rejected):** Whitelisting the bare `/usr/bin/env` binary in `sudoers` to run as `_secretspec` would allow the caller to execute _any_ binary as `_secretspec`, entirely defeating the restriction boundary.
- **Dedicated System User + Sudo Wrapper (Chosen):** We created a dedicated, locked-down system user (`_secretspec`) that owns the synced secrets. The `operator` user is permitted via a strictly scoped `sudoers` rule to run exactly one wrapper script, which securely bakes in the required environment variables.

## 3. Architecture as Built

The architecture relies on strict UNIX file permissions and a rigid privilege boundary:

1. **The `_sudo_secretspec` System User:** A dedicated macOS daemon user (UID 499, no login shell) that owns the vault and under whose identity the privileged broker reads it.
2. **The Canonical Store (`/var/db/sudo-secretspec/`):** A directory owned by `_sudo_secretspec` with `0700` permissions. It is the sole store for `secretspec.toml` and `.env` — declarations and values alike. Nothing is tracked in Git; the broker is the single source of truth and resolves everything from this store automatically, with no manifest path for any caller to know or specify.
3. **The Root-Owned Broker (`/usr/local/libexec/sudo-secretspec`):** Owned by `root:wheel` so it cannot be modified by the operator. It exposes a fixed set of audited operations against the canonical store and never forwards arbitrary arguments to SecretSpec. Every operation carries a caller-supplied reason; the hash-chained audit ledger records only its SHA-256 digest.
4. **The Public Client (`sudo-secretspec`):** Elevates itself to the broker through the NOPASSWD sudoers path, so callers never wrap it in `sudo`. For `run`, it fetches the environment from the broker and then `exec`s the target as the _invoking_ user, purging every `SECRETSPEC_*` variable first.
5. **The Sudoers Rule (`/etc/sudoers.d/sudo-secretspec`):** Permits `djbclark` to invoke only this project's broker, and only for its allowlisted operations. It does not permit arbitrary commands.
6. **No tracked schema.** An earlier design mirrored declarations into a Git-tracked `site-private/secretspec.toml.example` for review, with `sudo-secretspec template-check` diffing it against the runtime manifest. That file (and the `stayturgid`/`site-djbclark` symlinks to it) were retired 2026-08-16 — `add`/`set`/`check`/`schema` against the runtime manifest are now the only record, and `template-check` is no longer part of the routine flow.

### 3.1 Notable declarations

Most secrets are self-explanatory from their name. Two aren't, and their
rationale would otherwise have lived only in the deleted tracked file:

- **`ATLASSIAN_CFENGINE_API_TOKEN`** — Atlassian API token for
  `northerntech.atlassian.net` (CFEngine's public Jira, project CFE); used to
  file and update tickets for the upstream CFEngine/libntech contributions.
  The account is a Google SSO login with no password, so a token is the only
  way to authenticate. Basic auth pairs it with the account's email address.
- **`FIRERPA_MCP_TOKEN`** — bearer token authenticating clients of the
  FIRERPA MCP server (`com.stayturgid.firerpa-mcp`) on the tailnet. Required:
  `firerpa_mcp.py` refuses to start its HTTP transport without it, after
  running with no authentication at all from 2026-08-01 to 2026-08-15 because
  the token was never declared anywhere.

## 4. Install & Setup Instructions

> [!IMPORTANT]
> **Prerequisites:** The commands below assume you are running them from the `stayturgid` checkout root and that your private site data is checked out at `~/ops/site-private`.

**1. Install the companion:**

```bash
brew install frdminc/sudo-secretspec/sudo-secretspec
```

**2. Install the boundary, from a real TTY:**

```bash
sudo-secretspec install
```

`--declarations` is optional — omit it and the installer auto-detects or
prompts. There is no tracked declarations file to point it at; the vault is
the only source of truth. It creates the service identity and the vault,
writes the root-owned config and sudoers drop-in, and records a manifest of
everything it installed. Add `--adopt-existing` to take over an existing
vault instead of creating one.

> [!WARNING]
> Without `--adopt-existing`, `install` truncates `<vault>/.env`. Against a vault
> holding real secrets that is total loss. Pass the flag whenever a vault
> already exists.

It authenticates every time (`timestamp_timeout=0`) and cannot prompt from a
backgrounded process, so it must not be run from a script or an agent session.

**3. Verify the boundary and the canonical store:**

```bash
sudo-secretspec doctor          # expect exit 0, no findings
bash control/bin/publish_secrets.sh
```

## 5. Usage & Verification

### Lifecycle CLI and Python Automation

```bash
sudo-secretspec add RESEND_API_KEY --description 'what it is' --reason 'declare outbound email key'
sudo-secretspec set RESEND_API_KEY --reason 'rotate outbound email key'   # prompts, no echo
sudo-secretspec get RESEND_API_KEY --reason 'debug outbound email'
sudo-secretspec delete RESEND_API_KEY --reason 'retire outbound email key'
sudo-secretspec check --reason 'routine verification' </dev/null
sudo-secretspec export --reason 'routine verification'
```

Declarations and provider values are changed through the broker. `add` validates
the declaration name and description; `set` and `delete` validate that the name
is declared. Caller-selected files, providers, profiles, arbitrary commands, and
shell interpreters are not accepted.

> [!WARNING]
> `check` is **not** read-only. With a missing secret it drops into the engine's
> interactive value-entry prompt; with stdout redirected that prompt is
> invisible and the command simply hangs. Always redirect stdin from
> `/dev/null` when scripting it.

Fleet automation builds its argv through `control/lib/secretspec_exec.py`, which
admits only the approved Ansible form and one named token fetch:

```bash
sudo-secretspec run --reason 'stayturgid approved ansible automation' -- ansible-playbook ...
sudo-secretspec get FIRERPA_MCP_TOKEN --reason 'stayturgid firerpa mcp bearer token'
```

`run` `exec`s the Ansible target as `djbclark` with a writable HOME; it does not
use shell `eval`. Targets are audited by basename, so pass a bare executable
name rather than a path.

### Functional Check

To manually verify the pipeline without printing secret values, run:

```bash
bash control/bin/publish_secrets.sh
```

A boundary defect or a SecretSpec validation failure exits nonzero. No secret
value is printed by the verifier.

### Negative Test

To verify that discretionary filesystem permission enforcement is working for a regular non-sudo process, run the following:

```bash
ls -la /var/db/sudo-secretspec
cat /var/db/sudo-secretspec/secretspec.toml
```

Both commands should instantly fail with `Permission denied`. _(Note: This demonstrates discretionary permission enforcement for ordinary processes; it is not a comprehensive security guarantee against a root-capable user)._

### Updating Secrets

Whenever declarations or provider values change, they go through the broker
directly (`sudo-secretspec add`/`set`/`delete`) and land in the canonical
`/var/db/sudo-secretspec` store immediately — there is no tracked file to
mirror the change into and no release step required. Run `publish_secrets.sh`
afterward as a sanity check that the boundary is still healthy.

## 6. One Pattern, No Exceptions

Every consumer on this machine goes through `sudo-secretspec`. An earlier
design permitted plain `secretspec run --` for lower-stakes, non-privilege-
separated consumers (e.g. the `hermes` gateway); that exception was retired
2026-08-16 along with the tracked-declarations file it also depended on.

## 7. Known Gotchas (Lessons Learned)

> [!NOTE]
> Historical. Both gotchas below are properties of the retired `_secretspec`
> wrapper and no longer apply: the `sudo-secretspec` client is never invoked
> through `sudo -u`, so neither the `$HOME` override nor the `env` scoping
> problem can arise. Kept because they explain why the wrapper looked the way
> it did.

During the build process, a few critical lessons emerged:

- **`$HOME` overrides during `sudo -u`:** By default, `sudo -u _secretspec` leaves the `$HOME` environment variable pointing to the calling user's home directory (e.g., `/Users/operator`). Since the `_secretspec` user has a synthetic home (`/var/empty`), this broke `secretspec`'s attempt to look up its global config or write audit logs. The wrapper script explicitly exports `HOME=/var/db/stayturgid-secrets` to fix this.
- **Sudoers scoping with `env`:** You cannot scope a sudoers rule to a script if the invocation starts with `env` (e.g., `sudo -u _secretspec env ...`). `sudo` evaluates the command as `/usr/bin/env` rather than the target script, causing a permission denial. This is exactly why the wrapper script exists—it bakes the necessary environment variables internally so the caller doesn't have to use `env`.

## 8. Continuous Integration Note

> [!WARNING]
> Real GitHub Actions CI was unavailable during the entire build of this feature (due to an account-wide billing/spending-limit block resetting 2026-08-31).
>
> As a result, PRs #245-#247 were merged based strictly on thorough local `just test` verification. While robust, there is no clean CI-verified trail in GitHub for this specific work. If you are reading this and CI is back online, keep this in mind when diagnosing any edge cases or regressions related to secret resolution.
