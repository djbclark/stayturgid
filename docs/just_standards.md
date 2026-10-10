# Just recipe conventions

How the fleet recipes in `justfile` and `just/*.just` take their targets.
Rewritten 2026-10-09 to match the code (issue #137 audit, finding A2); the
earlier text described wrappers, `--set` shims and uppercase overrides that
never existed. Per-recipe usage lives in [commands.md](commands.md).

## Variables

The root `justfile` reads three lowercase settings from the environment with
`env_var_or_default`: `hosts` (default empty, meaning the whole fleet),
`scope` (default `full`) and `devices_only` (default empty). `deploy_args`,
`deploy_scope_arg`, `deploy_devices_only_arg` and `limit_flag` are derived
from them and can also be set directly. `mac_site`, `venv` and `collections`
are constants. There is no `set export`, and uppercase names (`HOSTS=`,
`SCOPE=`) are not read: an exported `HOSTS` is ignored, and `just HOSTS=x`
fails with "variable `HOSTS` overridden on the command line but not present
in justfile".

## Public recipe, private implementation

Each fleet recipe is a public wrapper that re-invokes a private
implementation in a nested `just` process:

```just
_deploy_impl host="":
    python3 control/bin/deploy_fleet.py {{ deploy_args }} {{ host }} {{ deploy_scope_arg }} {{ deploy_devices_only_arg }}

deploy host="":
    @just _deploy_impl {{ host }}
```

The nested process re-reads the justfile and sees only the environment. A
positional argument and an environment variable reach it; `just --set hosts x
deploy` and `just hosts=x deploy` do not, so those forms run against the whole
fleet.

## Targeting hosts

1. **Positional:** `deploy`, `deploy-check`, `verify-drift`,
   `termux-pkg-upgrade`, `bootstrap-ssh`, `deploy-termux` and `firerpa-heal`
   take one host, e.g. `just deploy oneui-device`.
2. **Environment:** `hosts=<host> just <recipe>` works for every recipe that
   reads `hosts`, except `firerpa-heal`, which overwrites it with its own
   (empty) argument.
   Several hosts go in one quoted value:
   `hosts="oneui-device fireos-device" just deploy`. `firerpa-deploy` passes
   the value to `ansible-playbook -l`, so use commas there.
3. **`verify` and `verify-heal`** declare a positional parameter but ignore
   it; use the environment form.
4. **Scope:** `scope=<scope> just deploy <host>`.

Check any new form with `just --dry-run`, and dry-run the nested call it
prints as well, before documenting it.

## Legacy shims

`<name>-legacy` recipes (`deploy-legacy`, `verify-drift-legacy`, …) call the
private implementation with no host argument. They exist for old automation,
honour only the environment form, and are not a way to make `--set` work.

## Adding a recipe

1. Put the work in a private `_<name>_impl` recipe.
2. If it takes a host, declare `host=""` on both the wrapper and the
   implementation and pass it through (`@just _<name>_impl {{ host }}`).
3. Document the working forms in [commands.md](commands.md) after a dry run.
