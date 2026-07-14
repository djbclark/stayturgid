# stayturgid CFEngine Build project

This directory is a [CFEngine Build (`cfbs`)](https://github.com/cfengine/cfbs)
project that produces the standalone CFEngine policy artifact deployed to Termux.
It intentionally does **not** build on the Masterfiles Policy Framework: Termux
executes the two explicit policy entry points with `cf-agent -f` and
`cf-serverd -f`, rather than running a CFEngine hub.

`policy/` is the source of truth. `out/` is generated and ignored by Git; normal
Ansible deploys use that generated artifact (check mode reads `policy/` only).

## Prerequisites

Install CFEngine Build with a supported Python. The current package supports
Python 3.5+, but on this Mac Python 3.12 is the known-compatible choice:

```bash
pipx install --python /opt/homebrew/bin/python3.12 'cfbs==5.5.6'
```

CFEngine Core (for `cf-promises` policy validation) is supplied by Homebrew:

```bash
brew install cfengine
```

## Build and validate

From the repository root:

```bash
just cfbs-validate
just cfbs-build
```

`cfbs-build` creates `device/termux/cfengine/out/masterfiles/`. The resulting
files retain the existing device paths:

- `stayturgid.cf`
- `cf-serverd.cf`
- `cf-runagent-wrapper.sh`

Do not run `cfbs install` or deploy this artifact as a CFEngine hub policy:
Android uses the explicitly invoked standalone files above. The Ansible
`termux_userland` role builds locally and deploys only this generated artifact.

## Updating policy

1. Edit a file under `policy/`.
2. Run `just cfbs-validate` and `just cfbs-build`.
3. Inspect `out/masterfiles/` and run the normal Ansible check/deploy gate.

The project has no remote CFBS modules. That is deliberate: the deployed policy
is small, Android/Termux-specific, and must remain reproducible without pulling
an unreviewed policy framework into a recovery channel.
