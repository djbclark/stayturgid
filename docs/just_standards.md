# Just Command Standards

## Overview

This document defines the **standard interface** for all `just` recipes in the StayTurgid project. It enforces a **POSIX‑style positional‑argument** syntax while preserving backward compatibility via **legacy shims** and supporting **environment‑variable overrides** for global configuration.

## Goals

- **Uniformity**: All fleet recipes accept optional `host` and `scope` arguments in a consistent way.
- **Backward Compatibility**: Existing scripts that use the historic `just --set hosts … <recipe>` form continue to work through automatically generated _legacy_ recipes (`<name>-legacy`). These appear in `just --list`.
- **Configurability**: Every global variable (`hosts`, `scope`, `mac_site`, `venv`, `collections`, `deploy_args`, `deploy_scope_arg`, `limit_flag`) can be overridden via environment variables using `env_var_or_default`.

## Naming Conventions

- Private implementation recipes are prefixed with an underscore, e.g. `_deploy_impl`.
- Legacy shims are named `<recipe>-legacy` and simply invoke the private implementation.
- Public wrappers use the original recipe name with optional positional arguments, e.g. `deploy +host?: +scope?:`.

## Positional Wrappers

```just
# Example wrapper
deploy +host?: +scope?:
    @just --set hosts {{host}} {{ if scope != "" }} --set scope {{scope}} {{ endif }} deploy-legacy
```

- `+host?` and `+scope?` are optional. When omitted, the recipe falls back to any values supplied via environment variables.
- The wrapper forwards the values to the legacy shim which calls the private implementation.

## Environment Variable Overrides (Root justfile)

```just
hosts := env_var_or_default("hosts", "")
scope := env_var_or_default("scope", "full")
mac_site := env_var_or_default("MAC_SITE", "ansible/playbooks/control_node/site.yml")
venv := env_var_or_default("VENV", ".venv-test")
collections := env_var_or_default("COLLECTIONS", "android_common termux obtainium fdroid play")
deploy_args := env_var_or_default("DEPLOY_ARGS", if hosts == "" { "" } else { hosts })
deploy_scope_arg := env_var_or_default("DEPLOY_SCOPE_ARG", if scope == "full" { "" } else { "--scope " + scope })
limit_flag := env_var_or_default("LIMIT_FLAG", if hosts == "" { "" } else { "-l " + hosts })
```

- Any of these can be set in the shell before invoking `just`, e.g. `HOSTS=s24 just deploy`.

## Legacy Shims

- Appear in `just --list` and maintain the original recipe names with a `-legacy` suffix.
- Provide a smooth migration path for existing automation, CI pipelines, and documentation.

## Updating Existing Recipes

1. Rename the original recipe to a private implementation (`_<name>_impl`).
2. Add a legacy shim (`<name>-legacy`).
3. Add a positional wrapper (`<name> +host?: +scope?:`).

All fleet recipes have been refactored accordingly (see `just/fleet.just`).

## Future Contributions

- New recipes should follow the same three‑step pattern.
- Consult this document when adding or modifying fleet commands.

---

_This file is part of the repository and should be kept up‑to‑date._
