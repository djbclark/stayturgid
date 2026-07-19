from __future__ import annotations

import configparser
import subprocess
import sys
import tomllib
from pathlib import Path

import yaml
from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from control.site_contract import generate_registry_seeds as seeds  # noqa: E402

TEMPLATES = ROOT / "control" / "site_contract" / "templates"


def _render(name: str) -> str:
    environment = Environment(undefined=StrictUndefined, keep_trailing_newline=True, autoescape=False)
    return environment.from_string((TEMPLATES / name).read_text(encoding="utf-8")).render(
        site_name="example",
        product_root="/srv/products/stayturgid",
    )


def test_complete_site_layout_templates_exist_and_load() -> None:
    expected = {
        ".gitignore",
        "README.md.j2",
        "ansible.cfg.j2",
        "docs/.gitkeep",
        "generated/stayturgid/.gitkeep",
        "inventory/group_vars/.gitkeep",
        "inventory/hosts.yml",
        "justfile.j2",
        "registry/paths.yml",
        "registry/ports.yml",
        "secretspec.toml.j2",
    }
    actual = {str(path.relative_to(TEMPLATES)) for path in TEMPLATES.rglob("*") if path.is_file()}
    assert actual == expected

    for path in sorted(TEMPLATES.rglob("*.j2")):
        _render(str(path.relative_to(TEMPLATES)))
    assert yaml.safe_load((TEMPLATES / "inventory/hosts.yml").read_text(encoding="utf-8"))
    assert yaml.safe_load((TEMPLATES / "registry/ports.yml").read_text(encoding="utf-8"))
    assert yaml.safe_load((TEMPLATES / "registry/paths.yml").read_text(encoding="utf-8"))


def test_rendered_structured_templates_parse() -> None:
    ansible_config = configparser.ConfigParser(interpolation=None)
    ansible_config.read_string(_render("ansible.cfg.j2"))
    assert ansible_config["defaults"]["inventory"] == "inventory/hosts.yml"
    assert ansible_config["defaults"]["roles_path"] == "/srv/products/stayturgid/ansible/roles"

    secret_spec = tomllib.loads(_render("secretspec.toml.j2"))
    assert secret_spec["project"]["name"] == "site-example"
    assert "OPENOBSERVE_ROOT_PASSWORD" in secret_spec["profiles"]["default"]


def test_rendered_justfile_parses(tmp_path: Path) -> None:
    justfile = tmp_path / "justfile"
    justfile.write_text(_render("justfile.j2"), encoding="utf-8")
    result = subprocess.run(
        ["just", "--summary", "--justfile", str(justfile)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_inventory_template_tracks_the_product_example() -> None:
    template = yaml.safe_load((TEMPLATES / "inventory/hosts.yml").read_text(encoding="utf-8"))
    product_example = yaml.safe_load((ROOT / "ansible/inventory/hosts.yml.example").read_text(encoding="utf-8"))
    assert template == product_example


def test_registry_seeds_are_current_and_derived_from_product_defaults() -> None:
    for name, content in seeds.rendered_seeds().items():
        assert (TEMPLATES / "registry" / name).read_text(encoding="utf-8") == content

    registry = yaml.safe_load((TEMPLATES / "registry/ports.yml").read_text(encoding="utf-8"))
    claims = [claim for scope in registry["product_defaults"].values() for claim in scope]
    by_service = {claim["service"]: claim for claim in claims}
    assert by_service["eternal-terminal"]["port"] == seeds._port_from_source(
        {
            "file": "ansible/roles/control_node/defaults/main.yml",
            "yaml_path": "stayturgid_control_et_port",
        }
    )
    assert by_service["openobserve-http"]["port"] == seeds._port_from_source(
        {"file": "ansible/roles/control_node/defaults/main.yml", "yaml_path": "openobserve_port"}
    )
    assert by_service["vector-otlp-http"]["port"] == seeds._port_from_source(
        {"file": "ansible/roles/control_node/defaults/main.yml", "yaml_path": "vector_otlp_port"}
    )
    assert by_service["firerpa"]["port"] == seeds._port_from_source(
        {
            "file": "ansible_collections/stayturgid/firerpa/roles/firerpa/defaults/main.yml",
            "yaml_path": "firerpa_port",
        }
    )
    assert len(claims) >= 10
    assert all(claim["source"] for claim in claims)

    paths = yaml.safe_load((TEMPLATES / "registry/paths.yml").read_text(encoding="utf-8"))
    assert paths["prefixes"]["stayturgid"]
    assert set(paths["prefixes"]["stayturgid"]) == set(paths["claim_sources"])


def test_gitignore_ignores_secrets_but_tracks_generated(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text((TEMPLATES / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8")
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)

    ignored = ["local.env", "service.pem", "private.key", "chain.crt", "id_ed25519"]
    for relative in ignored:
        result = subprocess.run(["git", "check-ignore", "--quiet", "--no-index", relative], cwd=tmp_path, check=False)
        assert result.returncode == 0, relative

    generated = subprocess.run(
        ["git", "check-ignore", "--quiet", "--no-index", "generated/stayturgid/example.yml"],
        cwd=tmp_path,
        check=False,
    )
    assert generated.returncode == 1
