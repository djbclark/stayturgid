#!/usr/bin/env bash
# Tier (c): device tests — STRICTLY read-only / non-destructive.
# (fleet-health.sh is the ops tool and invokes the self-heal; this does not.)
#
# Usage: tests/test-device.sh [--ansible-check] [host ...]   (default: s24 p7a)
#   --ansible-check   also run the Ansible playbook in --check --diff mode
#                     (a dry run: reports drift, changes nothing — termux_pkg
#                     honors check mode, verified by tests/test-unit.sh)
set -u
cd "$(dirname "$0")/.." || exit 2
. tests/lib.sh

ANSIBLE_CHECK=0
HOSTS=()
for a in "$@"; do
    case "$a" in
        --ansible-check) ANSIBLE_CHECK=1 ;;
        *) HOSTS+=("$a") ;;
    esac
done
[ "${#HOSTS[@]}" -eq 0 ] && HOSTS=(s24 p7a)

for host in "${HOSTS[@]}"; do
    # One SSH round trip gathers everything (read-only probes only).
    report="$(ssh -o BatchMode=yes -o ConnectTimeout=10 -o LogLevel=ERROR "$host" 'bash -s' <<'REMOTE' 2>/dev/null
export PATH=/data/data/com.termux/files/usr/bin:$PATH
export TMPDIR=/data/data/com.termux/files/usr/tmp   # adb needs a writable TMPDIR
echo "ssh=ok"
pgrep -x sshd >/dev/null 2>&1 && echo "sshd=ok" || echo "sshd=down"
pgrep -f 'start-adb\.sh' >/dev/null 2>&1 && echo "bootloop=ok" || echo "bootloop=down"
pid=$(cat ~/.repair-bridge.pid 2>/dev/null)
if [ -n "$pid" ] && [ -d "/proc/$pid" ] && grep -q repair-bridge "/proc/$pid/cmdline" 2>/dev/null; then
    echo "bridge=ok"
else
    echo "bridge=down"
fi
# </dev/null everywhere: adb otherwise slurps the rest of this bash -s script
adb connect localhost:5555 >/dev/null 2>&1 </dev/null
uid=$(adb -s localhost:5555 shell id -u 2>/dev/null </dev/null | tr -d "\r")
[ "$uid" = "2000" ] && echo "shell5555=ok" || echo "shell5555=down"
last=$(grep "\[repair\]" /sdcard/stayturgid_watchdog.log 2>/dev/null | tail -1 | cut -d" " -f1,2)
if [ -n "$last" ]; then
    age=$(( $(date +%s) - $(date -d "$last" +%s 2>/dev/null || echo 0) ))
    [ "$age" -ge 0 ] && [ "$age" -lt 2700 ] && echo "repairlog=fresh" || echo "repairlog=stale($age s)"
else
    echo "repairlog=missing"
fi
batt=$(termux-battery-status 2>/dev/null | grep -o '"percentage": *[0-9]*' | grep -o '[0-9]*' || true)
[ -n "$batt" ] && echo "battery=${batt}" || echo "battery=unknown"
for f in stayturgid-repair.sh repair-bridge.sh claude-presence.sh check-repo-version.sh stayturgid-battery-alarm.sh; do
    printf 'md5 %s %s\n' "$f" "$(md5sum "$HOME/$f" 2>/dev/null | cut -d" " -f1)"
done
REMOTE
)"
    if ! printf '%s' "$report" | grep -q '^ssh=ok'; then
        tap_fail "$host: SSH reachable"
        continue
    fi
    tap_ok "$host: SSH reachable"

    for probe in sshd bootloop bridge shell5555; do
        val="$(printf '%s\n' "$report" | sed -n "s/^${probe}=//p")"
        case "$probe:$val" in
            sshd:ok)      tap_ok "$host: sshd running" ;;
            sshd:*)       tap_fail "$host: sshd running" "$val" ;;
            bootloop:ok)  tap_ok "$host: Termux boot loop running" ;;
            bootloop:*)   tap_fail "$host: Termux boot loop running" "$val" ;;
            bridge:ok)    tap_ok "$host: repair bridge alive (pidfile)" ;;
            bridge:*)     tap_todo_fail "$host: repair bridge alive (pidfile)" "expected until post-fix redeploy + reboot" ;;
            shell5555:ok) tap_ok "$host: privileged shell on localhost:5555" ;;
            shell5555:*)  tap_fail "$host: privileged shell on localhost:5555" "$val" ;;
        esac
    done

    val="$(printf '%s\n' "$report" | sed -n 's/^repairlog=//p')"
    [ "$val" = "fresh" ] && tap_ok "$host: repair log fresh (<45 min)" \
                         || tap_fail "$host: repair log fresh (<45 min)" "$val"
    val="$(printf '%s\n' "$report" | sed -n 's/^battery=//p')"
    [ "$val" != "unknown" ] && [ -n "$val" ] && tap_ok "$host: termux-api battery readable (${val}%)" \
                         || tap_fail "$host: termux-api battery readable" "termux-api unavailable"

    # Deployment drift: deployed scripts vs repo (informational TODO, not a failure)
    drift=""
    for f in stayturgid-repair.sh repair-bridge.sh claude-presence.sh check-repo-version.sh stayturgid-battery-alarm.sh; do
        remote_md5="$(printf '%s\n' "$report" | sed -n "s/^md5 $f //p")"
        local_md5="$(md5 -q "termux/$f" 2>/dev/null || md5sum "termux/$f" | cut -d' ' -f1)"
        [ "$remote_md5" = "$local_md5" ] || drift="$drift $f"
    done
    if [ -z "$drift" ]; then
        tap_ok "$host: deployed termux scripts match repo"
    else
        tap_todo_fail "$host: deployed termux scripts match repo" "drift:$drift (run ./mac/deploy-fleet.sh)"
    fi

    if [ "$ANSIBLE_CHECK" -eq 1 ]; then
        if command -v ansible-playbook >/dev/null 2>&1; then
            if ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook \
                 ansible/playbooks/termux-userland.yml --check --diff --limit "$host" >/dev/null 2>&1; then
                tap_ok "$host: ansible --check dry run clean"
            else
                tap_fail "$host: ansible --check dry run clean" "re-run without >/dev/null for the diff"
            fi
        else
            tap_skip "$host: ansible --check dry run" "ansible not installed"
        fi
    fi
done

tap_done
