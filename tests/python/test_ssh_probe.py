"""The control-node banner + key-exchange probe (module_utils/ssh_probe.py) against fake sshds.

A stale sshd listener (p7a, 2026-11-21) accepts the TCP connection and resets it before
sending its banner: the ssh client calls that `kex_exchange_identification: Connection reset by
peer`. Open port, `sv status` and `sshd -t` all looked fine, so the probe has to complete a handshake.
"""

import socket
import sys
import threading
from pathlib import Path

import pytest

_UTILS = Path(__file__).resolve().parents[2] / "ansible_collections/stayturgid/termux/plugins/module_utils"
sys.path.insert(0, str(_UTILS))

import ssh_probe as sp  # noqa: E402
from fake_sshd import BANNER, FakeSshd, good, kexinit_packet, reset_close  # noqa: E402


@pytest.fixture
def fake():
    made = []

    def make(*handlers):
        server = FakeSshd(*handlers)
        made.append(server)
        return server

    yield make
    for server in made:
        server.close()


def test_a_healthy_sshd_passes_and_reports_its_banner(fake):
    server = fake(good)
    banner, attempts = sp.probe("127.0.0.1", server.port, timeout=3)
    assert banner == "SSH-2.0-OpenSSH_10.6" and attempts == 1


def test_a_reset_before_the_banner_is_the_stale_listener_failure(fake):
    server = fake(reset_close)
    with pytest.raises(sp.ProbeError) as err:
        sp.probe("127.0.0.1", server.port, timeout=3)
    assert "kex_exchange_identification" in str(err.value)
    assert "stale sshd listener" in str(err.value)


def test_a_clean_close_before_the_banner_fails_the_same_way(fake):
    server = fake(lambda conn: conn.close())
    with pytest.raises(sp.ProbeError, match="kex_exchange_identification"):
        sp.probe("127.0.0.1", server.port, timeout=3)


def test_something_that_is_not_ssh_is_named_as_such(fake):
    server = fake(lambda conn: conn.sendall(b"HTTP/1.1 400 Bad Request\r\n"))
    with pytest.raises(sp.ProbeError, match="not an ssh server"):
        sp.probe("127.0.0.1", server.port, timeout=3)


def test_a_banner_followed_by_a_close_is_a_failed_key_exchange(fake):
    server = fake(lambda conn: conn.sendall(BANNER))
    with pytest.raises(sp.ProbeError, match="no key exchange packet"):
        sp.probe("127.0.0.1", server.port, timeout=3)


def test_a_first_packet_that_is_not_kexinit_fails(fake):
    def wrong(conn):
        conn.sendall(BANNER)
        conn.recv(64)
        conn.sendall(kexinit_packet(msg_type=1))

    server = fake(wrong)
    with pytest.raises(sp.ProbeError, match="not SSH_MSG_KEXINIT"):
        sp.probe("127.0.0.1", server.port, timeout=3)


def test_a_silent_server_times_out(fake):
    gate = threading.Event()
    server = fake(lambda conn: gate.wait(5))
    try:
        with pytest.raises(sp.ProbeError, match="no ssh banner"):
            sp.probe("127.0.0.1", server.port, timeout=0.3)
    finally:
        gate.set()


def test_a_closed_port_fails_to_connect():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    with pytest.raises(sp.ProbeError, match="cannot connect"):
        sp.probe("127.0.0.1", port, timeout=1)


def test_retries_wait_for_a_fresh_sshd_to_come_up(fake):
    server = fake(reset_close, reset_close, good)
    sleeps = []
    banner, attempts = sp.probe("127.0.0.1", server.port, timeout=3, retries=5, delay=2, sleep=sleeps.append)
    assert attempts == 3 and sleeps == [2, 2] and banner.startswith("SSH-2.0")


def test_the_last_error_is_raised_after_the_attempts_run_out(fake):
    server = fake(reset_close, reset_close)
    with pytest.raises(sp.ProbeError, match=r"kex_exchange_identification.*after 2 attempts"):
        sp.probe("127.0.0.1", server.port, timeout=3, retries=2, delay=0, sleep=lambda _s: None)
    assert server.accepted == 2


def test_a_single_attempt_does_not_say_attempts():
    with pytest.raises(sp.ProbeError) as err:
        sp.probe("127.0.0.1", 1, timeout=0.5)
    assert str(err.value).endswith("(after 1 attempt)")
