#!/usr/bin/env bash
set -euo pipefail

# Compatibility verifier for the single canonical SecretSpec store.
# Lifecycle operations now mutate /var/db/stayturgid-secrets directly through
# the root-owned wrapper; there is no checkout source to copy or hash.
WRAPPER=/usr/local/libexec/stayturgid-secretspec-wrapper.sh

sudo -n "$WRAPPER" source-publish
sudo -n "$WRAPPER" source-check
sudo -n "$WRAPPER" source-template-check
printf '%s\n' 'SecretSpec canonical store permissions, values, and tracked schema match.'
