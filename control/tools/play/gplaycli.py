#!/usr/bin/env python3
"""gplaycli launcher for the pip-installed gplaycli in Homebrew's Python.

gplaycli imports pkg_resources, which current setuptools no longer ships, so
this prepends pip's vendored copy to PYTHONPATH. matlink-gpapi's generated
_pb2 modules predate protobuf 4 ("Descriptors cannot be created directly"),
so the pure-Python protobuf backend is selected unless the caller set one.
Then gplaycli runs as a module.

Interpreter: $GPLAYCLI_PYTHON, else Homebrew's unversioned python3 (its newest
python@; install there with `uv pip install --python /opt/homebrew/bin/python3
--break-system-packages gplaycli`), else python3 on PATH. No minor is pinned.
"""

from __future__ import annotations

import os
import subprocess
import sys

BREW_PYTHON = "/opt/homebrew/bin/python3"


def vendor_dir(py: str) -> str:
    result = subprocess.run(
        [py, "-c", "import os, pip; print(os.path.join(os.path.dirname(pip.__file__), '_vendor'))"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    py = os.environ.get("GPLAYCLI_PYTHON") or (BREW_PYTHON if os.access(BREW_PYTHON, os.X_OK) else "python3")
    env = os.environ.copy()
    env.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")
    vendor = vendor_dir(py)
    env["PYTHONPATH"] = vendor + (f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else "")
    return subprocess.call([py, "-m", "gplaycli.gplaycli", *argv], env=env)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(130)
