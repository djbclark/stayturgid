"""github_latest_release resolves the newest release through the GitHub API.

Runs the real role under ansible-playbook against a local stand-in for
api.github.com, so no test touches the network.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(shutil.which("ansible-playbook") is None, reason="ansible-playbook not installed")


class _FakeGitHub(BaseHTTPRequestHandler):
    tags: dict[str, str] = {}
    seen: list[tuple[str, str]] = []

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        type(self).seen.append((self.path, self.headers.get("Authorization", "")))
        repo = self.path.removeprefix("/repos/").removesuffix("/releases/latest")
        if repo not in self.tags:
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps({"tag_name": self.tags[repo], "draft": False, "prerelease": False}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:
        pass


@pytest.fixture
def fake_api():
    _FakeGitHub.tags = {"o/v-prefixed": "v0.29.1", "o/bare": "3000.21.0", "o/odd": "nightly"}
    _FakeGitHub.seen = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeGitHub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()


def _play(tmp_path: Path, api: str, repo: str, token: str) -> subprocess.CompletedProcess:
    out = tmp_path / "version.txt"
    play = [
        {
            "hosts": "localhost",
            "connection": "local",
            "gather_facts": False,
            "tasks": [
                {
                    "name": "Resolve",
                    "ansible.builtin.include_role": {"name": "github_latest_release"},
                    "vars": {
                        "github_latest_release_repo": repo,
                        "github_latest_release_api": api,
                        "github_latest_release_token": token,
                    },
                },
                {
                    "name": "Write",
                    "ansible.builtin.copy": {"content": "{{ github_latest_release_version }}", "dest": str(out)},
                },
            ],
        }
    ]
    playbook = tmp_path / "play.yml"
    playbook.write_text(yaml.safe_dump(play))
    utf8 = "en_US.UTF-8" if sys.platform == "darwin" else "C.UTF-8"
    env = {
        **os.environ,
        "LC_ALL": utf8,
        "LANG": utf8,
        "ANSIBLE_ROLES_PATH": str(REPO / "ansible/roles"),
        "ANSIBLE_LOCALHOST_WARNING": "False",
        "ANSIBLE_INVENTORY_UNPARSED_WARNING": "False",
        "ANSIBLE_HOME": str(tmp_path / "ansible-home"),
    }
    return subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(playbook)],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        timeout=180,
        check=False,
    )


@pytest.mark.parametrize(("repo", "expected"), [("o/v-prefixed", "0.29.1"), ("o/bare", "3000.21.0")])
def test_latest_tag_becomes_a_bare_version(tmp_path: Path, fake_api: str, repo: str, expected: str) -> None:
    done = _play(tmp_path, fake_api, repo, "")
    assert done.returncode == 0, (done.stdout + done.stderr)[-2000:]
    assert (tmp_path / "version.txt").read_text() == expected
    assert _FakeGitHub.seen == [(f"/repos/{repo}/releases/latest", "")]


def test_a_token_is_sent_as_basic_auth(tmp_path: Path, fake_api: str) -> None:
    done = _play(tmp_path, fake_api, "o/bare", "s3cret")
    assert done.returncode == 0, (done.stdout + done.stderr)[-2000:]
    expected = "Basic " + base64.b64encode(b"x-access-token:s3cret").decode()
    assert _FakeGitHub.seen == [("/repos/o/bare/releases/latest", expected)]
    assert "s3cret" not in done.stdout + done.stderr


@pytest.mark.parametrize("repo", ["o/odd", "o/missing"])
def test_an_unusable_answer_fails_the_play(tmp_path: Path, fake_api: str, repo: str) -> None:
    done = _play(tmp_path, fake_api, repo, "")
    assert done.returncode != 0
    assert not (tmp_path / "version.txt").exists()
