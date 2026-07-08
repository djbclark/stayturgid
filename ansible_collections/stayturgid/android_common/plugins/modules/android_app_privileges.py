#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.stayturgid.android_common.plugins.module_utils.fleet_privileges import (
    apply_profiles,
)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            device=dict(type="str", required=True),
            connect=dict(type="bool", default=True),
            profiles=dict(type="list", elements="dict", required=True),
            skip_missing_packages=dict(type="bool", default=True),
        ),
        supports_check_mode=True,
    )

    changed, results = apply_profiles(
        module.run_command,
        module.params["device"],
        module.params["profiles"] or [],
        check_mode=module.check_mode,
        skip_missing=module.params["skip_missing_packages"],
        connect=module.params["connect"],
    )
    module.exit_json(changed=changed, results=results)


if __name__ == "__main__":
    main()
