# Mac control-node Homebrew formulae

## `cfengine@3.27.1` — pinned to match the Termux fleet

The Mac control node talks to the fleet's Termux `cf-serverd` (via `cf-runagent`,
Tier 3a hail-mary recovery). Termux CFEngine is **3.27.1**. Homebrew-core's
`cfengine` formula tracks the latest (3.28.0+), and a newer control-node
CFEngine is one variable that can complicate the already-fragile 3.27↔newer
`cf-runagent`↔`cf-serverd` handshake.

To keep both ends on the **same** version we pin the Mac to CFEngine Core
**3.27.1** and prevent `brew upgrade` from bumping it.

`cfengine@3.27.1.rb` is the homebrew-core `cfengine` formula as it stood at
3.27.1 (`brew extract`), pointing at the official community dist tarball
(includes the `libntech` submodule — the GitHub git-archive tarball does not, so
a naive `@3.27` source build fails at `make install`).

### Install / re-pin

The control-node deploy applies this automatically: the `control_node` role's
`prereqs.yml` installs + pins `cfengine@3.27.1` (idempotent, macOS-only). That
runs via `just deploy-mac`, which is currently blocked by stayturgid#85 — until
that is fixed, apply it manually:

```bash
just cfengine-pin            # tap + install cfengine@3.27.1 + brew pin + drop plain cfengine
# or manually:
brew tap-new cfengine-local/cfengine 2>/dev/null || true
cp packaging/homebrew/cfengine@3.27.1.rb \
   "$(brew --repo cfengine-local/cfengine)/Formula/"
brew uninstall --ignore-dependencies cfengine 2>/dev/null || true
brew install cfengine-local/cfengine/cfengine@3.27.1
brew link --overwrite cfengine@3.27.1
brew pin cfengine@3.27.1
```

### Verify

```bash
cf-runagent --version      # => CFEngine Core 3.27.1  (matches Termux cf-serverd)
brew list --pinned | grep cfengine   # => cfengine@3.27.1
```

To intentionally move both ends later, bump the device CFEngine first, then
re-`brew extract` the matching Mac formula here and update the pin.
