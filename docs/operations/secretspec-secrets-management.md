# Secretspec Secrets Management

This document outlines the `secretspec` enforcement architecture for the `stayturgid` fleet automation. Built across PRs [#244](https://github.com/djbclark/stayturgid/pull/244), [#245](https://github.com/djbclark/stayturgid/pull/245), [#246](https://github.com/djbclark/stayturgid/pull/246), and [#247](https://github.com/djbclark/stayturgid/pull/247), this system ensures that automation scripts and background tasks access secrets reliably and strictly through the `secretspec` API boundary.

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

1. **The `_secretspec` System User:** A dedicated macOS daemon user (UID 503, no login shell, hidden from the login screen) that acts as the vault guardian.
2. **The Secure Vault (`/var/db/stayturgid-secrets/`):** A directory owned by `_secretspec` with `0700` permissions. It contains the locked-down, synced copies of `secretspec.toml` and `.env`.
3. **The Root-Owned Wrapper (`/usr/local/libexec/stayturgid-secretspec-wrapper.sh`):** A `0755` script owned by `root:wheel` (so it cannot be modified by the operator). Root-target calls expose the validated `source-add`, `source-set`, `source-delete`, `source-get`, `source-check`, `source-export`, and `source-publish` lifecycle operations. `_secretspec` calls expose only `automation-env`, `firerpa-mcp-token`, and `verify-sync`. It never forwards arbitrary `"$@"` to SecretSpec.
   _(Note: While the wrapper script itself is root-owned and untamperable, the `/opt/homebrew/bin/secretspec` binary it executes resides in a `djbclark`-owned Homebrew tree and is not tamper-proof. This is a residual same-admin limitation, not a claim of full operator isolation.)_
4. **The Sudoers Rule (`/etc/sudoers.d/secretspec`):** Two exact wrapper entries permit the `djbclark` user to invoke the same root-owned script as either `root` for lifecycle operations or `_secretspec` for consumer operations. The wrapper validates the operation and arguments; sudoers does not permit arbitrary commands.
5. **The Sync Mechanism:** Wrapper mutations copy the fixed source manifest and `.env` into the locked `/var/db/` vault with owner-only modes, while `verify-sync` checks hashes and permissions.

## 4. Install & Setup Instructions

> [!IMPORTANT]
> **Prerequisites:** The commands below assume you are running them from the `stayturgid` checkout root and that your private site data is checked out at `~/ops/site-private`.

If you are setting this up fresh on a new machine, follow this exact sequence:

**1. Create the `_secretspec` user and vault directory:**

```bash
# Create the service account (auto-assigned uid 503, verify with `id _secretspec`)
sudo sysadminctl -addUser _secretspec -fullName "Secretspec Service Account" -home /var/empty -shell /usr/bin/false
sudo dscl . -create /Users/_secretspec IsHidden 1

# Setup the secure vault directory
sudo mkdir -p /var/db/stayturgid-secrets
sudo chown _secretspec /var/db/stayturgid-secrets
sudo chmod 0700 /var/db/stayturgid-secrets
```

**2. Create the Root-Owned Wrapper Script:**

```bash
sudo mkdir -p /usr/local/libexec
sudo tee /usr/local/libexec/stayturgid-secretspec-wrapper.sh > /dev/null << 'EOF'
#!/bin/bash
set -euo pipefail
if [ "$#" -ne 1 ]; then exit 2; fi
export HOME=/var/db/stayturgid-secrets
export SECRETSPEC_PROVIDER=dotenv
export SECRETSPEC_FILE=/var/db/stayturgid-secrets/secretspec.toml
unset SECRETSPEC_PROFILE SECRETSPEC_SCOPE SECRETSPEC_REASON DYLD_LIBRARY_PATH DYLD_INSERT_LIBRARIES
case "$1" in
  automation-env) exec /opt/homebrew/bin/secretspec -f "$SECRETSPEC_FILE" export --format json ;;
  firerpa-mcp-token) exec /opt/homebrew/bin/secretspec -f "$SECRETSPEC_FILE" get firerpa_mcp_token ;;
  *) exit 2 ;;
esac
EOF
sudo chmod 0755 /usr/local/libexec/stayturgid-secretspec-wrapper.sh
sudo chown root:wheel /usr/local/libexec/stayturgid-secretspec-wrapper.sh
```

**3. Validate and Install the Sudoers Rule:**

> [!WARNING]
> You **must** validate your sudoers file with `visudo -c` before installing it. A syntax error in `/etc/sudoers.d/` can completely lock you out of `sudo` machine-wide.

```bash
TMPFILE=$(mktemp)
echo 'djbclark ALL=(_secretspec) NOPASSWD: /usr/local/libexec/stayturgid-secretspec-wrapper.sh' > "$TMPFILE"
sudo visudo -c -f "$TMPFILE"
# Ensure the output says "parsed OK" before continuing!
sudo install -o root -g wheel -m 0440 "$TMPFILE" /etc/sudoers.d/secretspec
rm "$TMPFILE"
```

**4. Publish the Secrets:**

```bash
# This syncs your local site-private secrets into the vault
bash control/bin/publish_secrets.sh
```

## 5. Usage & Verification

### Lifecycle CLI and Python Automation

The interactive `secretspec` function routes lifecycle requests through the
root-owned wrapper:

```bash
secretspec add RESEND_API_KEY --description "Resend API key for outbound email"
secretspec set RESEND_API_KEY       # prompts without echoing the value
secretspec get RESEND_API_KEY
secretspec delete RESEND_API_KEY
secretspec check
secretspec export
secretspec publish
```

Declarations and provider values are changed through the wrapper. `source-add`
validates the declaration name and description; `source-set` and
`source-delete` validate that the name is declared. Direct caller-selected
files, providers, profiles, arbitrary commands, and shell interpreters are not
accepted.

Fleet automation still uses the two `_secretspec` consumer operations:

```bash
sudo -n -u _secretspec /usr/local/libexec/stayturgid-secretspec-wrapper.sh automation-env
sudo -n -u _secretspec /usr/local/libexec/stayturgid-secretspec-wrapper.sh firerpa-mcp-token
```

The first returns JSON to the checked-in `control/lib/secretspec_env_exec.py`,
which validates it and `exec`s the Ansible target as `djbclark`; it does not use
shell `eval`.

### Functional Check

To manually verify the pipeline without printing secret values, run the
non-secret drift check first:

```bash
python3 control/bin/verify_secretspec_sync.py \
  "${OPS_ROOT:-$HOME/ops}/site-private" /var/db/stayturgid-secrets
```

A source/vault hash mismatch, symlink, missing file, wrong mode, or wrong vault
permissions exits nonzero. `publish_secrets.sh` performs the same check after
publishing and must be run after every source change. Do not bypass this check
or add secret values to logs.

### Negative Test

To verify that discretionary filesystem permission enforcement is working for a regular non-sudo process, run the following:

```bash
ls -la /var/db/stayturgid-secrets
cat /var/db/stayturgid-secrets/secretspec.toml
```

Both commands should instantly fail with `Permission denied`. _(Note: This demonstrates discretionary permission enforcement for ordinary processes; it is not a comprehensive security guarantee against a root-capable user)._

### Updating Secrets

Whenever you modify your local `site-private/.env` or `secretspec.toml`, you must run `bash control/bin/publish_secrets.sh` to sync the changes into the locked `/var/db/` vault.

## 6. Two Coexisting Patterns

> [!NOTE]
> This locked-down `_secretspec` boundary is specific to the `stayturgid` fleet automation.
>
> A simpler pattern (direct `secretspec run --` executed as the operator) is used elsewhere on this machine (e.g., the `hermes` gateway). This is **not** wrong—it just operates in a different, lower-stakes context that doesn't require strict privilege separation. There is no requirement for every service on the machine to migrate to the `_secretspec` pattern.

## 7. Known Gotchas (Lessons Learned)

During the build process, a few critical lessons emerged:

- **`$HOME` overrides during `sudo -u`:** By default, `sudo -u _secretspec` leaves the `$HOME` environment variable pointing to the calling user's home directory (e.g., `/Users/operator`). Since the `_secretspec` user has a synthetic home (`/var/empty`), this broke `secretspec`'s attempt to look up its global config or write audit logs. The wrapper script explicitly exports `HOME=/var/db/stayturgid-secrets` to fix this.
- **Sudoers scoping with `env`:** You cannot scope a sudoers rule to a script if the invocation starts with `env` (e.g., `sudo -u _secretspec env ...`). `sudo` evaluates the command as `/usr/bin/env` rather than the target script, causing a permission denial. This is exactly why the wrapper script exists—it bakes the necessary environment variables internally so the caller doesn't have to use `env`.

## 8. Continuous Integration Note

> [!WARNING]
> Real GitHub Actions CI was unavailable during the entire build of this feature (due to an account-wide billing/spending-limit block resetting 2026-08-31).
>
> As a result, PRs #245-#247 were merged based strictly on thorough local `just test` verification. While robust, there is no clean CI-verified trail in GitHub for this specific work. If you are reading this and CI is back online, keep this in mind when diagnosing any edge cases or regressions related to secret resolution.
