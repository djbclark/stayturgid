"""A ``module.run_command`` that leaves ``$VAR`` and ``~`` in its arguments alone.

``AnsibleModule.run_command`` defaults to ``expand_user_and_vars=True``: for a list
argv it runs ``os.path.expanduser(os.path.expandvars(arg))`` on every element in
the module's own process. Our modules run on the control node and hand a *device*
script to adb as one argument, for example::

    adb -s DEV shell run-as com.termux bash -c 'export HOME=/data/...; mkdir -p "$HOME/.ssh"'

The Mac then replaces ``$HOME`` with its own home before adb sends anything, so the
phone runs ``mkdir -p "/Users/<operator>/.ssh"`` (s24, 2026-11-21: ``mkdir: cannot
create directory '/Users': Read-only file system``) and reads the wrong
``authorized_keys``. Call ``plain_run_command(module)`` once, right after the
``AnsibleModule`` is built: every later ``module.run_command`` (and every use of it
as a callable, e.g. ``adb_shell(module.run_command, ...)``) then sends its argv
verbatim. A caller that really wants expansion passes ``expand_user_and_vars=True``.
"""

from __future__ import annotations

PLAIN_MARK = "_stayturgid_plain_run_command"


def plain_run_command(module):
    """Make ``module.run_command`` default to ``expand_user_and_vars=False``; returns *module*."""
    original = module.run_command
    if getattr(original, PLAIN_MARK, False):
        return module

    def run_command(args, *positional, **kwargs):
        kwargs.setdefault("expand_user_and_vars", False)
        return original(args, *positional, **kwargs)

    setattr(run_command, PLAIN_MARK, True)
    module.run_command = run_command
    return module
