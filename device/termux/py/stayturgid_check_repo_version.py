#!/data/data/com.termux/files/usr/bin/python
"""check-repo-version (Python) — deployed as ~/stayturgid_check_repo_version.py.

Notify when GitHub's version.json is newer than the last seen version.
Notify-only (updates are applied from the Mac). Migrated from the former
check-repo-version.sh; unit-tested via tests/test-unit.sh (version_check_suite).
"""
import os
import re
import subprocess
import sys

os.environ["PATH"] = "/data/data/com.termux/files/usr/bin:" + os.environ.get("PATH", "")
os.environ["LC_ALL"] = "C"

URL = "https://raw.githubusercontent.com/djbclark/stayturgid/master/version.json"
STAMP = os.path.join(os.environ.get("HOME", ""), ".stayturgid", "state", "repo_version")


def _write(path, text):
    """Write, self-healing the parent dir (a user may delete ~/.stayturgid)."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
    except OSError:
        pass


def _field(text, key):
    """Match the shell's sed extraction so parity holds even on malformed JSON."""
    m = re.search(r'"%s"\s*:\s*"([^"]*)"' % key, text)
    return m.group(1) if m else ""


def main():
    try:
        p = subprocess.run(["curl", "-fsSL", URL], capture_output=True, text=True)
    except OSError:
        return 0
    if p.returncode != 0:
        return 0  # network failure — quiet
    body = p.stdout

    remote = _field(body, "version")
    if not remote:
        return 0

    seen = ""
    try:
        with open(STAMP) as f:
            seen = f.read().strip()
    except OSError:
        pass
    if remote == seen:
        return 0

    changelog = _field(body, "changelog") or "Run control/bin/deploy_termux.py from your Mac"
    # Never SIGKILL termux-notification — orphan on hang (ResultReturner).
    try:
        import stayturgid_shell as sh  # noqa: WPS433

        sh.ensure_lib_path()
        import termux_api as tapi  # noqa: WPS433

        tapi.notify(
            [
                "termux-notification",
                "--id",
                "stayturgid-update",
                "--title",
                "stayturgid %s on GitHub" % remote,
                "--content",
                changelog,
                "--priority",
                "high",
                "--button",
                "OK",
            ]
        )
    except Exception:
        try:
            subprocess.Popen(
                [
                    "termux-notification",
                    "--id",
                    "stayturgid-update",
                    "--title",
                    "stayturgid %s on GitHub" % remote,
                    "--content",
                    changelog,
                    "--priority",
                    "high",
                    "--button",
                    "OK",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            pass

    _write(STAMP, remote + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
