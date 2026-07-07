"""Unit tests for shared/mac/adb_cli.py and obtainium sync_to_device catalogs."""
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "shared", "mac"))
import adb_cli as ac  # noqa: E402

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "obtainium", "mac"))
import sync_to_device as sync  # noqa: E402


def test_autojs_constants():
    assert ac.AUTOJS_PKG == "org.autojs.autojs6"
    assert ac.AUTOJS_PROJECT_BASE.endswith("/autojs6")


def test_sync_catalog_paths_exist():
    for which, (json_path, dest_name) in sync.CATALOGS.items():
        assert json_path.is_file(), which
        assert dest_name.startswith("stayturgid-obtainium-")
