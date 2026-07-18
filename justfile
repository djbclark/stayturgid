# stayturgid — operator commands (run `just` or `just --list`).
#
# Variables (optional on most recipes):
#   hosts=s24       Limit to one or more inventory hosts: just deploy hosts=s24 hd8
#   scope=full      Deploy scope: full | fdroid | play | app-stores
#
# Quick start:
#   just help           → show this listing
#   just check          → syntax / import checks
#   just test           → full test suite
#   just --set hosts s24 deploy  → fleet deploy

set shell := ["bash", "-uc"]

repo := justfile_directory()
export STAYTURGID_ROOT := repo
ansible_playbook := "python3 control/bin/ansible_exec.py ansible-playbook"

hosts := env_var_or_default("hosts", "")
scope := env_var_or_default("scope", "full")

deploy_args := env_var_or_default("deploy_args", if hosts == "" { "" } else { hosts })
deploy_scope_arg := env_var_or_default("deploy_scope_arg", if scope == "full" { "" } else { "--scope " + scope })
limit_flag := env_var_or_default("limit_flag", if hosts == "" { "" } else { "-l " + hosts })

mac_site := "ansible/playbooks/control_node/site.yml"
venv := ".venv-test"
collections := "android_common termux obtainium fdroid play"

import "just/fleet.just"
import "just/services.just"
import "just/tests.just"
import "just/cfengine.just"

# Show available recipes (default).
help:
    @just --justfile "{{ repo }}/justfile" --list
