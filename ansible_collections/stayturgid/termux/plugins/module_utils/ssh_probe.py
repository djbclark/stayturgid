# -*- coding: utf-8 -*-
"""Banner + key-exchange probe of an sshd from the control node.

`sshd -t`, `sv status` and an open port all pass on a listener that resets every
login (p7a, 2026-11-21: stale listener after an openssh upgrade). Only a handshake
shows it. This reads the server's identification string, sends ours, then reads the
server's first binary packet and checks it is SSH_MSG_KEXINIT (20): that proves the
per-connection `sshd-session` started, parsed its host keys and began key exchange.
No keys, no authentication, nothing sent beyond our banner.

A reset before the banner is what the ssh client reports as
`kex_exchange_identification: Connection reset by peer`; the failure text names it.
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import socket
import time

CLIENT_BANNER = b"SSH-2.0-stayturgid-probe\r\n"
SSH_MSG_KEXINIT = 20
MAX_BANNER = 255
DEADLINE_FACTOR = 3  # one attempt may use at most this many timeouts in total
MAX_PACKET = 35000  # RFC 4253 section 6.1 minimum every implementation must accept


class ProbeError(Exception):
    """The handshake failed; ``str()`` is the operator-facing reason."""


def _remaining(deadline, host, port):
    left = deadline - time.monotonic()
    if left <= 0:
        raise ProbeError("handshake with %s:%s did not finish in time" % (host, port))
    return left


def _read_exact(sock, count, deadline, host, port):
    data = b""
    while len(data) < count:
        sock.settimeout(_remaining(deadline, host, port))
        chunk = sock.recv(count - len(data))
        if not chunk:
            raise ProbeError("connection closed after %d of %d bytes" % (len(data), count))
        data += chunk
    return data


def _read_banner(sock, deadline, host, port):
    """Bytes up to and including the first newline, at most MAX_BANNER, within the deadline."""
    data = b""
    while b"\n" not in data and len(data) < MAX_BANNER:
        sock.settimeout(_remaining(deadline, host, port))
        chunk = sock.recv(MAX_BANNER - len(data))
        if not chunk:
            break
        data += chunk
    return data


def _printable(raw):
    """Only printable ASCII, so a hostile banner cannot put terminal escapes in logs."""
    return "".join(chr(b) for b in raw if 0x20 <= b < 0x7F)


def probe_once(host, port, timeout):
    """One handshake; returns the server's identification string or raises ProbeError."""
    try:
        sock = socket.create_connection((host, int(port)), timeout=timeout)
    except OSError as exc:
        raise ProbeError("cannot connect to %s:%s: %s" % (host, port, exc))
    try:
        deadline = time.monotonic() + timeout * DEADLINE_FACTOR
        try:
            banner = _read_banner(sock, deadline, host, port)
        except ConnectionResetError:
            banner = b""
            reset = True
        except OSError as exc:
            raise ProbeError("no ssh banner from %s:%s: %s" % (host, port, exc))
        else:
            reset = False
        if not banner.startswith(b"SSH-"):
            if reset or not banner:
                raise ProbeError(
                    "kex_exchange_identification: connection reset or closed before the ssh banner on %s:%s "
                    "(a stale sshd listener after a package upgrade does this; restart it)" % (host, port)
                )
            raise ProbeError("not an ssh server on %s:%s: first line %r" % (host, port, _printable(banner[:40])))
        ident = _printable(banner.strip())
        try:
            sock.sendall(CLIENT_BANNER)
            header = _read_exact(sock, 6, deadline, host, port)
        except ConnectionResetError:
            raise ProbeError(
                "connection reset after the banner (%s) before key exchange on %s:%s" % (ident, host, port)
            )
        except (OSError, ProbeError) as exc:
            raise ProbeError("%s: no key exchange packet from %s:%s: %s" % (ident, host, port, exc))
        length = int.from_bytes(header[:4], "big")
        if not 2 <= length <= MAX_PACKET or header[5] != SSH_MSG_KEXINIT:
            raise ProbeError(
                "%s: first packet from %s:%s is not SSH_MSG_KEXINIT (length %d, type %d)"
                % (ident, host, port, length, header[5])
            )
        return ident
    finally:
        sock.close()


def probe(host, port=8022, timeout=8.0, retries=1, delay=3.0, sleep=time.sleep):
    """Probe up to ``retries`` times; returns ``(ident, attempts)`` or raises ProbeError.

    The last error is raised. A fresh sshd needs a moment, so callers right after a
    restart pass retries > 1.
    """
    last = None
    attempts = max(1, int(retries))
    for attempt in range(1, attempts + 1):
        try:
            return probe_once(host, port, timeout), attempt
        except ProbeError as exc:
            last = exc
            if attempt < attempts:
                sleep(delay)
    raise ProbeError("%s (after %d attempt%s)" % (last, attempts, "" if attempts == 1 else "s"))
