"""Host-cert re-signing guards for tasks/ca.yml ("Sign host key with CA").

The cached cert in stayturgid_ca_tmpdir used to be reused whenever its public key
matched the host key, even after the wanted principals changed (m11's ansible_host
moved but its cert kept the old names, so `ssh m11` printed "Certificate invalid:
name is not a listed principal"). The task must re-sign when the cert's principal
set differs from the wanted one, compare as de-duplicated sets, and still re-sign
for a different key. These tests render the real task and run it with the real
`ssh-keygen` against throwaway keys.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path

import jinja2
import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
CA_YML = REPO / "ansible_collections/stayturgid/termux/roles/termux_userland/tasks/ca.yml"

pytestmark = pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="needs ssh-keygen")


def _task(name: str) -> dict:
    tasks = yaml.safe_load(CA_YML.read_text())
    return next(t for t in tasks if t.get("name", "").startswith(name))


def _env() -> jinja2.Environment:
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    env.filters["quote"] = lambda v: shlex.quote(str(v))
    env.globals["lookup"] = lambda kind, name: "/nonexistent-home" if (kind, name) == ("env", "HOME") else ""
    return env


def _principals(inventory_hostname: str, ansible_host: str, device_lan_ip: str | None) -> str:
    """Render the real set_fact expression."""
    expr = _task("Build host cert principals")["ansible.builtin.set_fact"]["_stg_cert_principals_str"]
    ctx = {"inventory_hostname": inventory_hostname, "ansible_host": ansible_host}
    if device_lan_ip is not None:
        ctx["device_lan_ip"] = device_lan_ip
    return _env().from_string(expr).render(**ctx).strip()


def _sign_script(tmp: Path, principals: str) -> str:
    script = _task("Sign host key with CA")["ansible.builtin.shell"]["cmd"]
    ctx = {
        "stayturgid_ca_tmpdir": str(tmp),
        "inventory_hostname": "m11",
        "stayturgid_ca_key_path": str(tmp / "ca"),
        "_stg_cert_principals_str": principals,
    }
    return _env().from_string(script).render(**ctx)


def _keygen(path: Path) -> None:
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(path), "-C", path.name],
        check=True,
        capture_output=True,
    )


def _run(tmp: Path, principals: str) -> str:
    r = subprocess.run(["sh", "-c", _sign_script(tmp, principals)], capture_output=True, text=True, check=True)
    return r.stdout


def _cert_principals(cert: Path) -> list[str]:
    out = subprocess.run(
        ["ssh-keygen", "-Lf", str(cert)], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    i = next(n for n, line in enumerate(out) if line.strip().startswith("Principals:"))
    found = []
    for line in out[i + 1 :]:
        if line.strip().startswith(("Critical Options:", "Extensions:")):
            break
        found.append(line.strip())
    return found


@pytest.fixture
def env(tmp_path: Path) -> Path:
    _keygen(tmp_path / "ca")
    _keygen(tmp_path / "m11_host_key")
    return tmp_path


CERT = "m11_host_key-cert.pub"


def test_same_key_same_principals_is_not_resigned(env: Path):
    assert "signed" in _run(env, "m11,100.92.162.72")
    first = (env / CERT).read_bytes()
    assert _run(env, "m11,100.92.162.72") == ""
    # Same set in another order is the same set.
    assert _run(env, "100.92.162.72,m11") == ""
    assert (env / CERT).read_bytes() == first


def test_same_key_changed_principals_is_resigned(env: Path):
    assert "signed" in _run(env, "m11,192.168.68.74")
    assert sorted(_cert_principals(env / CERT)) == ["192.168.68.74", "m11"]
    assert "signed" in _run(env, "m11,100.92.162.72,192.168.68.74")
    assert sorted(_cert_principals(env / CERT)) == ["100.92.162.72", "192.168.68.74", "m11"]
    # A strict subset or superset of the cached names also differs.
    assert "signed" in _run(env, "m11")
    assert _cert_principals(env / CERT) == ["m11"]


def test_different_key_is_still_resigned(env: Path):
    assert "signed" in _run(env, "m11")
    old = (env / CERT).read_bytes()
    (env / "m11_host_key").unlink()
    (env / "m11_host_key.pub").unlink()
    _keygen(env / "m11_host_key")  # reinstalled Termux: new host key, same principals
    assert "signed" in _run(env, "m11")
    assert (env / CERT).read_bytes() != old


def test_duplicate_principals_are_deduplicated():
    # The m11 case: ansible_host == device_lan_ip.
    assert _principals("m11", "192.168.68.74", "192.168.68.74") == "m11,192.168.68.74"
    assert _principals("m11", "100.92.162.72", "192.168.68.74") == "m11,100.92.162.72,192.168.68.74"
    assert _principals("m11", "100.92.162.72", "") == "m11,100.92.162.72"
    assert _principals("m11", "100.92.162.72", None) == "m11,100.92.162.72"


def test_duplicate_wanted_names_do_not_force_resign_or_duplicate_in_cert(env: Path):
    want = _principals("m11", "192.168.68.74", "192.168.68.74")
    assert "signed" in _run(env, want)
    assert sorted(_cert_principals(env / CERT)) == ["192.168.68.74", "m11"]
    assert _run(env, want) == ""
    # Even a raw duplicated list (old behaviour) compares equal as a set.
    assert _run(env, "m11,192.168.68.74,192.168.68.74") == ""


def test_hostile_principal_stays_quoted(env: Path, tmp_path: Path):
    marker = tmp_path / "pwned"
    _run(env, f"m11,x;touch {marker}")
    assert not marker.exists()


def test_corrupt_cached_cert_is_resigned_not_fatal(env: Path):
    assert "signed" in _run(env, "m11")
    (env / CERT).write_text("ssh-ed25519-cert-v01@openssh.com not-a-cert\n")
    assert "signed" in _run(env, "m11")
    assert _cert_principals(env / CERT) == ["m11"]
