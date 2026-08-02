#!/usr/bin/env python3
"""gplaycli launcher: Homebrew gplaycli on Python 3.14 breaks without setuptools.

Prepends pip's vendored pkg_resources path, then runs gplaycli as a module.
"""

from __future__ import annotations

import os
import subprocess
import sys


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
    py = os.environ.get("GPLAYCLI_PYTHON", "python3.14")
    env = os.environ.copy()
    vendor = vendor_dir(py)
    env["PYTHONPATH"] = vendor + (f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else "")
    return subprocess.call([py, "-m", "gplaycli.gplaycli", *argv], env=env)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(130)
