"""Regression tests for the normal fleet deploy's single convergence path."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
POST_UI_TASKS = ROOT / "ansible_collections/stayturgid/fleet/roles/post_ui/tasks/main.yml"


def test_site_runs_fleet_convergence_once():
    site = (ROOT / "ansible/playbooks/site.yml").read_text(encoding="utf-8")

    assert site.count("import_playbook: fleet/fleet.yml") == 1
    assert "post-ui-app-stores" not in site
    assert site.index("fleet/ensure-bootstrap-apks.yml") < site.index("fleet/verify-bootstrap-apks.yml")


def test_obtainium_import_is_not_duplicated_through_screen_control():
    post_ui = POST_UI_TASKS.read_text(encoding="utf-8")

    assert "import_obtainium_catalog" not in post_ui
    assert "Import Obtainium catalog" not in post_ui


def test_post_ui_unlock_is_gated_by_enabled_app_stores():
    tasks = yaml.safe_load(POST_UI_TASKS.read_text(encoding="utf-8"))

    assert tasks[0]["when"] == [
        "not ansible_check_mode",
        "stayturgid_app_stores_enabled | default(false) | bool",
    ]
    assert tasks[1]["when"] == tasks[0]["when"]


def test_main_obtainium_role_uses_only_headless_import():
    role_tasks = (ROOT / "ansible_collections/stayturgid/obtainium/roles/obtainium_apps/tasks/main.yml").read_text(
        encoding="utf-8"
    )

    assert "headless_import: true" in role_tasks
    assert "import_ui:" not in role_tasks


def test_ensure_apps_can_disable_destructive_incompatible_upgrade_cleanup():
    tasks_path = ROOT / "ansible_collections/stayturgid/android_common/roles/ensure_apps/tasks/main.yml"
    tasks = yaml.safe_load(tasks_path.read_text(encoding="utf-8"))
    ensure_apks = next(task for task in tasks if task["name"].startswith("Ensure APK apps"))

    assert (
        ensure_apks["stayturgid.android_common.android_apk"]["clean_on_incompatible"]
        == "{{ item.clean_on_incompatible | default(omit) }}"
    )
