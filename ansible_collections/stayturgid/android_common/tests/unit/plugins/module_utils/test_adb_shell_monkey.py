from ansible_collections.stayturgid.android_common.plugins.module_utils import adb_shell


def test_monkey_launch_restores_the_rotation_setting():
    seen = []

    def run_command(argv, **_kw):
        seen.append(argv)
        return 0, "", ""

    adb_shell.monkey_launch(run_command, "serial", "org.example.app")
    cmd = " ".join(str(part) for part in seen[-1])
    read = cmd.index("settings get system accelerometer_rotation")
    launch = cmd.index("monkey -p org.example.app")
    restore = cmd.index("settings put system accelerometer_rotation")
    assert read < launch < restore
