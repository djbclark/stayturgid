"""Static safety checks for SecretSpec boundary installation."""

from pathlib import Path

ROOT = Path(__file__).parents[2]
INSTALLER = (ROOT / "control/bin/install-sudo-secretspec").read_text()
WRAPPER = (ROOT / "control/bin/sudo-secretspec-broker").read_text()
SUDOERS = (ROOT / "control/config/sudoers.d/secretspec").read_text()


def test_installer_pins_provider_and_all_broker_components_root_owned():
    assert '"$SECRETSPEC_SOURCE"' in INSTALLER
    assert 'install -o root -g wheel -m "${MODES[$i]}" "$source_path" "$stage_path"' in INSTALLER
    for target in (
        "sudo-secretspec-engine",
        "sudo-secretspec-broker",
        "sudo-secretspec-audit",
        "sudo-secretspec",
        "sudo-secretspec-drift-check",
    ):
        assert target in INSTALLER
    assert "SECRETSPEC_INSTALL_VISUDO:-/usr/sbin/visudo" in INSTALLER
    assert '"$VISUDO" -c -f' in INSTALLER
    assert '"$VISUDO" -c' in INSTALLER


def test_installer_never_reads_or_copies_runtime_secret_files():
    for forbidden in (
        'cat "$VAULT',
        'cp "$VAULT',
        "read_text",
        "SOURCE_ENV",
        "/var/db/stayturgid-secrets/.env",
        "/var/db/stayturgid-secrets/secretspec.toml",
    ):
        assert forbidden not in INSTALLER


def test_installer_rolls_back_all_destinations_after_partial_commit():
    assert "trap rollback EXIT" in INSTALLER
    assert 'rm -f "$destination"' in INSTALLER
    assert 'install -o root -g wheel -m "$mode" "$ROLLBACK/$i" "$destination"' in INSTALLER
    assert "for ((i = ${#DESTINATIONS[@]} - 1; i >= 0; i--))" in INSTALLER
    assert "rollback_verified" in INSTALLER
    assert "exit 125" in INSTALLER


def test_installer_creates_only_value_free_ledger_inside_vault():
    assert "sudo-secretspec-audit" in INSTALLER
    assert "unsafe audit ledger path" in INSTALLER
    assert 'touch "$VAULT/broker-audit.sqlite3"' not in INSTALLER
    assert 'attempt --directory "$VAULT"' not in INSTALLER
    assert "_secretspec:staff:700" in INSTALLER


def test_installer_binds_source_destination_mode_and_revalidates_writable_sources():
    assert "installer manifest length mismatch" in INSTALLER
    assert 'before=$(metadata "$source_path")' in INSTALLER
    assert 'after=$(metadata "$source_path")' in INSTALLER
    assert '[[ "$before" == "$after" ]]' in INSTALLER
    assert '[[ "$(sha "$source_path")" == "$(sha "$stage_path")" ]]' in INSTALLER


def test_installer_rejects_operator_removable_parent_chain():
    assert "operator-removable canonical ancestor" in INSTALLER
    assert "ACL-bearing canonical ancestor" in INSTALLER
    assert "/private/var/db/stayturgid-secrets" in INSTALLER


def test_wrapper_uses_pinned_binary_and_released_schema_first():
    assert "SECRETSPEC_BIN=/usr/local/libexec/sudo-secretspec-engine" in WRAPPER
    assert "SOURCE_EXAMPLE=/usr/local/share/sudo-secretspec/secretspec.toml.example" in WRAPPER
    assert "merge and deploy the declaration first" in WRAPPER
    assert "install_released_schema" in WRAPPER
    assert 'run_spec add "$name"' not in WRAPPER
    assert "mirror %s" not in WRAPPER
    add_block = WRAPPER.split("source-add)", 1)[1].split("source-set)", 1)[0]
    assert add_block.index("install_released_schema") < add_block.index("run_spec set")
    assert "if ((rc == 0))" in add_block


def test_wrapper_audits_before_provider_and_has_terminal_trap():
    assert WRAPPER.index("audit_event attempt") < WRAPPER.index("run_spec export")
    assert WRAPPER.index("audit_event attempt") < WRAPPER.index("require_store\nset +e")
    assert "trap on_exit EXIT" in WRAPPER
    assert "audit_event failure" in WRAPPER
    assert "audit_event success" in WRAPPER


def test_sudoers_only_allows_the_fixed_wrapper():
    active = [line for line in SUDOERS.splitlines() if line and not line.startswith("#")]
    assert active
    assert all(line.endswith("/usr/local/libexec/sudo-secretspec-broker") for line in active)
    assert all("/bin/sh" not in line and "/usr/bin/env" not in line for line in active)
