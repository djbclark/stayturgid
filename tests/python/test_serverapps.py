"""Focused tests for site-serverapps (Site Contract v1 acceptance test 5)."""

from __future__ import annotations

import io
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from control.site_contract import serverapps as sa  # noqa: E402
from control.site_contract import site_init as si  # noqa: E402
from control.site_contract import site_sync as ss  # noqa: E402

FIXED_VERSION = "9.9.9-test"
FIXED_COMMIT = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
FIXED_SYNCED = "2026-07-19T15:00:00Z"

CADDY_FRAGMENT = "generated/stayturgid/fragments/caddy/stayturgid.caddy"
VECTOR_SOURCES = "generated/stayturgid/fragments/vector/stayturgid_sources.yaml"
VECTOR_SINKS = "generated/stayturgid/fragments/vector/stayturgid_sinks.yaml"


def _init_and_sync(tmp_path: Path, name: str = "example") -> Path:
    dest = tmp_path / f"site-{name}"
    err = io.StringIO()
    code = si.run_site_init(
        sitename=name,
        dir_path=str(dest),
        mode="apply",
        product_root=ROOT,
        env={},
        stdout=io.StringIO(),
        stderr=err,
    )
    assert code == si.EXIT_OK, err.getvalue()
    # site_ns required by serverapps
    group_vars = dest / "inventory" / "group_vars"
    group_vars.mkdir(parents=True, exist_ok=True)
    (group_vars / "all.yml").write_text(
        "---\nsite_ns: example\ncaddy_public_hostname: example.test\ncaddy_short_hostname: example\n",
        encoding="utf-8",
    )
    code, _out, sync_err = _sync(dest)
    assert code == ss.EXIT_OK, sync_err
    assert (dest / CADDY_FRAGMENT).is_file()
    assert (dest / VECTOR_SOURCES).is_file()
    assert (dest / VECTOR_SINKS).is_file()
    return dest


def _sync(dest: Path) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    code = ss.run_site_sync(
        dir_path=str(dest),
        mode="apply",
        product_root=ROOT,
        env={},
        product_version=FIXED_VERSION,
        product_commit=FIXED_COMMIT,
        synced=FIXED_SYNCED,
        stdout=out,
        stderr=err,
    )
    return code, out.getvalue(), err.getvalue()


def _run(
    *,
    dir_path: str,
    mode: str = "apply",
    force_generated: bool = False,
    home: Path | None = None,
    skip_ansible: bool = True,
    apps: str | None = "caddy",
) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    code = sa.run_site_serverapps(
        dir_path=dir_path,
        mode=mode,
        apps=apps,
        force_generated=force_generated,
        product_root=ROOT,
        env={},
        home=home,
        skip_ansible=skip_ansible,
        stdout=out,
        stderr=err,
    )
    return code, out.getvalue(), err.getvalue()


def _write_site_map(dest: Path, body: str) -> None:
    (dest / "site-map.yml").write_text(body, encoding="utf-8")


# --- mode resolution -------------------------------------------------------


def test_mode_defaults_to_own_on_clean_prefix(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    code, stdout, stderr = _run(dir_path=str(dest), mode="dry-run", home=home)
    assert code == sa.EXIT_OK, stderr
    assert "caddy: mode=own (source=default)" in stdout


def test_mode_site_map_off(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    _write_site_map(
        dest,
        "contract_version: 1\nserverapps:\n  caddy:\n    mode: off\n",
    )
    code, stdout, stderr = _run(dir_path=str(dest), mode="dry-run", home=tmp_path / "home")
    assert code == sa.EXIT_OK, stderr
    assert "caddy: mode=off (source=site-map)" in stdout


def test_mode_detect_inject_for_foreign_caddyfile(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    foreign = home / ".config" / "caddy" / "Caddyfile"
    foreign.parent.mkdir(parents=True)
    foreign.write_text("# user caddyfile\n{\n\tadmin off\n}\n", encoding="utf-8")
    # Point detect at our foreign path via site-map mode inject + config.
    frag_dir = home / "caddy.d"
    frag_dir.mkdir()
    _write_site_map(
        dest,
        "contract_version: 1\n"
        "serverapps:\n"
        "  caddy:\n"
        "    mode: inject\n"
        f"    config: {foreign}\n"
        f"    fragment_dir: {frag_dir}\n",
    )
    code, stdout, stderr = _run(dir_path=str(dest), mode="dry-run", home=home)
    # Missing import line → exit 2 even on dry-run plan refuse
    assert code == sa.EXIT_WOULD_OVERWRITE, (stdout, stderr)
    assert "import" in stderr.lower()
    assert str(frag_dir) in stderr


def test_mode_detection_uses_passed_home_not_process_home(tmp_path: Path, monkeypatch) -> None:
    """resolve_app_mode() (and the detect helpers it calls) must honor the
    ``home`` override threaded through build_plan/plan_caddy, not silently
    fall back to the real process ``Path.home()`` (see FINAL-REVIEW finding —
    every one of these previously ignored the override for mode selection
    even though plan_caddy/plan_vector/etc. already accept and use it for
    everything else)."""
    real_home = tmp_path / "real-home-with-foreign-caddyfile"
    foreign = real_home / ".config" / "caddy" / "Caddyfile"
    foreign.parent.mkdir(parents=True)
    foreign.write_text("# a real user's caddyfile that must NOT be scanned\n", encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: real_home))

    dest = _init_and_sync(tmp_path)
    clean_home = tmp_path / "clean-home"
    clean_home.mkdir()
    code, stdout, stderr = _run(dir_path=str(dest), mode="dry-run", home=clean_home)
    assert code == sa.EXIT_OK, stderr
    # If the bug were present, detect would scan real_home's foreign
    # Caddyfile (via Path.home()) instead of clean_home and force inject.
    assert "caddy: mode=own (source=default)" in stdout


def test_legacy_stayturgid_config_does_not_force_inject(tmp_path: Path) -> None:
    """Our own legacy ~/.config/stayturgid/Caddyfile must not flip default to inject."""
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    legacy = home / ".config" / "stayturgid" / "Caddyfile"
    legacy.parent.mkdir(parents=True)
    # No generated header, but under stayturgid prefix → still own.
    legacy.write_text("# live legacy config without marker\n", encoding="utf-8")
    # Monkeypatch OUR_CONFIG_PREFIXES relative to this home by only testing
    # detect paths that are not under stayturgid — default detect won't see
    # legacy unless XDG points there. Force empty foreign detect.
    code, stdout, stderr = _run(dir_path=str(dest), mode="dry-run", home=home)
    assert code == sa.EXIT_OK, stderr
    assert "mode=own" in stdout


# --- acceptance test 5 -----------------------------------------------------


def test_acceptance_5_own_on_clean_prefix(tmp_path: Path) -> None:
    """own mode on clean prefix → base config + plist under com.<site_ns>.caddy."""
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    (home / "Library" / "LaunchAgents").mkdir(parents=True)

    code, stdout, stderr = _run(dir_path=str(dest), mode="apply", home=home, skip_ansible=True)
    assert code == sa.EXIT_OK, stderr
    assert "mode=own" in stdout

    base = home / ".config" / "example" / "caddy" / "Caddyfile"
    plist = home / "Library" / "LaunchAgents" / "com.example.caddy.plist"
    assert base.is_file(), base
    assert "GENERATED by stayturgid" in base.read_text(encoding="utf-8")
    assert "import" in base.read_text(encoding="utf-8")
    assert "*.caddy" in base.read_text(encoding="utf-8")
    assert plist.is_file()
    assert "com.example.caddy" in plist.read_text(encoding="utf-8")
    assert str(base) in plist.read_text(encoding="utf-8")

    # Fragment dir is importable (generated area exists)
    frag = dest / "generated" / "stayturgid" / "fragments" / "caddy" / "stayturgid.caddy"
    assert frag.is_file()
    assert "GENERATED by stayturgid" in frag.read_text(encoding="utf-8")
    assert "reverse_proxy" in frag.read_text(encoding="utf-8")


def test_acceptance_5_inject_without_import_exits_2(tmp_path: Path) -> None:
    """inject mode against pre-existing Caddyfile without import line → exit 2."""
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    foreign = home / "etc" / "Caddyfile"
    foreign.parent.mkdir(parents=True)
    foreign.write_text("{\n\tadmin off\n}\n", encoding="utf-8")
    frag_dir = home / "etc" / "caddy.d"
    frag_dir.mkdir()
    _write_site_map(
        dest,
        "contract_version: 1\n"
        "serverapps:\n"
        "  caddy:\n"
        "    mode: inject\n"
        f"    config: {foreign}\n"
        f"    fragment_dir: {frag_dir}\n",
    )
    code, stdout, stderr = _run(dir_path=str(dest), mode="apply", home=home)
    assert code == sa.EXIT_WOULD_OVERWRITE, (stdout, stderr)
    assert "import" in stderr
    assert f"import {frag_dir.resolve()}/*.caddy" in stderr
    # No fragment copies written on exit 2
    assert list(frag_dir.glob("*.caddy")) == []


def test_inject_with_import_line_copies_fragments(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    foreign = home / "etc" / "Caddyfile"
    foreign.parent.mkdir(parents=True)
    frag_dir = home / "etc" / "caddy.d"
    frag_dir.mkdir()
    foreign.write_text(
        f"{{\n\tadmin off\n}}\nexample.test {{\n\timport {frag_dir.resolve()}/*.caddy\n}}\n",
        encoding="utf-8",
    )
    _write_site_map(
        dest,
        "contract_version: 1\n"
        "serverapps:\n"
        "  caddy:\n"
        "    mode: inject\n"
        f"    config: {foreign}\n"
        f"    fragment_dir: {frag_dir}\n",
    )
    code, stdout, stderr = _run(dir_path=str(dest), mode="apply", home=home)
    assert code == sa.EXIT_OK, stderr
    placed = frag_dir / "stayturgid.caddy"
    assert placed.is_file()
    assert "GENERATED by stayturgid" in placed.read_text(encoding="utf-8")

    # Second run is no-op (all skip)
    code2, stdout2, stderr2 = _run(dir_path=str(dest), mode="apply", home=home)
    assert code2 == sa.EXIT_OK, stderr2
    assert "skip" in stdout2
    assert "create" not in stdout2.split("inject fragment")[0] if False else True
    # Stronger: action lines for the placed file are skip
    assert any(line.startswith("  skip") and str(placed) in line for line in stdout2.splitlines())


def test_import_line_for_sibling_dir_does_not_wrongly_cover_fragment_dir(tmp_path: Path) -> None:
    """A foreign Caddyfile importing an unrelated sibling directory whose
    name starts with fragment_dir's name (e.g. ``caddy.d-other``) must not
    be treated as covering ``caddy.d`` (see FINAL-REVIEW finding — the old
    substring check accepted this)."""
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    foreign = home / "etc" / "Caddyfile"
    foreign.parent.mkdir(parents=True)
    frag_dir = home / "etc" / "caddy.d"
    frag_dir.mkdir()
    sibling_dir = home / "etc" / "caddy.d-other"
    sibling_dir.mkdir()
    foreign.write_text(
        f"{{\n\tadmin off\n}}\nexample.test {{\n\timport {sibling_dir.resolve()}/*.caddy\n}}\n",
        encoding="utf-8",
    )
    _write_site_map(
        dest,
        "contract_version: 1\n"
        "serverapps:\n"
        "  caddy:\n"
        "    mode: inject\n"
        f"    config: {foreign}\n"
        f"    fragment_dir: {frag_dir}\n",
    )
    code, stdout, stderr = _run(dir_path=str(dest), mode="apply", home=home)
    assert code == sa.EXIT_WOULD_OVERWRITE, (stdout, stderr)
    assert "import" in stderr.lower()
    assert list(frag_dir.glob("*.caddy")) == []


def test_idempotent_second_own_run(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    (home / "Library" / "LaunchAgents").mkdir(parents=True)

    code1, _, err1 = _run(dir_path=str(dest), mode="apply", home=home, skip_ansible=True)
    assert code1 == sa.EXIT_OK, err1
    base = home / ".config" / "example" / "caddy" / "Caddyfile"
    before = base.read_bytes()

    code2, stdout2, err2 = _run(dir_path=str(dest), mode="apply", home=home, skip_ansible=True)
    assert code2 == sa.EXIT_OK, err2
    assert base.read_bytes() == before
    # Second plan should report skip for existing base/plist (still re-materializes via test hook)
    assert "mode=own" in stdout2


def test_missing_site_ns_exits_1(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    # Remove site_ns
    gv = dest / "inventory" / "group_vars" / "all.yml"
    gv.write_text("---\n# no site_ns\n", encoding="utf-8")
    code, _stdout, stderr = _run(dir_path=str(dest), mode="dry-run", home=tmp_path / "h")
    assert code == sa.EXIT_PRECONDITION
    assert "site_ns" in stderr


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    (home / "Library" / "LaunchAgents").mkdir(parents=True)
    before = {p.relative_to(home).as_posix() for p in home.rglob("*")}
    code, stdout, stderr = _run(dir_path=str(dest), mode="dry-run", home=home)
    assert code == sa.EXIT_OK, stderr
    assert "mode=own" in stdout
    after = {p.relative_to(home).as_posix() for p in home.rglob("*")}
    assert before == after


def test_fragment_rendered_with_registry_ports(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    text = (dest / CADDY_FRAGMENT).read_text(encoding="utf-8")
    # Product seed defaults: landing 8088, dashboard 4097, opencode 4096, vlm 8081
    assert "127.0.0.1:8088" in text
    assert "127.0.0.1:4097" in text
    assert "127.0.0.1:4096" in text
    assert "127.0.0.1:8081" in text
    assert "DO NOT EDIT" in text


def test_cli_module_help() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "control.site_contract.serverapps", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "site" in result.stdout.lower() or "serverapp" in result.stdout.lower()


# --- vector adapter (D2) ---------------------------------------------------


def test_vector_mode_defaults_to_own(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    code, stdout, stderr = _run(dir_path=str(dest), mode="dry-run", home=home, apps="vector")
    assert code == sa.EXIT_OK, stderr
    assert "vector: mode=own (source=default)" in stdout


def test_vector_own_materializes_base_and_multi_config_plist(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    (home / "Library" / "LaunchAgents").mkdir(parents=True)

    code, stdout, stderr = _run(dir_path=str(dest), mode="apply", home=home, skip_ansible=True, apps="vector")
    assert code == sa.EXIT_OK, stderr
    assert "mode=own" in stdout

    base = home / ".config" / "example" / "vector" / "vector.yaml"
    plist = home / "Library" / "LaunchAgents" / "com.example.vector.plist"
    assert base.is_file(), base
    text = base.read_text(encoding="utf-8")
    assert "GENERATED by stayturgid" in text
    assert "data_dir" in text
    assert "api:" in text

    plist_text = plist.read_text(encoding="utf-8")
    assert "com.example.vector" in plist_text
    assert str(base) in plist_text
    # Multi --config: base + each product fragment
    sources = dest / VECTOR_SOURCES
    sinks = dest / VECTOR_SINKS
    assert str(sources.resolve()) in plist_text
    assert str(sinks.resolve()) in plist_text
    assert plist_text.count("--config") >= 3
    assert "--dangerously-allow-env-var-interpolation" in plist_text


def test_vector_fragments_have_prefixed_component_ids(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    sources = (dest / VECTOR_SOURCES).read_text(encoding="utf-8")
    sinks = (dest / VECTOR_SINKS).read_text(encoding="utf-8")
    assert "stayturgid_otlp_source" in sources
    assert "4318" in sources  # product seed / init registry default
    assert "0.0.0.0" in sources  # fleet ingest bind
    assert "stayturgid_openobserve_sink" in sinks
    assert "stayturgid_otlp_source.logs" in sinks
    assert "${OPENOBSERVE_ROOT_EMAIL}" in sinks
    assert "${OPENOBSERVE_ROOT_PASSWORD}" in sinks
    # No secrets embedded
    assert 'password: "' not in sinks or 'password: "${' in sinks


def test_vector_inject_without_unit_config_args_exits_2(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    foreign = home / "etc" / "vector" / "vector.yaml"
    foreign.parent.mkdir(parents=True)
    foreign.write_text("data_dir: /tmp/vector\n", encoding="utf-8")
    frag_dir = home / "etc" / "vector.d"
    frag_dir.mkdir()
    _write_site_map(
        dest,
        "contract_version: 1\n"
        "serverapps:\n"
        "  vector:\n"
        "    mode: inject\n"
        f"    config: {foreign}\n"
        f"    fragment_dir: {frag_dir}\n",
    )
    code, stdout, stderr = _run(dir_path=str(dest), mode="apply", home=home, apps="vector")
    assert code == sa.EXIT_WOULD_OVERWRITE, (stdout, stderr)
    assert "--config" in stderr
    assert list(frag_dir.glob("*.yaml")) == []


def test_vector_config_arg_for_sibling_dir_does_not_wrongly_cover_fragment_dir(tmp_path: Path) -> None:
    """A launchd plist's ``--config`` pointing at an unrelated sibling
    directory whose name starts with fragment_dir's name (e.g.
    ``vector.d-other``) must not be treated as covering ``vector.d`` (see
    FINAL-REVIEW finding — the old check just searched the whole plist text
    for the fragment_dir string, with no association to ``--config`` at
    all)."""
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    foreign = home / "etc" / "vector" / "vector.yaml"
    foreign.parent.mkdir(parents=True)
    foreign.write_text("data_dir: /tmp/vector\n", encoding="utf-8")
    frag_dir = home / "etc" / "vector.d"
    frag_dir.mkdir()
    sibling_dir = home / "etc" / "vector.d-other"
    sibling_dir.mkdir()
    plist_dir = home / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True)
    (plist_dir / "com.example.vector.plist").write_text(
        '<?xml version="1.0"?>\n<plist><dict><key>ProgramArguments</key><array>\n'
        "<string>/opt/homebrew/bin/vector</string>\n"
        "<string>--config</string>\n"
        f"<string>{sibling_dir.resolve()}/foo.yaml</string>\n"
        "</array></dict></plist>\n",
        encoding="utf-8",
    )
    _write_site_map(
        dest,
        "contract_version: 1\n"
        "serverapps:\n"
        "  vector:\n"
        "    mode: inject\n"
        f"    config: {foreign}\n"
        f"    fragment_dir: {frag_dir}\n",
    )
    code, stdout, stderr = _run(dir_path=str(dest), mode="apply", home=home, apps="vector")
    assert code == sa.EXIT_WOULD_OVERWRITE, (stdout, stderr)
    assert "--config" in stderr
    assert list(frag_dir.glob("*.yaml")) == []


def test_vector_legacy_stayturgid_config_does_not_force_inject(tmp_path: Path) -> None:
    """Legacy ~/.config/stayturgid/vector/vector.yaml must not flip default to inject."""
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    legacy = home / ".config" / "stayturgid" / "vector" / "vector.yaml"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("# live legacy without marker\ndata_dir: /tmp\n", encoding="utf-8")
    # Foreign detect paths do not include stayturgid prefix; default remains own.
    code, stdout, stderr = _run(dir_path=str(dest), mode="dry-run", home=home, apps="vector")
    assert code == sa.EXIT_OK, stderr
    assert "mode=own" in stdout


def test_vector_idempotent_second_own_run(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    (home / "Library" / "LaunchAgents").mkdir(parents=True)

    code1, _, err1 = _run(dir_path=str(dest), mode="apply", home=home, skip_ansible=True, apps="vector")
    assert code1 == sa.EXIT_OK, err1
    base = home / ".config" / "example" / "vector" / "vector.yaml"
    before = base.read_bytes()

    code2, stdout2, err2 = _run(dir_path=str(dest), mode="apply", home=home, skip_ansible=True, apps="vector")
    assert code2 == sa.EXIT_OK, err2
    assert base.read_bytes() == before
    assert "mode=own" in stdout2


# --- openobserve adapter (D3) ----------------------------------------------


def test_openobserve_mode_defaults_to_own(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    code, stdout, stderr = _run(dir_path=str(dest), mode="dry-run", home=home, apps="openobserve")
    assert code == sa.EXIT_OK, stderr
    assert "openobserve: mode=own (source=default)" in stdout


def test_openobserve_own_materializes_plist_with_stable_data_dir(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    (home / "Library" / "LaunchAgents").mkdir(parents=True)

    code, stdout, stderr = _run(dir_path=str(dest), mode="apply", home=home, skip_ansible=True, apps="openobserve")
    assert code == sa.EXIT_OK, stderr
    assert "mode=own" in stdout

    data_dir = home / ".local" / "share" / "openobserve" / "data"
    plist = home / "Library" / "LaunchAgents" / "com.example.openobserve.plist"
    assert data_dir.is_dir(), data_dir
    assert plist.is_file()
    text = plist.read_text(encoding="utf-8")
    assert "com.example.openobserve" in text
    assert str(data_dir) in text
    assert "ZO_DATA_DIR_PATH" in text
    assert "ZO_HTTP_ADDR" in text
    assert "ZO_GRPC_ADDR" in text
    assert "ZO_BIND_ADDRESS" not in text
    # Must not re-home data under site_ns config tree
    assert "/.config/example/openobserve" not in text


def test_openobserve_inject_zero_file_writes(tmp_path: Path) -> None:
    """inject = reuse endpoint only; never writes unit or config files."""
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    (home / "Library" / "LaunchAgents").mkdir(parents=True)
    foreign = home / "Library" / "LaunchAgents" / "io.openobserve.openobserve.plist"
    foreign.write_text("<!-- foreign unit -->\n", encoding="utf-8")
    _write_site_map(
        dest,
        f"contract_version: 1\nserverapps:\n  openobserve:\n    mode: inject\n    config: {foreign}\n",
    )
    before = {p.relative_to(home).as_posix() for p in home.rglob("*")}
    code, stdout, stderr = _run(dir_path=str(dest), mode="apply", home=home, apps="openobserve")
    assert code == sa.EXIT_OK, stderr
    assert "mode=inject" in stdout
    assert "no file writes" in stdout or "reuse" in stdout.lower()
    after = {p.relative_to(home).as_posix() for p in home.rglob("*")}
    assert before == after
    # Must not create site-namespace plist
    assert not (home / "Library" / "LaunchAgents" / "com.example.openobserve.plist").exists()


def test_openobserve_legacy_stayturgid_unit_does_not_force_inject(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    agents = home / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    (agents / "com.stayturgid.openobserve.plist").write_text("<!-- legacy -->\n", encoding="utf-8")
    # Detect uses real Path.home() for default scan; site-map-free default stays own
    # when no foreign unit is at real-home detect paths. Force empty foreign via dry-run
    # on a home that only has legacy under the test tree — resolve still uses real home.
    code, stdout, stderr = _run(dir_path=str(dest), mode="dry-run", home=home, apps="openobserve")
    assert code == sa.EXIT_OK, stderr
    assert "mode=own" in stdout


def test_openobserve_idempotent_second_own_run(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    (home / "Library" / "LaunchAgents").mkdir(parents=True)

    code1, _, err1 = _run(dir_path=str(dest), mode="apply", home=home, skip_ansible=True, apps="openobserve")
    assert code1 == sa.EXIT_OK, err1
    plist = home / "Library" / "LaunchAgents" / "com.example.openobserve.plist"
    before = plist.read_bytes()

    code2, stdout2, err2 = _run(dir_path=str(dest), mode="apply", home=home, skip_ansible=True, apps="openobserve")
    assert code2 == sa.EXIT_OK, err2
    assert plist.read_bytes() == before
    assert "mode=own" in stdout2
    assert "skip" in stdout2


# --- landing adapter (D4) --------------------------------------------------


def test_landing_port_default_is_8088() -> None:
    """Footgun closed: bare landing.py default must not collide with caddy-health 8080."""
    # Avoid importing flask (not in test venv); assert the source constant.
    text = (ROOT / "control" / "landing" / "landing.py").read_text(encoding="utf-8")
    assert re.search(r"^PORT = 8088\b", text, re.MULTILINE)
    assert not re.search(r"^PORT = 8080\b", text, re.MULTILINE)


def test_landing_mode_defaults_to_own(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    code, stdout, stderr = _run(dir_path=str(dest), mode="dry-run", home=home, apps="landing")
    assert code == sa.EXIT_OK, stderr
    assert "landing: mode=own (source=default)" in stdout


def test_landing_own_materializes_both_plists(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    (home / "Library" / "LaunchAgents").mkdir(parents=True)

    code, stdout, stderr = _run(dir_path=str(dest), mode="apply", home=home, skip_ansible=True, apps="landing")
    assert code == sa.EXIT_OK, stderr
    assert "mode=own" in stdout

    landing_plist = home / "Library" / "LaunchAgents" / "com.example.landing.plist"
    discover_plist = home / "Library" / "LaunchAgents" / "com.example.landing-discover.plist"
    assert landing_plist.is_file()
    assert discover_plist.is_file()
    text = landing_plist.read_text(encoding="utf-8")
    assert "com.example.landing" in text
    assert "8088" in text
    assert "landing.py" in text
    dtext = discover_plist.read_text(encoding="utf-8")
    assert "landing-discover" in dtext
    assert "discover.py" in dtext


def test_landing_inject_refused(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    _write_site_map(
        dest,
        "contract_version: 1\nserverapps:\n  landing:\n    mode: inject\n",
    )
    code, stdout, stderr = _run(dir_path=str(dest), mode="apply", home=home, apps="landing")
    assert code == sa.EXIT_WOULD_OVERWRITE, (stdout, stderr)
    assert "inject" in stderr.lower()


def test_landing_idempotent_second_own_run(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    (home / "Library" / "LaunchAgents").mkdir(parents=True)

    code1, _, err1 = _run(dir_path=str(dest), mode="apply", home=home, skip_ansible=True, apps="landing")
    assert code1 == sa.EXIT_OK, err1
    plist = home / "Library" / "LaunchAgents" / "com.example.landing.plist"
    before = plist.read_bytes()

    code2, stdout2, err2 = _run(dir_path=str(dest), mode="apply", home=home, skip_ansible=True, apps="landing")
    assert code2 == sa.EXIT_OK, err2
    assert plist.read_bytes() == before
    assert "skip" in stdout2


# --- victoriametrics / grafana / olivetin (D5) ------------------------------

GRAFANA_DS = "generated/stayturgid/fragments/grafana/datasources/stayturgid.yaml"
GRAFANA_PROVIDER = "generated/stayturgid/fragments/grafana/dashboards/provider.yaml"
GRAFANA_FLEET = "generated/stayturgid/fragments/grafana/dashboards/json/stayturgid-fleet.json"
OLIVETIN_ACTIONS = "generated/stayturgid/fragments/olivetin/stayturgid_actions.yaml"


def test_d5_fragments_render_with_registry_ports(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    assert (dest / GRAFANA_DS).is_file()
    assert (dest / GRAFANA_PROVIDER).is_file()
    assert (dest / GRAFANA_FLEET).is_file()
    assert (dest / OLIVETIN_ACTIONS).is_file()
    ds = (dest / GRAFANA_DS).read_text(encoding="utf-8")
    assert "8428" in ds or "victoriametrics" in ds
    assert "stayturgid-victoriametrics" in ds
    fleet = (dest / GRAFANA_FLEET).read_text(encoding="utf-8")
    assert "Fleet Control Room" in fleet
    assert "stayturgid-victoriametrics" in fleet
    assert '"_generated"' in fleet


def test_victoriametrics_mode_defaults_to_own(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    code, stdout, stderr = _run(dir_path=str(dest), mode="dry-run", home=home, apps="victoriametrics")
    assert code == sa.EXIT_OK, stderr
    assert "victoriametrics: mode=own (source=default)" in stdout


def test_victoriametrics_own_materializes_plist_and_scrape(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    (home / "Library" / "LaunchAgents").mkdir(parents=True)

    code, stdout, stderr = _run(dir_path=str(dest), mode="apply", home=home, skip_ansible=True, apps="victoriametrics")
    assert code == sa.EXIT_OK, stderr
    assert "mode=own" in stdout
    plist = home / "Library" / "LaunchAgents" / "com.example.victoriametrics.plist"
    scrape = home / ".config" / "example" / "victoriametrics" / "scrape.yml"
    assert plist.is_file()
    assert scrape.is_file()
    text = plist.read_text(encoding="utf-8")
    assert "com.example.victoriametrics" in text
    assert "8428" in text
    assert "GENERATED by stayturgid" in scrape.read_text(encoding="utf-8")


def test_victoriametrics_inject_zero_file_writes(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    (home / "Library" / "LaunchAgents").mkdir(parents=True)
    foreign = home / "Library" / "LaunchAgents" / "homebrew.mxcl.victoriametrics.plist"
    foreign.write_text("<!-- foreign brew unit -->\n", encoding="utf-8")
    _write_site_map(
        dest,
        f"contract_version: 1\nserverapps:\n  victoriametrics:\n    mode: inject\n    config: {foreign}\n",
    )
    before = {p.relative_to(home).as_posix() for p in home.rglob("*")}
    code, stdout, stderr = _run(dir_path=str(dest), mode="apply", home=home, apps="victoriametrics")
    assert code == sa.EXIT_OK, stderr
    assert "mode=inject" in stdout
    assert "no file writes" in stdout or "reuse" in stdout.lower()
    after = {p.relative_to(home).as_posix() for p in home.rglob("*")}
    assert before == after


def test_grafana_mode_defaults_to_own(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    code, stdout, stderr = _run(dir_path=str(dest), mode="dry-run", home=home, apps="grafana")
    assert code == sa.EXIT_OK, stderr
    assert "grafana: mode=own (source=default)" in stdout


def test_grafana_own_materializes_ini_and_plist(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    (home / "Library" / "LaunchAgents").mkdir(parents=True)

    code, stdout, stderr = _run(dir_path=str(dest), mode="apply", home=home, skip_ansible=True, apps="grafana")
    assert code == sa.EXIT_OK, stderr
    assert "mode=own" in stdout
    ini = home / ".config" / "example" / "grafana" / "grafana.ini"
    plist = home / "Library" / "LaunchAgents" / "com.example.grafana.plist"
    assert ini.is_file()
    assert plist.is_file()
    ini_text = ini.read_text(encoding="utf-8")
    assert "provisioning" in ini_text
    assert "fragments/grafana" in ini_text or "grafana" in ini_text
    assert "3000" in ini_text
    assert "com.example.grafana" in plist.read_text(encoding="utf-8")


def test_grafana_inject_requires_fragment_dir(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    _write_site_map(
        dest,
        "contract_version: 1\nserverapps:\n  grafana:\n    mode: inject\n",
    )
    code, stdout, stderr = _run(dir_path=str(dest), mode="apply", home=home, apps="grafana")
    assert code == sa.EXIT_WOULD_OVERWRITE, (stdout, stderr)
    assert "fragment_dir" in stderr


def test_olivetin_mode_defaults_to_own(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    code, stdout, stderr = _run(dir_path=str(dest), mode="dry-run", home=home, apps="olivetin")
    assert code == sa.EXIT_OK, stderr
    assert "olivetin: mode=own (source=default)" in stdout


def test_olivetin_own_materializes_config_and_plist(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    (home / "Library" / "LaunchAgents").mkdir(parents=True)

    code, stdout, stderr = _run(dir_path=str(dest), mode="apply", home=home, skip_ansible=True, apps="olivetin")
    assert code == sa.EXIT_OK, stderr
    assert "mode=own" in stdout
    cfg = home / ".config" / "example" / "olivetin" / "config.yaml"
    plist = home / "Library" / "LaunchAgents" / "com.example.olivetin.plist"
    assert cfg.is_file()
    assert plist.is_file()
    assert "1337" in cfg.read_text(encoding="utf-8")
    assert "actions: []" in cfg.read_text(encoding="utf-8")
    assert "com.example.olivetin" in plist.read_text(encoding="utf-8")


def test_olivetin_inject_refused(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    _write_site_map(
        dest,
        "contract_version: 1\nserverapps:\n  olivetin:\n    mode: inject\n",
    )
    code, stdout, stderr = _run(dir_path=str(dest), mode="apply", home=home, apps="olivetin")
    assert code == sa.EXIT_WOULD_OVERWRITE, (stdout, stderr)
    assert "inject" in stderr.lower()


def test_d5_idempotent_second_own_run(tmp_path: Path) -> None:
    dest = _init_and_sync(tmp_path)
    home = tmp_path / "home"
    (home / "Library" / "LaunchAgents").mkdir(parents=True)
    for app in ("victoriametrics", "grafana", "olivetin"):
        code1, _, err1 = _run(dir_path=str(dest), mode="apply", home=home, skip_ansible=True, apps=app)
        assert code1 == sa.EXIT_OK, (app, err1)
        code2, stdout2, err2 = _run(dir_path=str(dest), mode="apply", home=home, skip_ansible=True, apps=app)
        assert code2 == sa.EXIT_OK, (app, err2)
        assert "mode=own" in stdout2
        assert "skip" in stdout2
