#!/usr/bin/env bash
set -euo pipefail

# Compatibility verifier for the single canonical SecretSpec store.
# Secrets live in /var/db/sudo-secretspec and are reached only through the
# sudo-secretspec broker; there is no checkout source to copy or hash.
#
# `doctor` verifies the boundary itself (vault ownership and mode, sudoers
# policy, installed-artifact hashes). `check` verifies that every declared
# secret resolves. Both elevate through the NOPASSWD broker path internally,
# so neither is wrapped in sudo here.
#
# `check` is NOT read-only: with a missing secret it drops into the engine's
# interactive value-entry prompt. `< /dev/null` keeps it from blocking when
# this script runs unattended.

sudo-secretspec doctor
sudo-secretspec check --reason 'publish_secrets verification' </dev/null
printf '%s\n' 'SecretSpec boundary, canonical store permissions, and declared values all verify.'
