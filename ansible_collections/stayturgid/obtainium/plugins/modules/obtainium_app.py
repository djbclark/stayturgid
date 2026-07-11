#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: obtainium_app
short_description: Render the Obtainium import catalog from terse app specs
description:
  - Declaratively renders an Obtainium export/import JSON on the device from
    terse app specifications, expanding each into Obtainium's verbose
    C(additionalSettings) format with sane GitHub-source defaults.
  - Runs on-device (Termux over SSH), so no Mac-side adb is needed.
  - Obtainium has no CLI; on Mac use C(control/tools/obtainium/import_catalog.py) (or
    C(sync_to_device.py)) to apply the catalog via obtainium://apps deep link.
    With C(import_ui=true) the module only launches the legacy file VIEW intent
    when the catalog changed.
  - Optionally reports which app packages are currently installed, via the
    privileged localhost:5555 shell (best effort).
options:
  apps:
    description:
      - App specifications. Each requires C(id) (package name) and C(url)
        (GitHub repo URL). Optional keys - C(name), C(author),
        C(categories) (list), and C(settings), a dict merged over the
        baseline additionalSettings (e.g. C(apkFilterRegEx), C(about),
        C(autoApkFilterByArch)).
    type: list
    elements: dict
    required: true
  catalog_path:
    description: Where to render the catalog on the device.
    type: str
    default: /sdcard/Download/stayturgid-obtainium-apps.json
  extra_settings:
    description: Top-level Obtainium C(settings) block for the export.
    type: dict
    default: {"groupByCategory": true}
  import_ui:
    description:
      - Launch Obtainium's import UI when the catalog changed (interrupts
        whatever is on screen; the user confirms the import in-app).
    type: bool
    default: false
  check_installed:
    description:
      - Report per-app installed state via the localhost:5555 privileged
        shell. Best effort - skipped silently when the shell is unreachable.
    type: bool
    default: true
"""

EXAMPLES = r"""
- name: Render Obtainium catalog
  stayturgid.obtainium.obtainium_app:
    apps:
      - id: org.autojs.autojs6
        url: https://github.com/djbclark/AutoJs6
        name: AutoJs6
        author: djbclark
        categories: [Automation]
        settings:
          apkFilterRegEx: arm64-v8a
          autoApkFilterByArch: true
          about: stayturgid fleet-profile AutoJs6
"""

RETURN = r"""
catalog_path:
  description: Rendered catalog location.
  type: str
  returned: always
installed:
  description: Package -> bool map (only packages listed in I(apps)).
  type: dict
  returned: when check_installed ran successfully
import_launched:
  description: Whether the Obtainium import UI was launched.
  type: bool
  returned: always
"""

import json
import os

from ansible.module_utils.basic import AnsibleModule

OBTAINIUM_PKG = "dev.imranr.obtainium"

# Obtainium's full additionalSettings schema with our GitHub-source baseline.
BASELINE_SETTINGS = {
    "includePrereleases": False,
    "fallbackToOlderReleases": True,
    "filterReleaseTitlesByRegEx": "",
    "filterReleaseNotesByRegEx": "",
    "verifyLatestTag": False,
    "sortMethodChoice": "date",
    "useLatestAssetDateAsReleaseDate": False,
    "releaseTitleAsVersion": False,
    "github-creds": "",
    "GHReqPrefix": "",
    "trackOnly": False,
    "versionExtractionRegEx": "",
    "matchGroupToUse": "",
    "versionDetection": True,
    "releaseDateAsVersion": False,
    "useVersionCodeAsOSVersion": False,
    "apkFilterRegEx": "",
    "invertAPKFilter": False,
    "autoApkFilterByArch": True,
    "appName": "",
    "appAuthor": "",
    "shizukuPretendToBeGooglePlay": False,
    "allowInsecure": False,
    "exemptFromBackgroundUpdates": False,
    "skipUpdateNotifications": False,
    "about": "",
    "refreshBeforeDownload": False,
    "includeZips": False,
    "zippedApkFilterRegEx": "",
}


def render_entry(module, spec):
    for key in ("id", "url"):
        if not spec.get(key):
            module.fail_json(msg="app spec missing required key '%s': %r" % (key, spec))
    settings = dict(BASELINE_SETTINGS)
    settings.update(spec.get("settings") or {})
    return {
        "id": spec["id"],
        "url": spec["url"],
        "author": spec.get("author", ""),
        "name": spec.get("name", spec["id"]),
        "preferredApkIndex": 0,
        "additionalSettings": json.dumps(settings, separators=(",", ":")),
        "categories": spec.get("categories") or [],
        "allowIdChange": False,
        "overrideSource": "GitHub",
    }


def normalize(catalog):
    """Comparable form: additionalSettings strings parsed into dicts."""
    norm = json.loads(json.dumps(catalog))  # deep copy
    for app in norm.get("apps", []):
        raw = app.get("additionalSettings")
        if isinstance(raw, str):
            try:
                app["additionalSettings"] = json.loads(raw)
            except ValueError:
                pass
    return norm


def read_existing(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def check_installed(module, package_ids):
    rc, _out, _err = module.run_command(["adb", "connect", "localhost:5555"])
    if rc != 0:
        return None
    rc, out, _err = module.run_command(
        ["adb", "-s", "localhost:5555", "shell", "pm", "list", "packages"]
    )
    if rc != 0:
        return None
    present = {
        line.split(":", 1)[1].strip()
        for line in out.replace("\r", "").splitlines()
        if line.startswith("package:")
    }
    return {pkg: (pkg in present) for pkg in package_ids}


def main():
    module = AnsibleModule(
        argument_spec=dict(
            apps=dict(type="list", elements="dict", required=True),
            catalog_path=dict(
                type="str", default="/sdcard/Download/stayturgid-obtainium-apps.json"
            ),
            extra_settings=dict(type="dict", default={"groupByCategory": True}),
            import_ui=dict(type="bool", default=False),
            check_installed=dict(type="bool", default=True),
        ),
        supports_check_mode=True,
    )

    path = module.params["catalog_path"]
    catalog = {
        "apps": [render_entry(module, s) for s in module.params["apps"]],
        "settings": module.params["extra_settings"],
    }

    existing = read_existing(path)
    changed = normalize(existing or {}) != normalize(catalog)

    result = {"changed": changed, "catalog_path": path, "import_launched": False}

    if module.params["check_installed"]:
        installed = check_installed(
            module, [s["id"] for s in module.params["apps"]]
        )
        if installed is not None:
            result["installed"] = installed
            missing = sorted(p for p, ok in installed.items() if not ok)
            if missing:
                module.warn(
                    "obtainium catalog apps not installed on device: %s "
                    "(import the catalog in Obtainium)" % ", ".join(missing)
                )

    if changed and not module.check_mode:
        # self-heal: the stayturgid import dir may not exist (or was deleted)
        parent = os.path.dirname(path)
        if parent:
            try:
                os.makedirs(parent, exist_ok=True)
            except OSError:
                pass
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(catalog, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)

        if module.params["import_ui"]:
            rc, _out, _err = module.run_command(
                [
                    "am", "start",
                    "-a", "android.intent.action.VIEW",
                    "-d", "file://" + path,
                    "-t", "application/json",
                    "-n", OBTAINIUM_PKG + "/.MainActivity",
                ]
            )
            result["import_launched"] = rc == 0

    module.exit_json(**result)


if __name__ == "__main__":
    main()
