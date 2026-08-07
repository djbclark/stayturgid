#!/usr/bin/env python3
"""Execute approved Ansible with JSON secrets from the fixed sudo wrapper."""

from __future__ import annotations

import json
import os
import subprocess
import sys

WRAPPER = "/usr/local/libexec/stayturgid-secretspec-wrapper.sh"
SERVICE_USER = "_secretspec"


def main(argv: list[str] | None = None) -> int:
    command = list(sys.argv[1:] if argv is None else argv)
    if not command or command[0] != "ansible-playbook":
        print("only ansible-playbook is approved", file=sys.stderr)
        return 2
    try:
        result = subprocess.run(
            ["sudo", "-n", "-u", SERVICE_USER, WRAPPER, "automation-env"],
            check=True,
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin:/opt/homebrew/bin:/usr/local/bin"},
        )
        values = json.loads(result.stdout)
        if not isinstance(values, dict) or any(
            not isinstance(key, str) or not isinstance(value, str) for key, value in values.items()
        ):
            raise ValueError("wrapper returned a non-string JSON object")
        env = os.environ.copy()
        env.update(values)
        os.execvpe(command[0], command, env)
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError) as exc:
        print(f"SecretSpec automation boundary failed closed: {exc}", file=sys.stderr)
        return 126


if __name__ == "__main__":
    raise SystemExit(main())
