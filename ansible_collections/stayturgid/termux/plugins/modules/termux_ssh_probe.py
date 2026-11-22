#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: termux_ssh_probe
short_description: Banner and key-exchange probe of a Termux sshd from the control node
description:
  - >-
    Connects to the phone's sshd, reads the identification banner, sends one and
    checks that the server's first packet is SSH_MSG_KEXINIT. No authentication.
  - >-
    Catches what C(sshd -t), C(sv status) and an open port cannot: a listener that
    resets every login (C(kex_exchange_identification: Connection reset by peer)),
    for example a stale listener after an C(openssh) package upgrade.
  - Runs on the control node; use with C(delegate_to: localhost).
options:
  host:
    description: Address or name to probe.
    type: str
    required: true
  port:
    description: sshd port.
    type: int
    default: 8022
  timeout:
    description: Seconds for each connect and read.
    type: float
    default: 8.0
  retries:
    description: Attempts before failing (a fresh sshd needs a moment).
    type: int
    default: 1
  delay:
    description: Seconds between attempts.
    type: float
    default: 3.0
"""

EXAMPLES = r"""
- name: A login must reach key exchange after the role
  stayturgid.termux.termux_ssh_probe:
    host: "{{ ansible_host | default(inventory_hostname) }}"
    port: "{{ ansible_port | default(8022) }}"
    retries: 5
  delegate_to: localhost
"""

RETURN = r"""
banner:
  description: The server identification string.
  type: str
attempts:
  description: Attempts used.
  type: int
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.stayturgid.android_common.plugins.module_utils.plain_run import plain_run_command
from ansible_collections.stayturgid.termux.plugins.module_utils.ssh_probe import ProbeError, probe


def main():
    module = AnsibleModule(
        argument_spec=dict(
            host=dict(type="str", required=True),
            port=dict(type="int", default=8022),
            timeout=dict(type="float", default=8.0),
            retries=dict(type="int", default=1),
            delay=dict(type="float", default=3.0),
        ),
        supports_check_mode=True,
    )
    plain_run_command(module)
    # A read-only network probe: it runs in check mode too.
    try:
        banner, attempts = probe(
            module.params["host"],
            module.params["port"],
            timeout=module.params["timeout"],
            retries=module.params["retries"],
            delay=module.params["delay"],
        )
    except ProbeError as exc:
        module.fail_json(msg=str(exc), changed=False)
    module.exit_json(changed=False, banner=banner, attempts=attempts)


if __name__ == "__main__":
    main()
