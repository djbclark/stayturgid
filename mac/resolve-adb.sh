#!/usr/bin/env bash
# Compatibility shim — implementation lives in shared/mac/resolve-adb.sh
# shellcheck source=../shared/mac/resolve-adb.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../shared/mac" && pwd)/resolve-adb.sh"
