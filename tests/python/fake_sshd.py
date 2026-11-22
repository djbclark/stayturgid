"""A fake sshd for tests: accepts TCP connections and plays banner / key-exchange / reset behaviours.

A stale sshd listener (p7a, 2026-11-21) accepts the connection and resets it before sending a banner.
"""

import socket
import struct
import threading

BANNER = b"SSH-2.0-OpenSSH_10.6\r\n"


def kexinit_packet(msg_type=20):
    payload = bytes([msg_type]) + b"\0" * 20
    padding = 8 - ((len(payload) + 5) % 8) + 8
    body = bytes([padding]) + payload + b"\0" * padding
    return struct.pack(">I", len(body)) + body


def reset_close(conn):
    # SO_LINGER 0 turns close() into an RST, which is what the stale listener's child does.
    conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    conn.close()


def good(conn):
    conn.sendall(BANNER)
    conn.recv(64)
    conn.sendall(kexinit_packet())
    conn.close()


class FakeSshd:
    """Listens on a free loopback port; hands each accepted connection to the next handler."""

    def __init__(self, *handlers, repeat=None):
        """``handlers`` serve the first connections in order; ``repeat`` (if any) serves every later one."""
        self.repeat = repeat
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        self.handlers = list(handlers)
        self.accepted = 0
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        while self.handlers or self.repeat:
            try:
                conn, _addr = self.sock.accept()
            except OSError:
                return
            self.accepted += 1
            handler = self.handlers.pop(0) if self.handlers else self.repeat
            try:
                handler(conn)
            except OSError:
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

    def close(self):
        self.sock.close()
