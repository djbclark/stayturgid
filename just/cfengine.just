# CFEngine Build project commands. Policy logic remains in device/termux/cfengine.

cfbs-validate:
    cd device/termux/cfengine && cfbs validate
    cf-promises -f "{{ repo }}/device/termux/cfengine/policy/stayturgid.cf"
    cf-promises -f "{{ repo }}/device/termux/cfengine/policy/cf-serverd.cf"

cfbs-build: cfbs-validate
    cd device/termux/cfengine && cfbs build
    diff -r --exclude=cfbs.json device/termux/cfengine/policy device/termux/cfengine/out/masterfiles

# Run CFEngine repair bundles on device(s) via SSH replacement for cf-runagent.
# cf-serverd can't bind ports on Termux/Android (seccomp blocks listen).
# Usage: just cf-run [hosts=s24,p7a,hd8]
cf-run:
    @if [ "{{ hosts }}" = "" ]; then for h in s24 p7a hd8; do echo "=== $h ==="; ssh -o ConnectTimeout=8 -o BatchMode=yes "$h" "export PATH=/data/data/com.termux/files/usr/bin:\$PATH; /data/data/com.termux/files/usr/bin/cf-agent -Kf ~/.stayturgid/cfengine/stayturgid.cf -D android,linux 2>&1" | grep -E "^R:|^   error:" | head -10; echo "---"; done; else ssh -o ConnectTimeout=8 "{{ hosts }}" "export PATH=/data/data/com.termux/files/usr/bin:\$PATH; /data/data/com.termux/files/usr/bin/cf-agent -Kf ~/.stayturgid/cfengine/stayturgid.cf -D android,linux 2>&1" | grep -E "^R:|^   error:" | head -15; fi
