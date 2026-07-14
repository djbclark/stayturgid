#!/usr/bin/env python3
"""Start FIRERPA while preserving ordinary Android accessibility services.

The signed FIRERPA v10 distribution validates ``service.jar`` at process
startup.  Its bundled UIAutomation driver then registers with Android flags 0,
which suppresses AutoJs6 and all other accessibility services.  A patched JAR
uses flag 1, but cannot be present during FIRERPA's integrity check.

This controller restores the signed JAR through ADB or Shizuku ``rish``, starts
FIRERPA, waits for integrity validation and the original Java helpers, atomically
activates the patched JAR, then restarts only those helpers.  It runs under Mac
or Termux Python; FIRERPA's embedded Python cannot parent another FIRERPA process
because its runtime applies a restrictive security policy.
"""
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

DEFAULT_ROOT = Path("/data/local/tmp/firerpa")
SIGNED_JAR_SHA256 = (
    "b1ac32d902227b7413ff6c867aa42c1630df1de57141e2efbefa0eca8169a67a"
)
PATCHED_JAR_SHA256 = (
    "805e39de934d39ebaabe221b4db1464f835cc8ad7753bf3f34f4313569f8f1e1"
)
SERVICE_JAR_FRAGMENT = "/site-packages/lamda/service.jar"


class LifecycleError(RuntimeError):
    """Raised when FIRERPA cannot reach a verified coexistence state."""


class ShellTransport:
    """Execute one command string as Android's shell UID."""

    def __init__(self, prefix: list[str]) -> None:
        self.prefix = prefix

    def run(self, command: str, timeout: float = 15) -> tuple[int, str]:
        try:
            result = subprocess.run(
                self.prefix + [command],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            output = exc.stdout or ""
            if isinstance(output, bytes):
                output = output.decode(errors="replace")
            return -1, output
        return result.returncode, result.stdout


def _wait_for(predicate: Callable[[], bool], timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.25)
    return predicate()


class FirerpaLifecycle:
    def __init__(
        self,
        transport: ShellTransport,
        root: Path,
        port: int,
        certificate: Path,
        timeout: float,
    ) -> None:
        self.transport = transport
        self.root = root
        self.server = root / "server"
        self.port = port
        self.certificate = certificate
        self.timeout = timeout
        self.active_jar = (
            self.server / "lib/python3.9/site-packages/lamda/service.jar"
        )
        self.signed_jar = root / "overrides/service.jar.signed"
        self.patched_jar = root / "overrides/service.jar.patched"
        self.launcher = self.server / "bin/launch.sh"
        self.log = root / "server.log"

    def _run(self, command: str, timeout: float = 15) -> str:
        rc, output = self.transport.run(command, timeout=timeout)
        if rc != 0:
            detail = output.strip() or f"exit {rc}"
            raise LifecycleError(f"Android shell command failed: {detail}")
        return output

    def _remote_sha256(self, path: Path) -> str:
        output = self._run(f"sha256sum {shlex.quote(str(path))}")
        for field in output.split():
            candidate = field.lower()
            if len(candidate) == 64 and all(
                character in "0123456789abcdef" for character in candidate
            ):
                return candidate
        raise LifecycleError(f"could not read SHA-256 for {path}")

    def _copy_atomic(self, source: Path, destination: Path) -> None:
        temporary = destination.with_name(f".{destination.name}.stayturgid.tmp")
        command = (
            f"cp {shlex.quote(str(source))} {shlex.quote(str(temporary))} "
            f"&& chmod 0644 {shlex.quote(str(temporary))} "
            f"&& mv -f {shlex.quote(str(temporary))} {shlex.quote(str(destination))}"
        )
        self._run(command)

    def _port_open(self) -> bool:
        rc, _ = self.transport.run(
            f"ss -ltn 2>/dev/null | grep -q ':{self.port} '", timeout=5
        )
        return rc == 0

    def service_jar_pids(self) -> set[int]:
        command = (
            "for pid in $(pidof lamda 2>/dev/null); do "
            f"grep -q {shlex.quote(SERVICE_JAR_FRAGMENT)} "
            '"/proc/$pid/maps" 2>/dev/null && echo "$pid"; '
            "done; exit 0"
        )
        rc, output = self.transport.run(command, timeout=10)
        if rc != 0:
            return set()
        return {int(line) for line in output.splitlines() if line.isdigit()}

    def validate(self) -> None:
        required = " ".join(
            shlex.quote(str(path))
            for path in (
                self.certificate,
                self.active_jar,
                self.signed_jar,
                self.patched_jar,
                self.launcher,
            )
        )
        self._run(f"for path in {required}; do test -f \"$path\" || exit 1; done")
        signed_digest = self._remote_sha256(self.signed_jar)
        if signed_digest != SIGNED_JAR_SHA256:
            raise LifecycleError(
                f"signed service.jar hash {signed_digest} is unsupported"
            )
        patched_digest = self._remote_sha256(self.patched_jar)
        if patched_digest != PATCHED_JAR_SHA256:
            raise LifecycleError(
                f"patched service.jar hash {patched_digest} is unsupported"
            )

    def _launch_signed_server(self) -> None:
        self._copy_atomic(self.signed_jar, self.active_jar)
        command = (
            "rm -f /data/local/tmp/usr/lamda.pid; "
            f"cd {shlex.quote(str(self.server))} && "
            f"nohup sh {shlex.quote(str(self.launcher))} "
            f"--port={self.port} --certificate={shlex.quote(str(self.certificate))} "
            f"> {shlex.quote(str(self.log))} 2>&1 < /dev/null &"
        )
        # Some Android adbd builds keep the client pipe open for a fully
        # redirected background child. A client timeout is harmless when the
        # listener proves that the signed server started successfully.
        launch_rc, launch_output = self.transport.run(command, timeout=12)
        if not _wait_for(self._port_open, self.timeout):
            if launch_rc != 0:
                detail = launch_output.strip() or f"exit {launch_rc}"
                raise LifecycleError(f"Android shell command failed: {detail}")
            raise LifecycleError(
                f"signed FIRERPA server did not listen on port {self.port}"
            )

    def _activate_coexistence_driver(self) -> None:
        original_pids: set[int] = set()

        def original_helpers_ready() -> bool:
            nonlocal original_pids
            original_pids = self.service_jar_pids()
            return bool(original_pids)

        if not _wait_for(original_helpers_ready, self.timeout):
            raise LifecycleError("FIRERPA UIAutomation helpers did not start")

        self._copy_atomic(self.patched_jar, self.active_jar)
        self._run("kill " + " ".join(str(pid) for pid in sorted(original_pids)))

        def replacement_ready() -> bool:
            return bool(self.service_jar_pids() - original_pids)

        if not _wait_for(replacement_ready, self.timeout):
            remaining = original_pids & self.service_jar_pids()
            if remaining:
                self._run("kill -9 " + " ".join(str(pid) for pid in sorted(remaining)))
            if not _wait_for(replacement_ready, self.timeout):
                raise LifecycleError(
                    "patched FIRERPA UIAutomation helpers did not restart"
                )
        if not self._port_open():
            raise LifecycleError("FIRERPA listener stopped during driver activation")

    def start(self) -> None:
        self.validate()
        active_digest = self._remote_sha256(self.active_jar)
        if self._port_open() and active_digest == PATCHED_JAR_SHA256:
            if self.service_jar_pids():
                print("INFO: FIRERPA coexistence driver already active")
                return
        if not self._port_open():
            self._launch_signed_server()
        self._activate_coexistence_driver()
        print("INFO: FIRERPA secure server and accessibility coexistence driver active")


def _transport_from_args(args: argparse.Namespace) -> ShellTransport:
    if args.adb_target:
        return ShellTransport([args.adb, "-s", args.adb_target, "shell"])
    return ShellTransport([str(args.rish), "-c"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run FIRERPA with the accessibility coexistence driver."
    )
    parser.add_argument("command", choices=("start",))
    transports = parser.add_mutually_exclusive_group(required=True)
    transports.add_argument("--adb-target")
    transports.add_argument("--rish", type=Path)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--port", type=int, default=65000)
    parser.add_argument("--certificate", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)

    try:
        lifecycle = FirerpaLifecycle(
            transport=_transport_from_args(args),
            root=args.root,
            port=args.port,
            certificate=args.certificate,
            timeout=args.timeout,
        )
        lifecycle.start()
    except (LifecycleError, OSError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
