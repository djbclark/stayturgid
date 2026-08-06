# Secretspec Secrets Management

This document outlines the `secretspec` enforcement architecture for the `stayturgid` fleet automation. Built across PRs [#244](https://github.com/djbclark/stayturgid/pull/244), [#245](https://github.com/djbclark/stayturgid/pull/245), [#246](https://github.com/djbclark/stayturgid/pull/246), and [#247](https://github.com/djbclark/stayturgid/pull/247), this system ensures that automation scripts and background tasks can access secrets securely, reliably, and strictly through the `secretspec` API boundary.

## 1. Rationale & Problem Statement

Historically, `secretspec.toml` was merely documentation for the `stayturgid` repository. Real code (like `site_contract/serverapps.py` or `reingest_soft_health.py`) bypassed it completely, manually parsing a legacy file located at `~/.config/stayturgid/observability.env`. 

This caused several issues:
- **Silently Empty Secrets:** Nothing automatically exported `secretspec` values into the ambient shell environment. If the legacy file went missing or was malformed, commands like `site-serverapps apply` could silently render and deploy empty passwords.
- **Architectural Drift:** Scripts directly accessed the file instead of honoring the `secretspec` contract, making secret rotation and auditing impossible.
- **Lack of Access Control:** The legacy `.env` file was accessible to any process running as the `operator` user. A rogue script or accidental command could easily read and exfiltrate the raw secrets file.

To solve this, we needed an enforcement boundary that prevents direct `.env` reads while still allowing unattended background tasks (like `launchd` jobs) to seamlessly resolve secrets.

## 2. Design Alternatives Considered

Several approaches were evaluated before settling on the current architecture:

- **1Password Service Account / Vault (Rejected):** While highly secure, moving to a 1Password Service Account replaces the `.env` file with a Service Account token on disk. This just moves the "confused deputy" problem rather than solving it (any script that reads the token can fetch the secrets). Additionally, it injects network latency and relies on 1Password uptime, which breaks local testing during network partitions.
- **SETENV Sudoers Rule (Rejected):** We considered allowing `operator` to run `secretspec` via `sudo` with the `SETENV` privilege to inject necessary variables. This was rejected because it allows the caller to inject arbitrary, potentially dangerous environment variables into the privileged `secretspec` process.
- **Whitelisting `env` in Sudoers (Rejected):** Whitelisting the bare `/usr/bin/env` binary in `sudoers` to run as `_secretspec` would allow the caller to execute *any* binary as `_secretspec`, entirely defeating the restriction boundary.
- **Dedicated System User + Sudo Wrapper (Chosen):** We created a dedicated, locked-down system user (`_secretspec`) that owns the synced secrets. The `operator` user is permitted via a strictly scoped `sudoers` rule to run exactly one root-owned wrapper script, which securely bakes in the required environment variables and executes `secretspec`.

## 3. Architecture as Built

The architecture relies on strict UNIX file permissions and a rigid privilege boundary:

1. **The `_secretspec` System User:** A dedicated macOS daemon user (UID 503, no login shell, hidden from the login screen) that acts as the vault guardian.
2. **The Secure Vault (`/var/db/stayturgid-secrets/`):** A directory owned by `_secretspec` with `0700` permissions. It contains the locked-down, synced copies of `secretspec.toml` and `.env`. The `operator` user cannot read this directory.
3. **The Root-Owned Wrapper (`/usr/local/libexec/stayturgid-secretspec-wrapper.sh`):** A `0755` script owned by `root:wheel` (so it cannot be modified by the operator). It securely sets `HOME` and `SECRETSPEC_PROVIDER` before executing the real `secretspec` binary.
4. **The Sudoers Rule (`/etc/sudoers.d/secretspec`):** A narrowly scoped rule that allows the `djbclark` (or `operator`) user to run *only* the wrapper script as `_secretspec` without a password.
5. **The Sync Mechanism (`publish_secrets.sh`):** A script that safely copies the operator's readable `~/ops/site-private/{.env,secretspec.toml}` into the locked `/var/db/` directory, adjusting ownership and performing hash-validation.

## 4. Install & Setup Instructions

If you are setting this up fresh on a new machine, follow this exact sequence:

**1. Create the `_secretspec` user and vault directory:**
```bash
sudo sysadminctl -addUser _secretspec -UID 503 -shell /usr/bin/false -home /var/empty
sudo defaults write /Library/Preferences/com.apple.loginwindow HiddenUsersList -array-add _secretspec
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
export HOME=/var/db/stayturgid-secrets
export SECRETSPEC_PROVIDER=dotenv
exec /opt/homebrew/bin/secretspec -f /var/db/stayturgid-secrets/secretspec.toml "$@"
EOF
sudo chmod 0755 /usr/local/libexec/stayturgid-secretspec-wrapper.sh
sudo chown root:wheel /usr/local/libexec/stayturgid-secretspec-wrapper.sh
```

**3. Validate and Install the Sudoers Rule:**
> [!WARNING]
> You **must** validate your sudoers file with `visudo -c` before installing it. A syntax error in `/etc/sudoers.d/` can completely lock you out of `sudo` machine-wide.

```bash
echo 'djbclark ALL=(_secretspec) NOPASSWD: /usr/local/libexec/stayturgid-secretspec-wrapper.sh' > /tmp/secretspec.tmp
sudo visudo -c -f /tmp/secretspec.tmp
# Ensure the output says "parsed OK" before continuing!
sudo cp /tmp/secretspec.tmp /etc/sudoers.d/secretspec
sudo chown root:wheel /etc/sudoers.d/secretspec
sudo chmod 0440 /etc/sudoers.d/secretspec
rm /tmp/secretspec.tmp
```

**4. Publish the Secrets:**
```bash
# This syncs your local site-private secrets into the vault
bash control/bin/publish_secrets.sh
```

## 5. Usage & Verification

### The Python Automation & Bash Alias
All Python automation scripts (like `ansible_exec.py`, `deploy_fleet.py`) have been updated to use the wrapper. 

For manual CLI usage, your `~/.bashrc` includes an alias so you can simply type:
```bash
secretspec run -- <command>
```
Under the hood, this expands to:
```bash
sudo -n -u _secretspec /usr/local/libexec/stayturgid-secretspec-wrapper.sh run -- <command>
```

### Functional Check
To manually verify the pipeline is working (without printing any secret values to your terminal), run this check to count the resolved environment variables:
```bash
sudo -n -u _secretspec /usr/local/libexec/stayturgid-secretspec-wrapper.sh run -- env | grep -c "="
```
It should return a number (e.g., `58`) indicating successful secret resolution.

### Negative Test
To ensure the isolation is working, verify that you (as a normal user) cannot read the vault:
```bash
ls -la /var/db/stayturgid-secrets
cat /var/db/stayturgid-secrets/secretspec.toml
```
Both commands should instantly fail with `Permission denied`.

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
