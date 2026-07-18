#!/opt/homebrew/bin/bash
# cf-run — SSH-based replacement for cf-runagent on fleet devices.
# cf-serverd can't bind ports on Termux/Android (seccomp blocks).
# Runs cf-agent on one or more devices via SSH, bypassing cf-serverd.
#
# Usage: cf-run [HOSTS=oneui-device,stock-android-device,fireos-device] [BUNDLE=check_sshd] [CLASSES=android,linux]
#
# Default: runs all auto-repair bundles on all devices.

HOSTS="${1:-oneui-device stock-android-device fireos-device}"
BUNDLE="${BUNDLE:-stayturgid_heal}"
CLASSES="${CLASSES:-android,linux}"
CF="$HOME/.stayturgid/cfengine/stayturgid.cf"
CF_AGENT='/data/data/com.termux/files/usr/bin/cf-agent'

for host in $HOSTS; do
  echo "=== $host ==="
  ssh -o ConnectTimeout=8 -o BatchMode=yes "$host" \
    "export PATH=\"/data/data/com.termux/files/usr/bin:\$PATH\"; $CF_AGENT -Kf $CF -D $CLASSES 2>&1" |
    grep -E "^R:|^   error:|^   notice:" | head -10
  echo "---"
done
