"""A version downgrade must never take the uninstall-and-reinstall fallback."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "android_apk", ROOT / "ansible_collections/stayturgid/android_common/plugins/modules/android_apk.py"
)
assert _spec is not None
android_apk = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(android_apk)


def test_downgrade_is_not_a_clean_fallback_reason():
    assert not android_apk.incompatible_install_failure("Failure [INSTALL_FAILED_VERSION_DOWNGRADE]")


def test_real_conflicts_still_take_the_fallback():
    for marker in (
        "INSTALL_FAILED_DUPLICATE_PACKAGE",
        "INSTALL_FAILED_SHARED_USER_INCOMPATIBLE",
        "INSTALL_FAILED_UPDATE_INCOMPATIBLE",
    ):
        assert android_apk.incompatible_install_failure("Failure [%s: x]" % marker)
