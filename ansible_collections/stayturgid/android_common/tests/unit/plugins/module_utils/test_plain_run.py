"""Unit tests for plain_run: module.run_command must not expand $VAR or ~ in a device script."""

import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "plugins", "module_utils"))

import plain_run as pr
from ansible.module_utils import basic

DEVICE_SCRIPT = 'export HOME=/data/data/com.termux/files/home\nmkdir -p "$HOME/.ssh"\ncd ~\n'
ECHO_ARG1 = [sys.executable, "-c", "import sys; sys.stdout.write(sys.argv[1])"]


class RecordingModule:
    """Just enough of AnsibleModule: records what run_command receives."""

    def __init__(self):
        self.calls = []

    def run_command(self, args, *positional, **kwargs):
        self.calls.append((args, positional, kwargs))
        return 0, "", ""


def real_module(mocker):
    mocker.patch("ansible.module_utils.basic._ANSIBLE_ARGS", json.dumps({"ANSIBLE_MODULE_ARGS": {}}).encode())
    mocker.patch("ansible.module_utils.basic._ANSIBLE_PROFILE", "legacy", create=True)
    return basic.AnsibleModule(argument_spec={})


def test_run_command_defaults_to_no_expansion():
    module = pr.plain_run_command(RecordingModule())
    module.run_command(["adb", "shell", DEVICE_SCRIPT])
    [(args, positional, kwargs)] = module.calls
    assert args == ["adb", "shell", DEVICE_SCRIPT]
    assert positional == ()
    assert kwargs == {"expand_user_and_vars": False}


def test_other_arguments_pass_through_unchanged():
    module = pr.plain_run_command(RecordingModule())
    module.run_command(["adb", "devices"], True, use_unsafe_shell=False, data="x")
    [(_args, positional, kwargs)] = module.calls
    assert positional == (True,)
    assert kwargs == {"use_unsafe_shell": False, "data": "x", "expand_user_and_vars": False}


def test_a_caller_can_still_ask_for_expansion():
    module = pr.plain_run_command(RecordingModule())
    module.run_command(["ls", "~"], expand_user_and_vars=True)
    assert module.calls[0][2] == {"expand_user_and_vars": True}


def test_wrapping_twice_does_not_stack_wrappers():
    module = RecordingModule()
    pr.plain_run_command(module)
    first = module.run_command
    assert pr.plain_run_command(module) is module
    assert module.run_command is first
    module.run_command(["adb"])
    assert len(module.calls) == 1


def test_the_wrapper_is_what_a_helper_receives_as_a_callable():
    module = pr.plain_run_command(RecordingModule())

    def helper(run_command, device):
        return run_command(["adb", "-s", device, "shell", DEVICE_SCRIPT])

    helper(module.run_command, "dev")
    assert module.calls[0][2]["expand_user_and_vars"] is False


def test_real_ansible_expands_the_mac_home_into_a_device_script_unless_wrapped(mocker, monkeypatch):
    # The s24 failure: `mkdir -p "$HOME/.ssh"` reached the phone as `mkdir -p "/Users/.../.ssh"`.
    monkeypatch.setenv("HOME", "/Users/mac-operator")
    module = real_module(mocker)

    _rc, out, _err = module.run_command([*ECHO_ARG1, DEVICE_SCRIPT])
    assert 'mkdir -p "/Users/mac-operator/.ssh"' in out
    assert "$HOME" not in out.split("mkdir", 1)[1]

    pr.plain_run_command(module)
    rc, out, _err = module.run_command([*ECHO_ARG1, DEVICE_SCRIPT])
    assert rc == 0
    assert out == DEVICE_SCRIPT
    assert "/Users/mac-operator" not in out


@pytest.mark.parametrize("variable", ["$PATH", "$TMPDIR", "$USER", "~"])
def test_real_ansible_keeps_other_mac_variables_out_of_a_device_script(mocker, monkeypatch, variable):
    monkeypatch.setenv("TMPDIR", "/var/folders/mac-tmp")
    monkeypatch.setenv("USER", "mac-operator")
    module = pr.plain_run_command(real_module(mocker))
    script = "echo %s\n" % variable
    _rc, out, _err = module.run_command([*ECHO_ARG1, script])
    assert out == script
