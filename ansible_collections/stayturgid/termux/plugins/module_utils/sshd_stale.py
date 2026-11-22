# -*- coding: utf-8 -*-
"""Detect (and restart) a Termux sshd listener that outlived its own binary.

An `openssh` package upgrade replaces `sshd`, `sshd-session` and `sshd-auth` under
a running listener. The old listener keeps running from the deleted inode, hands
host keys to the NEW `sshd-session` and every login dies before the banner:
`parse_hostkeys: parse pubkey: unexpected internal error` on the phone,
`kex_exchange_identification: Connection reset by peer` on the control node
(p7a, 2026-11-21, openssh 10.5p1 -> 10.6p2, 242 failed connections). Nothing
noticed because sshd was "running". The cure is a listener restart (established
sessions survive it).

The check is one shell script so the same logic runs over adb + run-as
(`termux_run_as.ensure_sshd`, before any SSH exists) and on the phone itself
(`stayturgid.termux.termux_sshd`, `restart_stale`). It is read-only.

Output, two lines::

    fresh | stale deleted-exe | stale older-than-binary | unknown <why>
    supervised=yes | supervised=no

`stale` means the listener must be restarted. `unknown` never triggers a restart:
a missing pidfile or an unreadable /proc entry is not evidence of a stale
listener. "Started" is the mtime of `$PREFIX/var/run/sshd.pid` (sshd writes it at start and
again when a SIGHUP re-execs it): an app-context shell cannot read /proc/uptime on Android
(`no-uptime` on t2e, p7a and m11, 2026-11-21), so a start time from /proc/PID/stat is not
usable. The test hooks (STAYTURGID_PROC / _STAT) only redirect reads.
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import shlex

TERMUX_PREFIX = "/data/data/com.termux/files/usr"

# Seconds of slack between "pidfile written" and "binary changed" (a listener restarted
# by the very install that replaced the binary writes its pidfile within moments).
STALE_MARGIN_S = 5

_CHECK_BODY = r"""
P="${STAYTURGID_PROC:-/proc}"
STATCMD="${STAYTURGID_STAT:-stat}"
verdict() { echo "$*"; if SVDIR="$PREFIX/var/service" "$PREFIX/bin/sv" status sshd >/dev/null 2>&1; then echo supervised=yes; else echo supervised=no; fi; exit 0; }
pid="$(cat "$PREFIX/var/run/sshd.pid" 2>/dev/null)"
case "$pid" in ''|*[!0-9]*) verdict unknown no-pidfile;; esac
[ -d "$P/$pid" ] || verdict unknown pid-gone
argv0="$(tr '\0' '\n' < "$P/$pid/cmdline" 2>/dev/null | head -n 1)"
case "${argv0##*/}" in sshd) ;; *) verdict unknown pid-not-sshd;; esac
exe="$(readlink "$P/$pid/exe" 2>/dev/null)"
case "$exe" in *" (deleted)") verdict stale deleted-exe;; '') verdict unknown exe-unreadable;; esac
started="$("$STATCMD" -c %Y "$PREFIX/var/run/sshd.pid" 2>/dev/null)"
case "$started" in ''|*[!0-9]*) verdict unknown no-pidfile-mtime;; esac
changed="$("$STATCMD" -c %Z "$PREFIX/bin/sshd" "$PREFIX/libexec/sshd-session" 2>/dev/null | sort -n | tail -n 1)"
case "$changed" in ''|*[!0-9]*) verdict unknown no-binary-ctime;; esac
if [ "$started" -lt $(( changed - __MARGIN__ )) ]; then verdict stale older-than-binary; fi
verdict fresh
"""

_RESTART_BODY = r"""
SVDIR="$PREFIX/var/service" "$PREFIX/bin/sv" status sshd >/dev/null 2>&1 || { echo "sshd is not supervised by runit; not restarting" >&2; exit 3; }
SVDIR="$PREFIX/var/service" "$PREFIX/bin/sv" restart sshd
"""


def _prefix_line(prefix):
    return "PREFIX=%s\n" % shlex.quote(prefix)


def stale_check_script(prefix=TERMUX_PREFIX, margin=STALE_MARGIN_S):
    """Read-only shell script printing the two-line verdict for ``prefix``."""
    return _prefix_line(prefix) + _CHECK_BODY.replace("__MARGIN__", str(int(margin)))


def restart_script(prefix=TERMUX_PREFIX):
    """Shell script restarting the runit-supervised sshd (exit 3: not supervised)."""
    return _prefix_line(prefix) + _RESTART_BODY


class Verdict(object):
    """Parsed output of :func:`stale_check_script`."""

    def __init__(self, state, reason, supervised):
        self.state = state
        self.reason = reason
        self.supervised = supervised

    @property
    def stale(self):
        return self.state == "stale"

    @property
    def fresh(self):
        return self.state == "fresh"

    def describe(self):
        return ("%s %s" % (self.state, self.reason)).strip()

    def __repr__(self):
        return "Verdict(%r, %r, supervised=%r)" % (self.state, self.reason, self.supervised)


def parse_verdict(output):
    """Parse the script output; anything unrecognised is ``unknown`` (never stale)."""
    lines = [line.strip() for line in (output or "").replace("\r", "").splitlines() if line.strip()]
    state, reason, supervised = "unknown", "no-output", False
    for line in lines:
        if line.startswith("supervised="):
            supervised = line == "supervised=yes"
            continue
        word, _, rest = line.partition(" ")
        if word in ("fresh", "stale", "unknown"):
            state, reason = word, rest.strip()
    return Verdict(state, reason, supervised)
