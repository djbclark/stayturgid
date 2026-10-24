"""The FIRERPA server and Mac client track the latest release in lockstep.

Runs the firerpa role's real tasks/resolve_release.yml under ansible-playbook,
first in a play over two device hosts (as fleet/firerpa.yml does) and then in a
localhost play (as control_node's firerpa_venv.yml does), against a local
stand-in for api.github.com. Both plays must see one version from one lookup.
"""

from __future__ import annotations

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
    tag = "v10.9"
    seen: list[str] = []

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        type(self).seen.append(self.path)
        if self.path != "/repos/firerpa/lamda/releases/latest":
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps({"tag_name": type(self).tag, "draft": False, "prerelease": False}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:
        pass


@pytest.fixture
def fake_api():
    _FakeGitHub.seen = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeGitHub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()


def _resolve_and_record(api: str, out: Path, label: str) -> list[dict]:
    return [
        {
            "name": "Resolve",
            "ansible.builtin.include_role": {"name": "stayturgid.firerpa.firerpa", "tasks_from": "resolve_release"},
            "vars": {"github_latest_release_api": api, "github_latest_release_token": ""},
        },
        {
            "name": "Record",
            "ansible.builtin.copy": {
                "content": "{{ hostvars['localhost']['firerpa_release_version'] }}",
                "dest": f"{out}/{label}-{{{{ inventory_hostname }}}}.txt",
            },
            "delegate_to": "localhost",
        },
    ]


def _run(tmp_path: Path, api: str) -> subprocess.CompletedProcess:
    out = tmp_path / "out"
    out.mkdir()
    plays = [
        {"hosts": "phones", "gather_facts": False, "tasks": _resolve_and_record(api, out, "device")},
        {"hosts": "localhost", "gather_facts": False, "tasks": _resolve_and_record(api, out, "mac")},
    ]
    playbook = tmp_path / "play.yml"
    playbook.write_text(yaml.safe_dump(plays))
    python = sys.executable
    inventory = tmp_path / "inventory.yml"
    host = {"ansible_connection": "local", "ansible_python_interpreter": python}
    inventory.write_text(
        yaml.safe_dump(
            {
                "all": {
                    "hosts": {"localhost": host},
                    "children": {"phones": {"hosts": {"phone1": host, "phone2": host}}},
                }
            }
        )
    )
    utf8 = "en_US.UTF-8" if sys.platform == "darwin" else "C.UTF-8"
    env = {
        **os.environ,
        "LC_ALL": utf8,
        "LANG": utf8,
        "ANSIBLE_ROLES_PATH": str(REPO / "ansible/roles"),
        "ANSIBLE_COLLECTIONS_PATH": str(REPO),
        "ANSIBLE_LOCALHOST_WARNING": "False",
        "ANSIBLE_HOME": str(tmp_path / "ansible-home"),
    }
    return subprocess.run(
        ["ansible-playbook", "-i", str(inventory), str(playbook)],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        timeout=180,
        check=False,
    )


def test_one_lookup_per_converge_feeds_devices_and_mac(tmp_path: Path, fake_api: str) -> None:
    done = _run(tmp_path, fake_api)
    assert done.returncode == 0, (done.stdout + done.stderr)[-3000:]

    recorded = {path.name: path.read_text() for path in (tmp_path / "out").iterdir()}
    assert recorded == {
        "device-phone1.txt": "10.9",
        "device-phone2.txt": "10.9",
        "mac-localhost.txt": "10.9",
    }
    assert _FakeGitHub.seen == ["/repos/firerpa/lamda/releases/latest"], "resolved more than once"


def test_an_unusable_release_tag_fails_the_converge(tmp_path: Path, fake_api: str) -> None:
    _FakeGitHub.tag = "nightly"
    try:
        done = _run(tmp_path, fake_api)
    finally:
        _FakeGitHub.tag = "v10.9"
    assert done.returncode != 0
    assert not any((tmp_path / "out").iterdir())
