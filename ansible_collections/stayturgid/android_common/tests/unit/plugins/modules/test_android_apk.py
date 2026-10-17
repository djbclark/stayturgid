"""Unit tests for android_apk module."""

import json
import os
import sys
from hashlib import sha256

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "plugins", "modules"))
sys.path.insert(0, os.path.join(ROOT, "plugins", "module_utils"))

import android_apk as mod
import apk_install


def test_parse_install_result_success():
    ok, reason = apk_install.parse_install_result("Performing Streamed Install\nSuccess\n")
    assert ok is True
    assert reason == "Success"


def test_parse_install_result_failure():
    ok, reason = apk_install.parse_install_result("Failure [INSTALL_FAILED_VERSION_DOWNGRADE]")
    assert ok is False
    assert "INSTALL_FAILED" in reason


def run_module(mocker, args, cmd_results=None, command_fn=None):
    stdin = json.dumps({"ANSIBLE_MODULE_ARGS": dict(args)})
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", stdin.encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)

    captured = {}
    warnings = []

    def fake_run_command(self, cmd, *a, **kw):
        if command_fn is not None:
            return command_fn(cmd)
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        for needle, result in cmd_results or []:
            if needle in joined:
                return result
        if "pm list packages" in joined:
            return (0, "", "")
        if "dumpsys package" in joined:
            return (1, "", "")
        if " install" in joined:
            return (0, "Success\n", "")
        return (0, "", "")

    def fake_exit(self, **kw):
        captured.update(kw, failed=False)
        raise SystemExit(0)

    def fake_fail(self, **kw):
        captured.update(kw, failed=True)
        raise SystemExit(1)

    mocker.patch(
        "ansible.module_utils.basic.AnsibleModule.get_bin_path", lambda self, name, required=False: "/usr/bin/" + name
    )
    mocker.patch("ansible.module_utils.basic.AnsibleModule.run_command", fake_run_command)
    mocker.patch("ansible.module_utils.basic.AnsibleModule.exit_json", fake_exit)
    mocker.patch("ansible.module_utils.basic.AnsibleModule.fail_json", fake_fail)
    mocker.patch(
        "ansible.module_utils.basic.AnsibleModule.warn",
        lambda self, msg: warnings.append(msg),
    )

    with pytest.raises(SystemExit):
        mod.main()
    captured["_warnings"] = warnings
    return captured


def test_android_apk_installs(mocker, tmp_path):
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    out = run_module(
        mocker,
        dict(
            device="dev",
            package="com.example.app",
            apk_path=str(apk),
            connect=False,
        ),
    )
    assert out.get("failed") is not True, out
    assert out["changed"] is True
    assert out["reason"] == "Success"


def test_android_apk_disables_play_protect_verifier_around_install(mocker, tmp_path):
    """The install is wrapped in a verifier off/restore pair (unsafe-app dialog)."""
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    seen = []

    def command_fn(cmd):
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        seen.append(joined)
        if "pm list packages" in joined:
            return (0, "", "")
        if "settings get global verifier_verify_adb_installs" in joined:
            return (0, "1\n", "")
        if "settings get global package_verifier_enable" in joined:
            return (0, "null\n", "")
        if " install" in joined:
            return (0, "Success\n", "")
        return (0, "", "")

    out = run_module(
        mocker,
        dict(
            device="dev",
            package="com.example.app",
            apk_path=str(apk),
            connect=False,
        ),
        command_fn=command_fn,
    )
    assert out.get("failed") is not True, out
    install_idx = next(i for i, c in enumerate(seen) if " install" in c)
    disables = [i for i, c in enumerate(seen) if "settings put global" in c and " 0" in c]
    assert len(disables) == 2 and all(i < install_idx for i in disables), seen
    restore_put = [i for i, c in enumerate(seen) if "settings put global verifier_verify_adb_installs 1" in c]
    restore_delete = [i for i, c in enumerate(seen) if "settings delete global package_verifier_enable" in c]
    assert restore_put and restore_put[0] > install_idx, seen
    assert restore_delete and restore_delete[0] > install_idx, seen


def test_android_apk_restores_verifier_on_install_failure(mocker, tmp_path):
    """A failed install must still restore the Play Protect settings."""
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    seen = []

    def command_fn(cmd):
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        seen.append(joined)
        if "pm list packages" in joined:
            return (0, "", "")
        if "settings get global" in joined:
            return (0, "1\n", "")
        if " install" in joined:
            return (1, "Failure [INSTALL_FAILED_INVALID_APK]", "")
        return (0, "", "")

    out = run_module(
        mocker,
        dict(
            device="dev",
            package="com.example.app",
            apk_path=str(apk),
            connect=False,
        ),
        command_fn=command_fn,
    )
    assert out.get("failed") is True
    restores = [c for c in seen if "settings put global" in c and c.rstrip().endswith(" 1")]
    assert len(restores) == 2, seen


def test_android_apk_accepts_locked_checksum(mocker, tmp_path):
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    out = run_module(
        mocker,
        dict(
            device="dev",
            package="com.example.app",
            apk_path=str(apk),
            checksum="sha256:" + sha256(b"PK").hexdigest(),
            connect=False,
        ),
    )
    assert out.get("failed") is not True, out
    assert out["changed"] is True


def test_android_apk_rejects_wrong_checksum(mocker, tmp_path):
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    out = run_module(
        mocker,
        dict(
            device="dev",
            package="com.example.app",
            apk_path=str(apk),
            checksum="0" * 64,
            connect=False,
        ),
    )
    assert out.get("failed") is True
    assert "checksum mismatch" in out["msg"]


def test_android_apk_install_wrapped_in_timeout(mocker, tmp_path):
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    seen_cmds = []

    def fake_run_command(self, cmd, *a, **kw):
        seen_cmds.append(cmd)
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        if "pm list packages" in joined:
            return (0, "", "")
        if "dumpsys package" in joined:
            return (1, "", "")
        if cmd[0].endswith("timeout"):
            return (0, "Success\n", "")
        return (0, "", "")

    mocker.patch(
        "ansible.module_utils.basic.AnsibleModule.get_bin_path", lambda self, name, required=False: "/usr/bin/" + name
    )
    mocker.patch("ansible.module_utils.basic.AnsibleModule.run_command", fake_run_command)
    mocker.patch(
        "ansible.module_utils.basic.AnsibleModule.exit_json", lambda self, **kw: (_ for _ in ()).throw(SystemExit(0))
    )
    mocker.patch(
        "ansible.module_utils.basic.AnsibleModule.fail_json", lambda self, **kw: (_ for _ in ()).throw(SystemExit(1))
    )

    stdin = json.dumps(
        {"ANSIBLE_MODULE_ARGS": dict(device="dev", package="com.example.app", apk_path=str(apk), connect=False)}
    )
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", stdin.encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)

    with pytest.raises(SystemExit):
        mod.main()

    # Match the adb install subcommand as a standalone argv element — a plain
    # substring check also matches the Play Protect verifier settings commands
    # (verifier_verify_adb_installs).
    install_cmds = [c for c in seen_cmds if isinstance(c, (list, tuple)) and "install" in c]
    assert len(install_cmds) == 1
    assert install_cmds[0][:3] == ["/usr/bin/timeout", "180", "adb"], install_cmds[0]


def test_android_apk_install_timeout_fails_loudly(mocker, tmp_path):
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    out = run_module(
        mocker,
        dict(device="dev", package="com.example.app", apk_path=str(apk), connect=False),
        cmd_results=[(" install", (124, "", ""))],
    )
    assert out.get("failed") is True
    assert "timed out" in out["msg"]


def test_android_apk_work_profile_install_wrapped_in_timeout(mocker, tmp_path):
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    out = run_module(
        mocker,
        dict(device="dev", package="com.example.app", apk_path=str(apk), work_profile=True, connect=False),
    )
    assert out.get("failed") is not True, out
    assert "also installed for user 10" in out["reason"]


def test_android_apk_work_profile_timeout_warns_with_dialog_hint(mocker, tmp_path):
    """Regression test for #59: a wedged work-profile install must warn with
    the same "confirmation dialog" hint as the primary install path, not just
    a bare rc number, and must not fail the whole task (best-effort)."""
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    out = run_module(
        mocker,
        dict(device="dev", package="com.example.app", apk_path=str(apk), work_profile=True, connect=False),
        cmd_results=[
            ("--user 10", (124, "", "")),
            (" install", (0, "Success\n", "")),
        ],
    )
    assert out.get("failed") is not True, out
    assert "also installed for user 10" not in out["reason"]
    assert any("timed out" in w and "confirmation dialog" in w for w in out["_warnings"]), out["_warnings"]


def test_android_apk_skips_when_present(mocker, tmp_path):
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    out = run_module(
        mocker,
        dict(
            device="dev",
            package="com.example.app",
            apk_path=str(apk),
            connect=False,
        ),
        cmd_results=[
            ("pm list packages", (0, "package:com.example.app\n", "")),
        ],
    )
    assert out["changed"] is False


def test_android_apk_reinstalls_when_locked_version_is_stale(mocker, tmp_path):
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    out = run_module(
        mocker,
        dict(
            device="dev",
            package="com.example.app",
            apk_path=str(apk),
            version_name="2.0.0",
            connect=False,
        ),
        cmd_results=[
            ("pm list packages", (0, "package:com.example.app\n", "")),
            ("dumpsys package", (0, "versionName=1.0.0\n", "")),
        ],
    )
    assert out["changed"] is True
    assert out["reason"] == "Success"


def _capture_commands(mocker, args):
    """Run the module recording every run_command invocation."""
    seen = []

    def fake_run_command(self, cmd, *a, **kw):
        seen.append(cmd)
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        if "pm list packages" in joined:
            return (0, "package:com.example.app\n", "")  # present
        if "dumpsys package" in joined:
            return (1, "", "")
        if "uninstall" in joined:
            return (0, "Success\n", "")
        if cmd[0].endswith("timeout"):
            return (0, "Success\n", "")
        return (0, "", "")

    stdin = json.dumps({"ANSIBLE_MODULE_ARGS": dict(args)})
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", stdin.encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)
    mocker.patch(
        "ansible.module_utils.basic.AnsibleModule.get_bin_path", lambda self, name, required=False: "/usr/bin/" + name
    )
    mocker.patch("ansible.module_utils.basic.AnsibleModule.run_command", fake_run_command)
    mocker.patch(
        "ansible.module_utils.basic.AnsibleModule.exit_json", lambda self, **kw: (_ for _ in ()).throw(SystemExit(0))
    )
    mocker.patch(
        "ansible.module_utils.basic.AnsibleModule.fail_json", lambda self, **kw: (_ for _ in ()).throw(SystemExit(1))
    )
    with pytest.raises(SystemExit):
        mod.main()
    return [" ".join(c) if isinstance(c, (list, tuple)) else str(c) for c in seen]


def test_android_apk_clean_uninstalls_before_install(mocker, tmp_path):
    """clean=true on a present package uninstalls before installing."""
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    cmds = _capture_commands(
        mocker,
        dict(device="dev", package="com.example.app", apk_path=str(apk), connect=False, clean=True, force=True),
    )
    uninstall_idx = next((i for i, c in enumerate(cmds) if "uninstall com.example.app" in c), None)
    install_idx = next((i for i, c in enumerate(cmds) if " install -r" in c), None)
    assert uninstall_idx is not None, cmds
    assert install_idx is not None, cmds
    assert uninstall_idx < install_idx, cmds


@pytest.mark.parametrize(
    "uninstall_rc,uninstall_err",
    [
        (1, "Failure [DELETE_FAILED_INTERNAL_ERROR]"),
        (124, ""),
    ],
    ids=["failure", "timeout"],
)
def test_android_apk_clean_uninstall_failure_fails_before_install(mocker, tmp_path, uninstall_rc, uninstall_err):
    """A failed or timed-out clean uninstall must not silently proceed to installing.

    Regression test: run_command_with_timeout()'s clean-uninstall result was
    previously discarded entirely, so a failed/timed-out uninstall silently
    fell through into an in-place `adb install -r`, defeating the native-lib
    re-extraction the `clean` flag exists for (see the module's history with
    #60). Covers both an ordinary adb failure and an rc==124 timeout, since
    run_command_with_timeout() surfaces both the same way (nonzero rc)."""
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    seen = []

    def fake_run_command(cmd):
        seen.append(cmd)
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        if "pm list packages" in joined:
            return (0, "package:com.example.app\n", "")
        if "dumpsys package" in joined:
            return (1, "", "")
        if "uninstall" in joined:
            return (uninstall_rc, "", uninstall_err)
        return (0, "", "")

    out = run_module(
        mocker,
        dict(device="dev", package="com.example.app", apk_path=str(apk), connect=False, clean=True, force=True),
        command_fn=fake_run_command,
    )

    assert out.get("failed") is True
    assert "clean reinstall" in out["msg"], out
    assert not any(" install -r" in " ".join(c) for c in seen), seen


def test_android_apk_clean_false_does_not_uninstall(mocker, tmp_path):
    """clean defaults off: a forced reinstall must not uninstall first."""
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    cmds = _capture_commands(
        mocker,
        dict(device="dev", package="com.example.app", apk_path=str(apk), connect=False, force=True),
    )
    assert not any("uninstall" in c for c in cmds), cmds


def test_android_apk_incompatible_upgrade_clean_retries(mocker, tmp_path):
    """A stale package from another signing lineage converges automatically."""
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    seen = []
    install_attempt = 0

    def fake_run_command(cmd):
        nonlocal install_attempt
        seen.append(cmd)
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        if "pm list packages" in joined:
            return (0, "package:com.example.app\n", "")
        if "dumpsys package" in joined:
            return (0, "versionName=1.0.0\n", "")
        if " uninstall " in f" {joined} ":
            return (0, "Success\n", "")
        if " install " in f" {joined} ":
            install_attempt += 1
            if install_attempt == 1:
                return (1, "Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE]\n", "")
            return (0, "Success\n", "")
        return (0, "", "")

    captured = run_module(
        mocker,
        dict(
            device="dev",
            package="com.example.app",
            apk_path=str(apk),
            version_name="2.0.0",
            connect=False,
        ),
        command_fn=fake_run_command,
    )

    commands = [" ".join(command) for command in seen]
    assert sum(" install " in f" {command} " for command in commands) == 2
    assert sum(" uninstall " in f" {command} " for command in commands) == 1
    assert "clean fallback" in captured["reason"]
    assert any("application data will be lost" in warning for warning in captured["_warnings"])


def test_android_apk_incompatible_upgrade_can_fail_without_data_loss(mocker, tmp_path):
    """A caller can explicitly reject the destructive clean fallback."""
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK")
    seen = []

    def fake_run_command(cmd):
        seen.append(cmd)
        joined = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        if "pm list packages" in joined:
            return (0, "package:com.example.app\n", "")
        if "dumpsys package" in joined:
            return (0, "versionName=1.0.0\n", "")
        if " install " in f" {joined} ":
            return (1, "Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE]\n", "")
        return (0, "", "")

    captured = run_module(
        mocker,
        dict(
            device="dev",
            package="com.example.app",
            apk_path=str(apk),
            version_name="2.0.0",
            clean_on_incompatible=False,
            connect=False,
        ),
        command_fn=fake_run_command,
    )

    commands = [" ".join(command) for command in seen]
    assert captured["failed"] is True
    assert not any(" uninstall " in f" {command} " for command in commands)


class FakeDownloadModule:
    """Just enough AnsibleModule for download_gh_release."""

    def __init__(self, tmpdir, run, bins=("gh", "aria2c")):
        self.tmpdir = str(tmpdir)
        self.bins = bins
        self.run = run
        self.calls = []
        self.warnings = []

    def get_bin_path(self, name, required=False):
        return "/usr/bin/" + name if name in self.bins or name == "timeout" else None

    def run_command(self, cmd, *a, **kw):
        self.calls.append(cmd)
        return self.run(cmd)

    def warn(self, msg):
        self.warnings.append(msg)

    def fail_json(self, **kw):
        raise AssertionError(kw)


ASSETS = json.dumps({"assets": [{"name": "app-1.apk", "url": "https://example.invalid/app-1.apk"}]})


def tool(cmd, name):
    return any(str(part).endswith("/" + name) for part in cmd)


def test_download_gh_release_uses_aria2c(tmp_path):
    def run(cmd):
        if tool(cmd, "gh") and "view" in cmd:
            return (0, ASSETS, "")
        if tool(cmd, "aria2c"):
            out = cmd[cmd.index("--dir") + 1]
            with open(os.path.join(out, cmd[cmd.index("--out") + 1]), "wb") as f:
                f.write(b"PK")
            return (0, "", "")
        raise AssertionError("unexpected %r" % cmd)

    module = FakeDownloadModule(tmp_path, run)
    path = mod.download_gh_release(module, "o/r", "app-*.apk", "v1")
    assert path.endswith("app-1.apk")
    assert not [c for c in module.calls if tool(c, "gh") and "download" in c]


def test_download_gh_release_falls_back_to_gh_and_retries(tmp_path):
    attempts = []

    def run(cmd):
        if tool(cmd, "gh") and "view" in cmd:
            return (0, ASSETS, "")
        if tool(cmd, "aria2c"):
            return (1, "", "connection reset")
        if tool(cmd, "gh") and "download" in cmd:
            attempts.append(cmd)
            if len(attempts) < 2:
                return (1, "", "unexpected EOF")
            with open(os.path.join(cmd[cmd.index("--dir") + 1], "app-1.apk"), "wb") as f:
                f.write(b"PK")
            return (0, "", "")
        raise AssertionError("unexpected %r" % cmd)

    module = FakeDownloadModule(tmp_path, run)
    assert mod.download_gh_release(module, "o/r", "app-*.apk", "v1").endswith("app-1.apk")
    assert len(attempts) == 2
    assert module.warnings and "falling back to gh" in module.warnings[0]


# --- detached_install: an APK that carries the adb transport (Tailscale) ---

TS_DEVICE = "100.64.0.1:5555"
TS_LOG_PATH = "/data/local/tmp/stayturgid-com.tailscale.ipn.log"
TS_OK_LOG = "Performing Streamed Install\nSuccess\nstayturgid-pm-rc=0\n"


class DetachedDevice:
    """A fake device: offline for the first reads of the log, then the script's log."""

    def __init__(self, log, offline_reads=1, push_rc=0, version_after="2.0.0"):
        self.log = log
        self.offline_reads = offline_reads
        self.push_rc = push_rc
        self.version_after = version_after
        self.seen = []
        self.script_started = False
        self.done = False

    def __call__(self, cmd):
        joined = " ".join(cmd)
        self.seen.append(joined)
        if " push " in joined:
            return (self.push_rc, "", "" if self.push_rc == 0 else "adb: error: failed to copy")
        if "nohup" in joined:
            self.script_started = True
            return (0, "", "")
        if "cat " + TS_LOG_PATH in joined:
            if self.offline_reads > 0:
                self.offline_reads -= 1
                return (1, "", "error: device offline")
            self.done = True
            return (0, self.log, "")
        if "pm list packages" in joined:
            return (0, "package:com.tailscale.ipn\n", "")
        if "dumpsys package" in joined:
            return (0, "versionName=%s\n" % (self.version_after if self.done else "1.0.0"), "")
        if "settings get global verifier_verify_adb_installs" in joined:
            return (0, "1\n", "")
        if "settings get global package_verifier_enable" in joined:
            return (0, "null\n", "")
        return (0, "", "")


@pytest.fixture
def fake_clock(mocker):
    clock = {"t": 0}
    mocker.patch.object(mod, "_now", lambda: clock["t"])
    mocker.patch.object(mod, "_sleep", lambda seconds: clock.__setitem__("t", clock["t"] + seconds))
    return clock


def detached_args(tmp_path, **extra):
    apk = tmp_path / "ts.apk"
    apk.write_bytes(b"PK")
    return dict(
        device=TS_DEVICE,
        package="com.tailscale.ipn",
        apk_path=str(apk),
        version_name="2.0.0",
        detached_install=True,
        **extra,
    )


def test_detached_install_pushes_starts_script_and_survives_offline_read(mocker, tmp_path, fake_clock):
    device = DetachedDevice(TS_OK_LOG, offline_reads=1)
    out = run_module(mocker, detached_args(tmp_path), command_fn=device)
    assert out.get("failed") is not True, out
    assert out["changed"] is True
    assert out["reason"] == "Success"

    seen = device.seen
    push = next(i for i, c in enumerate(seen) if " push " in c)
    assert seen[push].endswith("/data/local/tmp/stayturgid-com.tailscale.ipn.apk")
    start = next(i for i, c in enumerate(seen) if "nohup" in c)
    script = seen[start]
    assert push < start
    assert "pm install -r --user 0 /data/local/tmp/stayturgid-com.tailscale.ipn.apk" in script
    # The verifier goes off and back on inside the script, restored to its values from before.
    assert script.index("settings put global verifier_verify_adb_installs 0") < script.index("pm install")
    assert script.index("pm install") < script.index("settings put global verifier_verify_adb_installs 1")
    assert script.index("pm install") < script.index("settings delete global package_verifier_enable")
    assert "rm -f /data/local/tmp/stayturgid-com.tailscale.ipn.apk" in script
    # Nothing on the Mac side touches the verifier or runs a plain adb install.
    assert not [c for c in seen if "settings put" in c and "nohup" not in c]
    assert not [c for c in seen if " install " in c and "pm install" not in c]
    # Two log reads (offline, then ready), each preceded by a reconnect.
    reads = [i for i, c in enumerate(seen) if "cat " + TS_LOG_PATH in c]
    assert len(reads) == 2
    connects = [i for i, c in enumerate(seen) if " connect " in c and i > start]
    assert len(connects) >= 2
    assert any("rm -f " + TS_LOG_PATH in c for c in seen[reads[-1] :])
    assert fake_clock["t"] == mod.DETACHED_POLL_SECONDS


def test_detached_install_failure_log_fails(mocker, tmp_path, fake_clock):
    log = "Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE]\nstayturgid-pm-rc=1\n"
    device = DetachedDevice(log, offline_reads=0)
    out = run_module(mocker, detached_args(tmp_path), command_fn=device)
    assert out["failed"] is True
    assert "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in out["msg"]
    # No clean fallback in detached mode: nothing uninstalls the package.
    assert not [c for c in device.seen if "uninstall" in c]


def test_detached_install_downgrade_is_not_uninstalled(mocker, tmp_path, fake_clock):
    log = "Failure [INSTALL_FAILED_VERSION_DOWNGRADE]\nstayturgid-pm-rc=1\n"
    out = run_module(mocker, detached_args(tmp_path), command_fn=DetachedDevice(log, offline_reads=0))
    assert out["failed"] is True
    assert "newer com.tailscale.ipn" in out["msg"]


def test_detached_install_timeout_fails_with_message(mocker, tmp_path, fake_clock):
    device = DetachedDevice(TS_OK_LOG, offline_reads=10**6)
    out = run_module(mocker, detached_args(tmp_path, detached_timeout=20), command_fn=device)
    assert out["failed"] is True
    assert "device did not come back within 20 s" in out["msg"]
    assert "check versionName" in out["msg"]


def test_detached_install_wrong_version_after_success_fails(mocker, tmp_path, fake_clock):
    device = DetachedDevice(TS_OK_LOG, offline_reads=0, version_after="1.5.0")
    out = run_module(mocker, detached_args(tmp_path), command_fn=device)
    assert out["failed"] is True
    assert "1.5.0" in out["msg"] and "2.0.0" in out["msg"]


def test_detached_install_push_failure_never_starts_script(mocker, tmp_path, fake_clock):
    device = DetachedDevice(TS_OK_LOG, push_rc=1)
    out = run_module(mocker, detached_args(tmp_path), command_fn=device)
    assert out["failed"] is True
    assert "adb push failed" in out["msg"]
    assert device.script_started is False


@pytest.mark.parametrize("option", ["clean", "work_profile"])
def test_detached_install_refuses_unsupported_combinations(mocker, tmp_path, option):
    out = run_module(mocker, detached_args(tmp_path, **{option: True}))
    assert out["failed"] is True
    assert option in out["msg"]


def test_detached_script_runs_under_sh(tmp_path):
    """Run the rendered script against stub pm/settings: quoting and order hold."""
    import subprocess
    import time

    bindir = tmp_path / "bin"
    bindir.mkdir()
    state = tmp_path / "state"
    state.mkdir()
    (bindir / "pm").write_text('#!/bin/sh\necho "pm $*" >> %s/calls\necho Success\n' % state)
    (bindir / "settings").write_text('#!/bin/sh\necho "settings $*" >> %s/calls\n' % state)
    for stub in bindir.iterdir():
        stub.chmod(0o755)
    remote = tmp_path / "remote"
    remote.mkdir()
    script = mod.detached_script(
        "com.tailscale.ipn",
        "0",
        "com.android.vending",
        [],
        {"verifier_verify_adb_installs": "1", "package_verifier_enable": "null"},
    ).replace("/data/local/tmp", str(remote))
    (remote / "stayturgid-com.tailscale.ipn.apk").write_bytes(b"PK")
    env = dict(os.environ, PATH="%s:%s" % (bindir, os.environ["PATH"]))
    subprocess.run(["/bin/sh", "-c", script], env=env, check=True, timeout=10)
    log = remote / "stayturgid-com.tailscale.ipn.log"
    deadline = time.monotonic() + 10
    while not log.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    text = log.read_text()
    assert mod.DETACHED_DONE_RE.search(text) and mod.DETACHED_DONE_RE.search(text).group(1) == "0"
    assert "Success" in text
    assert not (remote / "stayturgid-com.tailscale.ipn.apk").exists()
    calls = (state / "calls").read_text().splitlines()
    assert calls[0] == "settings put global verifier_verify_adb_installs 0"
    assert calls[2].startswith("pm install -r --user 0 -i com.android.vending ")
    assert calls[3:] == [
        "settings put global verifier_verify_adb_installs 1",
        "settings delete global package_verifier_enable",
    ]
