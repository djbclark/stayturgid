#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: android_apk
short_description: Install an APK on a device via adb with failure parsing
description:
  - Installs an APK from a local path, a URL, or a GitHub release
    (C(gh release download)) with C(adb install -r).
  - Parses C(INSTALL_FAILED_*) / C(Failure) output — adb can exit 0 while the
    install actually failed.
  - Idempotent by package presence; set C(force=true) to reinstall, or
    C(version_name) to upgrade only when the installed version differs.
options:
  device:
    description: ADB device serial or C(host:5555) target.
    type: str
    required: true
  package:
    description: Package id used for the idempotence check.
    type: str
    required: true
  apk_path:
    description: Local APK file to install.
    type: path
  url:
    description: Download URL for the APK (fetched to a temp file).
    type: str
  gh_repo:
    description: GitHub C(owner/repo) to download a release asset from (needs C(gh) CLI).
    type: str
  gh_pattern:
    description: Asset glob for C(gh release download --pattern).
    type: str
  gh_tag:
    description: Release tag (default latest).
    type: str
  gh_latest:
    description:
      - Resolve the newest release of I(gh_repo) (prereleases such as a
        C(nightly) tag included) on every run and install its I(gh_pattern) asset.
      - The APK is verified against the SHA-256 digest GitHub publishes for that
        asset (C(assets[].digest)); an asset without a digest is installed
        unverified. Idempotent by comparing the digest with the installed
        C(base.apk). When GitHub cannot be reached the release last
        resolved (kept under C(~/.cache/stayturgid/apks/gh-latest)) is reused if its APK is
        still cached, an installed app is left alone, and only a first install with nothing
        cached fails; each case warns. Mutually exclusive with I(gh_tag), I(checksum) and
        I(version_name).
    type: bool
    default: false
  gh_tag_prefix:
    description:
      - Only with I(gh_latest). Consider only releases whose whole tag is this prefix
        followed by a plain integer, for example C(agent-r) matches C(agent-r101) but not
        C(agent-rz), C(agent-r1x), C(agent-r999.1), C(agent-ci-0.9.19) or C(agent-v0.9.19), and
        take the one with the highest number (not the first listed). Without it the newest release of
        any tag is used.
      - Also part of the key of the remembered release, so two entries of one repository
        with different prefixes never share a memory.
      - Fails when no release carries the prefix. Ignored unless I(gh_latest) is true.
    type: str
  gh_skip_prereleases:
    description:
      - Only with I(gh_latest). Skip releases GitHub marks as prereleases, so a beta tag
        published after the stable one is not installed.
      - Leave it off for an upstream whose only release channel is a republished
        prerelease (C(nightly)).
    type: bool
    default: false
  gh_latest_pin_to_cache:
    description:
      - Only with I(gh_latest). Skip GitHub entirely and install the release last
        resolved for I(gh_repo) and I(gh_pattern) (the one the rest of the fleet runs),
        read from C(~/.cache/stayturgid/apks/gh-latest) and its APK from the sha256
        cache. The cached APK is verified against the remembered digest.
      - Fails, never falling back to the newest release, when no release was remembered or
        its cached APK is missing or does not match.
      - Ignored unless I(gh_latest) is true.
    type: bool
    default: false
  version_name:
    description: Expected versionName; install only when the device differs.
    type: str
  checksum:
    description:
      - Expected SHA-256 digest of the APK before any optional resigning.
      - Accepts either the bare hexadecimal digest or C(sha256:<digest>).
    type: str
  force:
    description: Install even when the package is already present.
    type: bool
    default: false
  clean:
    description:
      - Uninstall the package before installing (only when an install is
        actually happening; the already-installed idempotency check still
        short-circuits first).
      - Forces the installer to re-extract native libs. Needed on Fire OS 8,
        which does not re-extract libs on an in-place C(adb install -r)
        upgrade, leaving native-lib-dependent components (e.g. shizuku_server
        loading librish.so) broken until a fresh install.
    type: bool
    default: false
  clean_on_incompatible:
    description:
      - If an in-place upgrade fails with an Android package or signature
        incompatibility, uninstall the stale package and retry once.
      - Never for a version downgrade (the device holds a newer build than the
        pin); that fails the install instead of losing the app's data.
      - This makes an immutable version lock convergent from packages installed
        through a different signing lineage. The fallback removes application
        data and runs only after the ordinary preserving upgrade has failed.
    type: bool
    default: true
  installer:
    description: Installer package to spoof (C(adb install -i), e.g. com.android.vending).
    type: str
  extra_args:
    description: Extra C(adb install) arguments.
    type: list
    elements: str
    default: []
  connect:
    description: Run C(adb connect) before other operations (for wireless targets).
    type: bool
    default: true
  resign:
    description:
      - Resign the downloaded APK with a debug keystore before installing.
      - Required for unsigned fork builds (operator/Obtainium, operator/Shizuku, etc.).
    type: bool
    default: false
  apksigner_bin:
    description:
      - Path to C(apksigner) (Android SDK build-tools). Used by I(resign=true) and I(signer_sha256);
        C(aapt2) is taken from the same directory.
    type: path
  signer_sha256:
    description:
      - Hex SHA-256 of the one signing certificate the downloaded APK must carry, checked with
        C(apksigner verify --print-certs) before anything is installed or uninstalled. The package
        name in the APK (C(aapt2 dump badging)) must also equal I(package).
      - Pins the signer, not the version, so a C(gh_latest) release can roll while a release written by
        anyone without the key is refused. Fails closed when apksigner or aapt2 is missing.
      - Checked on a fresh install too, where Android has no earlier signer to compare with.
    type: str
  keystore:
    description: Debug keystore path. Ignored unless I(resign=true).
    type: path
  keystore_pass:
    description: Keystore password. Ignored unless I(resign=true).
    type: str
    default: android
  key_alias:
    description: Key alias in the keystore. Ignored unless I(resign=true).
    type: str
    default: androiddebugkey
  install_timeout:
    description: >-
      Seconds before C(adb install) is killed. Without this, a stuck install
      (e.g. an on-device confirmation dialog nobody is present to tap) hangs
      forever — this ansible-core's C(run_command) has no timeout of its own.
    type: int
    default: 180
  download_timeout:
    description: >-
      Seconds the one download may take. The deploy passes its own window
      (C(stayturgid_download_timeout_seconds), normally
      C(STAYTURGID_DEPLOY_TIMEOUT_SECONDS)). There is no second attempt and no
      fallback that deletes a partial and starts over. When the window expires,
      or the transfer fails, this module fails the deploy and names the file.
      A partial under C(~/.cache/stayturgid/apks/partials) is kept so the next
      deploy continues it.
    type: int
    default: 1800
  detached_install:
    description:
      - Install through a detached on-device script, for an APK that carries the
        adb transport itself (Tailscale over a C(host:5555) tailnet target).
        Replacing that app drops the adb connection mid-install, which a plain
        C(adb install -r) reports as a bare failure and which, with the Play
        Protect verifier switched off from the Mac, would leave it off.
      - The APK is pushed to C(/data/local/tmp/stayturgid-<package>.apk), then one
        C(adb shell) starts a C(nohup) script that disables the verifier settings,
        runs C(pm install -r --user), restores the verifier settings to their
        pre-install values, deletes the APK and writes the C(pm) output to
        C(/data/local/tmp/stayturgid-<package>.log). The module then reconnects
        and polls that log for up to I(detached_timeout) seconds.
      - Refused together with I(clean) and I(work_profile). The
        I(clean_on_incompatible) fallback is not run; it would need a second
        detached step, so an incompatible upgrade fails the install instead.
    type: bool
    default: false
  detached_timeout:
    description: >-
      Seconds to keep reconnecting and polling for the detached install's log
      before giving up. Ignored unless I(detached_install=true).
    type: int
    default: 300
"""

EXAMPLES = r"""
- name: Install a local APK
  stayturgid.android_common.android_apk:
    device: "{{ adb_target }}"
    package: com.example.app
    apk_path: /tmp/app.apk
  delegate_to: localhost

- name: Install latest Shizuku from a GitHub release
  stayturgid.android_common.android_apk:
    device: "{{ adb_target }}"
    package: moe.shizuku.privileged.api
    gh_repo: thedjchi/Shizuku
    gh_pattern: "*.apk"
  delegate_to: localhost

- name: Install fork build with resign
  stayturgid.android_common.android_apk:
    device: "{{ adb_target }}"
    package: moe.shizuku.privileged.api
    gh_repo: operator/Shizuku
    gh_pattern: "*universal*"
    resign: true
  delegate_to: localhost
"""

RETURN = r"""
changed:
  description: True when an install ran.
  type: bool
reason:
  description: Install outcome or skip reason.
  type: str
"""

import fcntl
import fnmatch
import hashlib
import json
import os
import re
import shlex
import shutil
import sys
import tempfile
import time

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.urls import fetch_url

from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_shell import (
    adb_connect,
    adb_shell,
    normalize_adb_output,
    package_installed,
)
from ansible_collections.stayturgid.android_common.plugins.module_utils.apk_install import (
    parse_install_result,
)

# Google Play Protect intercepts adb installs with an on-device "unsafe app
# blocked" dialog that nobody is there to tap (observed live 2026-10-03 on
# s24 installing com.termux.tasker: the install hung until timeout). These
# two global settings gate that scan for adb installs; both default to 1.
ADB_INSTALL_VERIFIER_KEYS = ("verifier_verify_adb_installs", "package_verifier_enable")


def read_verifier_settings(run_command, device):
    """Read the Play Protect adb-install verifier settings, keyed by name.

    An unset setting reads back as the literal string "null"; keep it so the
    restore can distinguish "was unset" from "was 0"/"was 1".
    """

    values = {}
    for key in ADB_INSTALL_VERIFIER_KEYS:
        rc, out, _err = adb_shell(run_command, device, "settings get global %s" % key)
        values[key] = out.strip() if rc == 0 else "null"
    return values


def write_verifier_settings(run_command, device, values):
    for key, value in values.items():
        if value == "null":
            adb_shell(run_command, device, "settings delete global %s" % key)
        else:
            adb_shell(run_command, device, "settings put global %s %s" % (key, value))


DETACHED_PACKAGE_RE = re.compile(r"^[A-Za-z0-9_.]+$")
DETACHED_DONE_RE = re.compile(r"^stayturgid-pm-rc=(\d+)\s*$", re.M)
DETACHED_POLL_SECONDS = 5
DETACHED_PROBE_TIMEOUT = 15
DETACHED_VERSION_ATTEMPTS = 3


def _now():
    return time.monotonic()


def _sleep(seconds):
    time.sleep(seconds)


def detached_script(package, user, installer, extra_args, verifier_before):
    """The on-device script for a detached install, as one sh command line.

    Order matters: the verifier restore and the APK removal run before the log
    appears, so a log on the device means the device state is final. The log is
    written aside and moved into place, so a reader never sees a partial one.
    """

    apk = "/data/local/tmp/stayturgid-%s.apk" % package
    log = "/data/local/tmp/stayturgid-%s.log" % package
    install = ["pm", "install", "-r", "--user", user]
    if installer:
        install += ["-i", installer]
    install += list(extra_args) + [apk]
    steps = ["settings put global %s 0" % key for key in ADB_INSTALL_VERIFIER_KEYS]
    steps.append("%s > %s.part 2>&1; rc=$?" % (" ".join(shlex.quote(a) for a in install), shlex.quote(log)))
    for key, value in verifier_before.items():
        if value == "null":
            steps.append("settings delete global %s" % key)
        else:
            steps.append("settings put global %s %s" % (key, shlex.quote(value)))
    steps.append("rm -f %s" % shlex.quote(apk))
    steps.append('echo "stayturgid-pm-rc=$rc" >> %s.part' % shlex.quote(log))
    steps.append("mv -f %s.part %s" % (shlex.quote(log), shlex.quote(log)))
    # setsid, where the device has it, moves the script out of adbd's process
    # group so a dropped connection cannot signal it; nohup covers SIGHUP.
    return "nohup $(command -v setsid) sh -c %s </dev/null >/dev/null 2>&1 &" % shlex.quote("; ".join(steps))


def install_detached(module, device, package, apk, user, install_timeout):
    """Install apk through a detached on-device script; returns the reason string."""

    if not DETACHED_PACKAGE_RE.match(package):
        module.fail_json(msg="detached_install: package %r is not a plain package id" % package)
    remote_apk = "/data/local/tmp/stayturgid-%s.apk" % package
    remote_log = "/data/local/tmp/stayturgid-%s.log" % package
    run_command = module.run_command
    timeout = module.params["detached_timeout"]

    rc, _out, err = adb_shell(run_command, device, "rm -f %s %s.part" % (remote_log, remote_log))
    if rc != 0:
        module.fail_json(msg="detached install: could not clear the old log on %s: %s" % (device, err.strip()))

    verifier_before = read_verifier_settings(run_command, device)
    sys.stderr.write("🚨📱🚨 USING — %s — detached install %s — ~%d min\n" % (device, package, max(timeout // 60, 1)))
    rc, out, err = run_command_with_timeout(
        run_command,
        ["adb", "-s", device, "push", apk, remote_apk],
        timeout=install_timeout,
        get_bin_path_fn=module.get_bin_path,
    )
    if rc != 0:
        sys.stderr.write("🟢📱🟢 FREE — %s — detached install aborted\n" % device)
        module.fail_json(msg="detached install: adb push failed (rc=%d): %s" % (rc, normalize_adb_output(out + err)))

    script = detached_script(package, user, module.params["installer"], module.params["extra_args"], verifier_before)
    # The connection may drop the moment the script's pm install replaces the
    # app, so a non-zero rc here is not proof that the script never started.
    start_rc, _out, start_err = adb_shell(run_command, device, script)
    if start_rc != 0:
        module.warn(
            "detached install: starting the script returned rc=%d (%s); polling anyway" % (start_rc, start_err.strip())
        )

    deadline = _now() + timeout
    log = None
    while True:
        if ":" in device:
            adb_connect(run_command, device, timeout=DETACHED_PROBE_TIMEOUT)
        rc, out, _err = adb_shell(run_command, device, "cat %s" % remote_log, timeout=DETACHED_PROBE_TIMEOUT)
        if rc == 0 and DETACHED_DONE_RE.search(normalize_adb_output(out)):
            log = normalize_adb_output(out)
            break
        if _now() >= deadline:
            break
        _sleep(DETACHED_POLL_SECONDS)
    sys.stderr.write("🟢📱🟢 FREE — %s — detached install finished\n" % device)

    if log is None:
        module.fail_json(
            msg="detached install: device did not come back within %d s; the install may still have completed: "
            "check versionName (script start rc=%d)" % (timeout, start_rc)
        )

    pm_rc = int(DETACHED_DONE_RE.search(log).group(1))
    ok, reason = parse_install_result(DETACHED_DONE_RE.sub("", log))
    adb_shell(run_command, device, "rm -f %s" % remote_log)
    if pm_rc != 0 or not ok:
        fail_install(module, package, reason)

    after = read_verifier_settings(run_command, device)
    if after != verifier_before:
        module.warn(
            "detached install: verifier settings %s differ from before (%s); restoring" % (after, verifier_before)
        )
        write_verifier_settings(run_command, device, verifier_before)

    expected = module.params["version_name"]
    if expected:
        current = None
        for attempt in range(DETACHED_VERSION_ATTEMPTS):
            current = installed_version(run_command, device, package)
            if current is not None:
                break
            _sleep(DETACHED_POLL_SECONDS)
        if current != expected:
            module.fail_json(
                msg="detached install reported Success but %s is at versionName %r, not %r"
                % (package, current, expected)
            )
    return reason


def fail_install(module, package, reason):
    if "INSTALL_FAILED_VERSION_DOWNGRADE" in reason:
        module.fail_json(
            msg="adb install failed: %s: the device has a newer %s than the configured APK; "
            "not uninstalling it (that would lose its data). Update the pin, or downgrade by hand." % (reason, package)
        )
    module.fail_json(msg="adb install failed: %s" % reason)


def installed_sha256(run_command, device, package):
    """SHA-256 of the package's installed base.apk, or None when unreadable."""
    rc, out, _err = adb_shell(run_command, device, "pm path %s" % package)
    if rc != 0:
        return None
    paths = [
        line.strip()[len("package:") :]
        for line in normalize_adb_output(out).splitlines()
        if line.strip().startswith("package:")
    ]
    base = [path for path in paths if path.endswith("/base.apk")]
    if len(base) != 1:
        return None
    rc, out, _err = adb_shell(run_command, device, "sha256sum %s" % shlex.quote(base[0]))
    if rc != 0:
        return None
    fields = normalize_adb_output(out).split()
    if fields and re.match(r"^[0-9a-f]{64}$", fields[0]):
        return fields[0]
    return None


def _gh_memory_path(repo, pattern, tag_prefix=None, skip_prereleases=False):
    """Memory file of one gh_latest entry. The keys of entries without a filter are unchanged."""
    key = "%s\0%s" % (repo, pattern or "")
    if tag_prefix:
        key += "\0prefix=%s" % tag_prefix
    if skip_prereleases:
        key += "\0stable"
    token = hashlib.sha256(key.encode()).hexdigest()[:16]
    return os.path.join(APK_CACHE_DIR, "gh-latest", token + ".json")


def _remember_gh_release(repo, pattern, tag, digest, tag_prefix=None, skip_prereleases=False):
    """Record the newest release a lookup resolved, so an outage can reuse the cached APK."""
    path = _gh_memory_path(repo, pattern, tag_prefix, skip_prereleases)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".part", "w") as handle:
            json.dump({"tag": tag, "sha256": digest}, handle)
        os.rename(path + ".part", path)
    except OSError:
        pass  # a missing memory only removes the outage fallback


def _read_gh_memory(repo, pattern, tag_prefix=None, skip_prereleases=False):
    """(tag, sha256) recorded for repo/pattern, or None when there is no usable record."""
    try:
        with open(_gh_memory_path(repo, pattern, tag_prefix, skip_prereleases)) as handle:
            seen = json.load(handle)
        tag, digest = seen["tag"], seen["sha256"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not (tag and re.match(r"^[0-9a-f]{64}$", str(digest))):
        return None
    return tag, digest


def _cached_apk_ok(digest):
    cached = os.path.join(APK_CACHE_DIR, digest + ".apk")
    return os.path.isfile(cached) and _sha256_of(cached) == digest


def _recall_gh_release(repo, pattern, tag_prefix=None, skip_prereleases=False):
    """(tag, sha256) last resolved for repo/pattern, when its APK is still in the cache, else None."""
    seen = _read_gh_memory(repo, pattern, tag_prefix, skip_prereleases)
    if seen and _cached_apk_ok(seen[1]):
        return seen
    return None


def _pinned_gh_release(module, repo, pattern, tag_prefix=None, skip_prereleases=False):
    """The remembered fleet release of repo/pattern without asking GitHub; fails rather than guess."""
    memory = _gh_memory_path(repo, pattern, tag_prefix, skip_prereleases)
    seen = _read_gh_memory(repo, pattern, tag_prefix, skip_prereleases)
    if not seen:
        module.fail_json(
            msg="gh_latest_pin_to_cache: no release remembered for %s %r (%s); run once without pinning "
            "on a host that can reach GitHub" % (repo, pattern, memory)
        )
    tag, digest = seen
    if not _cached_apk_ok(digest):
        module.fail_json(
            msg="gh_latest_pin_to_cache: the fleet release %s of %s %r is remembered in %s but its APK %s "
            "is missing or does not match sha256:%s"
            % (tag, repo, pattern, memory, os.path.join(APK_CACHE_DIR, digest + ".apk"), digest)
        )
    module.warn("pinned to the cached fleet release %s of %s; GitHub was not consulted" % (tag, repo))
    return tag, digest


def _tag_version(tag, tag_prefix):
    """Number of a tag that is exactly tag_prefix + a plain integer (ASCII digits, no dots), else None."""
    if not re.fullmatch(re.escape(tag_prefix) + r"[0-9]+", tag, re.ASCII):
        return None
    return int(tag[len(tag_prefix) :])


def select_gh_release(releases, tag_prefix=None, skip_prereleases=False):
    """The newest published release that passes the filters, from a newest-first release list, or None.

    With tag_prefix "newest" is the highest version number in the tag, not the first the API lists, so
    a release re-created on an old tag (listed first because it is recent) never beats the real newest.
    """
    best, best_version = None, None
    for release in releases:
        if release.get("draft"):
            continue
        if skip_prereleases and release.get("prerelease"):
            continue
        if not tag_prefix:
            return release
        version = _tag_version(str(release.get("tag_name") or ""), tag_prefix)
        if version is not None and (best_version is None or version > best_version):
            best, best_version = release, version
    return best


def gh_newest_release(
    module, repo, pattern, installed=False, pin_to_cache=False, tag_prefix=None, skip_prereleases=False
):
    """(tag, sha256 hex or None) of the pattern asset in repo's newest release.

    GitHub lists releases newest first (prereleases included, so a republished
    C(nightly) tag counts, unless skip_prereleases is set). With tag_prefix only releases whose tag
    starts with it are considered. The digest is the one GitHub computed for the asset
    (C(sha256:<hex>)); older assets have none.

    When GitHub cannot be reached (DNS, outage, rate limit) the release last resolved for
    this repo and pattern is reused if its APK is still in the checksum cache; failing that,
    an app that is already installed is left alone. Both paths warn; only a first install
    with nothing cached fails (a flapping resolver cost three m11 deploys on 2026-11-20).

    With pin_to_cache GitHub is not asked at all: the remembered release is used or the call fails.
    """
    if pin_to_cache:
        return _pinned_gh_release(module, repo, pattern, tag_prefix, skip_prereleases)
    gh = module.get_bin_path("gh", required=True)
    # A filter can skip past the newest releases, so look at more of them.
    per_page = 100 if (tag_prefix or skip_prereleases) else 10
    rc, out, err = run_command_with_timeout(
        module.run_command,
        [gh, "api", "repos/%s/releases?per_page=%d" % (repo, per_page)],
        timeout=60,
        get_bin_path_fn=module.get_bin_path,
    )
    if rc != 0:
        reason = (err or out).strip()[:500]
        recalled = _recall_gh_release(repo, pattern, tag_prefix, skip_prereleases)
        if recalled:
            module.warn("could not list releases of %s (%s); using cached %s" % (repo, reason, recalled[0]))
            return recalled
        if installed:
            module.warn("could not list releases of %s (%s); leaving the installed build" % (repo, reason))
            module.exit_json(changed=False, reason="GitHub unreachable; installed build left as is")
        module.fail_json(msg="could not list releases of %s: %s" % (repo, reason))
    try:
        release = select_gh_release(json.loads(out), tag_prefix, skip_prereleases)
    except (ValueError, TypeError, AttributeError):
        module.fail_json(msg="unparseable release list for %s" % repo)
    if release is None:
        filters = []
        if tag_prefix:
            filters.append("tag prefix %r" % tag_prefix)
        if skip_prereleases:
            filters.append("no prereleases")
        module.fail_json(
            msg="%s has no published release%s" % (repo, " with " + " and ".join(filters) if filters else "")
        )
    tag = release.get("tag_name")
    matches = [a for a in release.get("assets") or [] if fnmatch.fnmatch(a.get("name", ""), pattern or "*.apk")]
    if not tag or len(matches) != 1:
        module.fail_json(
            msg="newest release %s of %s has %d assets matching %r, expected 1" % (tag, repo, len(matches), pattern)
        )
    digest = matches[0].get("digest") or ""
    if not digest:
        return tag, None
    wanted = _wanted_sha256(digest)
    if not digest.startswith("sha256:") or not re.match(r"^[0-9a-f]{64}$", wanted):
        module.fail_json(msg="unexpected digest %r on %s %s" % (digest, repo, tag))
    _remember_gh_release(repo, pattern, tag, wanted, tag_prefix, skip_prereleases)
    return tag, wanted


def installed_version(run_command, device, package):
    rc, out, _err = adb_shell(run_command, device, "dumpsys package %s | grep versionName" % package)
    if rc != 0:
        return None
    text = normalize_adb_output(out)
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("versionName="):
            return line.split("=", 1)[1]
    return None


def download_url(module, url):
    resp, info = fetch_url(module, url)
    if info.get("status") != 200 or resp is None:
        module.fail_json(msg="download failed (%s): %s" % (info.get("status"), url))
    tmp = tempfile.NamedTemporaryFile("wb", dir=module.tmpdir, suffix=".apk", delete=False)
    tmp.write(resp.read())
    tmp.close()
    return tmp.name


try:
    from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_timeout import (
        DEFAULT_SLOW_TIMEOUT,
        run_command_with_timeout,
    )
except ImportError:
    import os
    import sys

    _mod_utils = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "module_utils")
    if _mod_utils not in sys.path:
        sys.path.insert(0, _mod_utils)
    # Same names as the collection import above (non-collection load path); mypy
    # would flag the rebinding as no-redef.
    from adb_timeout import (  # type: ignore[no-redef]
        DEFAULT_SLOW_TIMEOUT,
        run_command_with_timeout,
    )


# One aria2c transfer for the whole download window. A slow link used to be
# abandoned: --lowest-speed-limit=20K closed connections, --quiet hid why, and
# a failure deleted the partial and started up to three single-stream
# `gh release download` attempts. On 2026-10-22 an 8-way fetch stalled while a
# 4-way fetch of the same GitHub CDN assets completed, so the split stays at 4.
# --timeout here is aria2c's connect timeout, not the deploy window.
ARIA2C_ARGS = [
    "--continue=true",
    "--auto-file-renaming=false",
    "--max-connection-per-server=4",
    "--split=4",
    "--min-split-size=4M",
    "--max-tries=10",
    "--retry-wait=5",
    "--timeout=60",
    "--file-allocation=none",
    "--console-log-level=warn",
    "--summary-interval=0",
]


def gh_asset(module, gh, repo, tag, pattern):
    """(name, url) of the one release asset matching pattern, or None."""
    rc, out, _err = run_command_with_timeout(
        module.run_command,
        [gh, "release", "view", tag, "--repo", repo, "--json", "assets"],
        timeout=60,
        get_bin_path_fn=module.get_bin_path,
    )
    if rc != 0:
        return None
    try:
        assets = json.loads(out)["assets"]
    except (ValueError, KeyError, TypeError):
        return None
    matches = [a for a in assets if fnmatch.fnmatch(a.get("name", ""), pattern or "*.apk")]
    if len(matches) != 1 or not matches[0].get("url"):
        return None
    return matches[0]["name"], matches[0]["url"]


def _apk_partial_dir(module, repo, tag, pattern):
    """Stable directory for one release asset, so a later deploy can resume it.

    The key matches control/bin/prefetch_pins.py. A gh_latest download also keys
    on the published digest: the republished C(nightly) tag must not continue
    the previous build's file.
    """
    if module.params.get("gh_latest") and module.params.get("checksum"):
        pattern = "%s@%s" % (pattern or "", module.params["checksum"])
    token = hashlib.sha256(("%s\0%s\0%s" % (repo, tag or "", pattern or "")).encode()).hexdigest()[:16]
    path = os.path.join(APK_CACHE_DIR, "partials", token)
    if not os.path.isdir(path):
        os.makedirs(path)
    return path


def _download_failure(module, name, window, dest, rc, out, err):
    detail = (err or out or "").strip()
    if rc == 124:
        module.fail_json(
            msg=(
                "download of %s did not finish within %ds. The transfer was stopped. "
                "The partial file was kept at %s and the next deploy continues it. %s"
                % (name, window, dest, detail[:500])
            )
        )
    module.fail_json(
        msg=(
            "download of %s failed. The partial file was kept at %s and the next deploy continues it. %s"
            % (name, dest, (detail or "exit %s" % rc)[:500])
        )
    )


def _fetch_helper(module):
    """Path of the shared fetcher when a deploy asked for it, else None."""
    root = os.environ.get("STAYTURGID_REPO_ROOT", "").strip()
    host = os.environ.get("STAYTURGID_FETCH_SSH_HOST", "").strip()
    if not root or not host:
        return None
    helper = os.path.join(root, "control", "bin", "fetch_asset.py")
    if not os.path.isfile(helper):
        return None
    return helper


def download_gh_release(module, repo, pattern, tag):
    """Download one release asset. Never discards a partial to start another tool."""
    gh = module.get_bin_path("gh", required=True)
    window = int(module.params["download_timeout"])
    aria2c = module.get_bin_path("aria2c")
    asset = gh_asset(module, gh, repo, tag, pattern) if aria2c and tag else None
    if aria2c and asset:
        name, url = asset
        destdir = _apk_partial_dir(module, repo, tag, pattern)
        dest = os.path.join(destdir, name)
        helper = _fetch_helper(module)
        if helper:
            # The helper owns the one transfer (fast host, else aria2). Its failure
            # is the deploy failure: do not start gh or a second aria2 on the same file.
            python = module.get_bin_path("python3") or "python3"
            rc, out, err = run_command_with_timeout(
                module.run_command,
                [python, helper, "--url", url, "--dest", dest, "--timeout", str(window)],
                timeout=window,
                get_bin_path_fn=module.get_bin_path,
                what="download",
            )
            if rc == 0 and os.path.isfile(dest) and not os.path.exists(dest + ".aria2"):
                return dest
            _download_failure(module, name, window, dest, rc, out, err)
        rc, out, err = run_command_with_timeout(
            module.run_command,
            [aria2c] + ARIA2C_ARGS + ["--dir", destdir, "--out", name, url],
            timeout=window,
            get_bin_path_fn=module.get_bin_path,
            what="download",
        )
        complete = rc == 0 and os.path.isfile(dest) and not os.path.exists(dest + ".aria2")
        if complete:
            return dest
        _download_failure(module, name, window, dest, rc, out, err)
    destdir = tempfile.mkdtemp(dir=module.tmpdir)
    cmd = [gh, "release", "download"]
    if tag:
        cmd.append(tag)
    cmd += ["--repo", repo, "--pattern", pattern or "*.apk", "--dir", destdir]
    rc, out, err = run_command_with_timeout(
        module.run_command,
        cmd,
        timeout=window,
        get_bin_path_fn=module.get_bin_path,
        what="download",
    )
    apks = sorted(f for f in os.listdir(destdir) if f.lower().endswith(".apk")) if rc == 0 else []
    if rc == 0 and apks:
        return os.path.join(destdir, apks[0])
    label = pattern or repo
    _download_failure(module, label, window, destdir, rc, out, err)


def _wanted_sha256(expected):
    wanted = expected.strip()
    if wanted.startswith("sha256:"):
        wanted = wanted[len("sha256:") :]
    return wanted.lower()


def _sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


APK_CACHE_DIR = os.path.expanduser("~/.cache/stayturgid/apks")


def cached_download(module, fetch):
    """Return a private copy of the checksum-pinned APK, downloading it at most once.

    Every host in a play runs this task at once on the control node, so a 263 MB APK used to be
    downloaded four times in parallel and timed out (2026-10-18). The verified file is kept as
    <sha256>.apk; a lock makes the other hosts wait for the first download. Each caller gets its own
    copy because resign_apk rewrites the file in place. Without a checksum there is no safe key.
    """
    expected = module.params["checksum"]
    if not expected:
        return fetch()
    wanted = _wanted_sha256(expected)
    if not re.match(r"^[0-9a-f]{64}$", wanted):
        return fetch()
    if not os.path.isdir(APK_CACHE_DIR):
        os.makedirs(APK_CACHE_DIR)
    cached = os.path.join(APK_CACHE_DIR, wanted + ".apk")
    with open(cached + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not (os.path.isfile(cached) and _sha256_of(cached) == wanted):
            apk = fetch()
            verify_sha256(module, apk, expected)
            shutil.copyfile(apk, cached + ".part")
            os.rename(cached + ".part", cached)
    copy = os.path.join(tempfile.mkdtemp(dir=module.tmpdir), wanted + ".apk")
    shutil.copyfile(cached, copy)
    return copy


def verify_sha256(module, apk_path, expected):
    if not expected:
        return
    wanted = _wanted_sha256(expected)
    actual = _sha256_of(apk_path)
    if actual != wanted:
        module.fail_json(msg="APK checksum mismatch: expected sha256:%s, got sha256:%s" % (wanted, actual))


def verify_signer_and_package(module, apk_path, expected_version_code=None):
    """Refuse an APK whose signer is not signer_sha256 or whose package is not the one being installed."""
    wanted = (module.params.get("signer_sha256") or "").lower()
    if not wanted:
        return
    if not re.match(r"^[0-9a-f]{64}$", wanted):
        module.fail_json(msg="signer_sha256 must be a 64-character hex SHA-256")
    apksigner = module.params.get("apksigner_bin")
    if not apksigner:
        apksigner = os.path.join(
            os.path.expanduser("~"), "Library", "Android", "sdk", "build-tools", "36.0.0", "apksigner"
        )
    aapt2 = os.path.join(os.path.dirname(apksigner), "aapt2")
    for tool in (apksigner, aapt2):
        if not os.path.isfile(tool):
            module.fail_json(msg="signer_sha256 needs %s (set apksigner_bin to the SDK build-tools apksigner)" % tool)
    rc, out, err = module.run_command([apksigner, "verify", "--print-certs", apk_path])
    if rc != 0:
        module.fail_json(msg="apksigner verify failed for the downloaded APK: %s" % (err or out).strip()[:300])
    signers = set(re.findall(r"certificate SHA-256 digest: ([0-9a-fA-F]{64})", out))
    if {s.lower() for s in signers} != {wanted}:
        module.fail_json(
            msg="the downloaded APK is not signed by the pinned certificate sha256:%s (it carries %s); not installing"
            % (wanted, ", ".join(sorted(signers)) or "none")
        )
    rc, out, err = module.run_command([aapt2, "dump", "badging", apk_path])
    found = re.search(r"package: name='([^']+)'(?: versionCode='(\d+)')?", out) if rc == 0 else None
    if not found or found.group(1) != module.params["package"]:
        module.fail_json(
            msg="the downloaded APK is package %r, not %r; not installing"
            % (found.group(1) if found else "unreadable", module.params["package"])
        )
    if expected_version_code is not None and found.group(2) != str(expected_version_code):
        module.fail_json(
            msg="the downloaded APK has versionCode %s but its release tag says %s (an old build under a new tag?); "
            "not installing" % (found.group(2), expected_version_code)
        )


def resign_apk(module, apk_path):
    apksigner = module.params.get("apksigner_bin")
    if not apksigner:
        home = os.path.expanduser("~")
        apksigner = os.path.join(home, "Library", "Android", "sdk", "build-tools", "36.0.0", "apksigner")
    if not os.path.isfile(apksigner):
        module.fail_json(
            msg="apksigner not found at %s; set apksigner_bin or install Android SDK build-tools" % apksigner
        )

    keystore = module.params.get("keystore")
    if not keystore:
        home = os.path.expanduser("~")
        keystore = os.path.join(home, ".android", "debug.keystore")
    if not os.path.isfile(keystore):
        module.fail_json(msg="debug keystore not found at %s" % keystore)

    keystore_pass = module.params.get("keystore_pass", "android")
    key_alias = module.params.get("key_alias", "androiddebugkey")

    cmd = [
        apksigner,
        "sign",
        "--ks",
        keystore,
        "--ks-pass",
        "pass:" + keystore_pass,
        "--ks-key-alias",
        key_alias,
        apk_path,
    ]
    rc, _out, err = run_command_with_timeout(
        module.run_command,
        cmd,
        timeout=DEFAULT_SLOW_TIMEOUT,
        get_bin_path_fn=module.get_bin_path,
    )
    if rc != 0:
        module.fail_json(msg="apksigner sign failed: %s" % err.strip())


def incompatible_install_failure(reason):
    """Return whether a clean retry can resolve an installed-package conflict.

    A version downgrade is deliberately not one: the device holds a newer build
    than the pin, and uninstalling it would throw away app data to go backwards.
    On 2026-10-06 that wiped Shizuku's ADB key and every grant on t2e (it ran a
    newer test build than a stale pin); the install now fails instead.
    """

    return any(
        marker in reason
        for marker in (
            "INSTALL_FAILED_DUPLICATE_PACKAGE",
            "INSTALL_FAILED_SHARED_USER_INCOMPATIBLE",
            "INSTALL_FAILED_UPDATE_INCOMPATIBLE",
        )
    )


def main():
    module = AnsibleModule(
        argument_spec=dict(
            device=dict(type="str", required=True),
            package=dict(type="str", required=True),
            apk_path=dict(type="path"),
            url=dict(type="str"),
            gh_repo=dict(type="str"),
            gh_pattern=dict(type="str"),
            gh_tag=dict(type="str"),
            gh_latest=dict(type="bool", default=False),
            gh_tag_prefix=dict(type="str"),
            gh_skip_prereleases=dict(type="bool", default=False),
            gh_latest_pin_to_cache=dict(type="bool", default=False),
            version_name=dict(type="str"),
            checksum=dict(type="str"),
            force=dict(type="bool", default=False),
            clean=dict(type="bool", default=False),
            clean_on_incompatible=dict(type="bool", default=True),
            installer=dict(type="str"),
            extra_args=dict(type="list", elements="str", default=[]),
            install_user=dict(type="str", default="0"),
            work_profile=dict(type="bool", default=False),
            work_profile_user=dict(type="str", default="10"),
            connect=dict(type="bool", default=True),
            resign=dict(type="bool", default=False),
            apksigner_bin=dict(type="path"),
            signer_sha256=dict(type="str"),
            keystore=dict(type="path"),
            keystore_pass=dict(type="str", default="android", no_log=True),
            key_alias=dict(type="str", default="androiddebugkey"),
            install_timeout=dict(type="int", default=180),
            download_timeout=dict(type="int", default=1800),
            detached_install=dict(type="bool", default=False),
            detached_timeout=dict(type="int", default=300),
        ),
        required_one_of=[["apk_path", "url", "gh_repo"]],
        mutually_exclusive=[
            ["apk_path", "url", "gh_repo"],
            ["gh_latest", "gh_tag"],
            ["gh_latest", "checksum"],
            ["gh_latest", "version_name"],
            ["gh_tag_prefix", "gh_tag"],
        ],
        required_if=[["gh_latest", True, ["gh_repo"]]],
        supports_check_mode=True,
    )

    device = module.params["device"]
    package = module.params["package"]

    if not module.params["gh_latest"]:
        for option in ("gh_tag_prefix", "gh_skip_prereleases"):
            if module.params[option]:
                module.fail_json(msg="%s needs gh_latest" % option)

    if module.params["detached_install"]:
        for option in ("clean", "work_profile"):
            if module.params[option]:
                module.fail_json(msg="detached_install cannot be combined with %s" % option)

    if module.params["connect"] and not module.check_mode:
        adb_connect(module.run_command, device)

    present = package_installed(module.run_command, device, package)
    latest_tag = None
    if module.params["gh_latest"]:
        latest_tag, digest = gh_newest_release(
            module,
            module.params["gh_repo"],
            module.params["gh_pattern"],
            installed=present,
            pin_to_cache=module.params["gh_latest_pin_to_cache"],
            tag_prefix=module.params["gh_tag_prefix"],
            skip_prereleases=module.params["gh_skip_prereleases"],
        )
        module.params["gh_tag"] = latest_tag
        module.params["checksum"] = digest
    if present and not module.params["force"]:
        if latest_tag:
            # Without a published digest the comparison waits for the download.
            if digest and installed_sha256(module.run_command, device, package) == digest:
                module.exit_json(changed=False, reason="newest release %s already installed" % latest_tag)
        elif module.params["version_name"]:
            current = installed_version(module.run_command, device, package)
            if current == module.params["version_name"]:
                module.exit_json(changed=False, reason="version %s already installed" % current)
        else:
            module.exit_json(changed=False, reason="already installed")

    if module.check_mode:
        module.exit_json(changed=True, reason="would install")

    if module.params["apk_path"]:
        apk = module.params["apk_path"]
        if not os.path.isfile(apk):
            module.fail_json(msg="apk_path not found: %s" % apk)
    elif module.params["url"]:
        apk = cached_download(module, lambda: download_url(module, module.params["url"]))
    else:
        apk = cached_download(
            module,
            lambda: download_gh_release(
                module,
                module.params["gh_repo"],
                module.params["gh_pattern"],
                module.params["gh_tag"],
            ),
        )

    verify_sha256(module, apk, module.params["checksum"])
    # A release tag that is the prefix plus a plain number (agent-r101) names the build's versionCode.
    tag_code = None
    prefix = module.params["gh_tag_prefix"]
    if latest_tag and prefix:
        tag_code = _tag_version(str(latest_tag), prefix)  # the tag is prefix + integer, or it was not selected
    verify_signer_and_package(module, apk, tag_code)

    if latest_tag and not digest:
        module.warn(
            "%s release %s publishes no digest for its asset; installing unverified"
            % (module.params["gh_repo"], latest_tag)
        )
        if (
            present
            and not module.params["force"]
            and installed_sha256(module.run_command, device, package) == _sha256_of(apk)
        ):
            module.exit_json(changed=False, reason="newest release %s already installed" % latest_tag)

    if module.params["resign"]:
        resign_apk(module, apk)

    user = module.params.get("install_user", "0")
    # This ansible-core's AnsibleModule.run_command() has no timeout param at
    # all, so `adb install` can hang indefinitely — confirmed live: a stuck
    # install (likely an on-device confirmation dialog nobody was there to
    # tap) blocked a deploy for 90+ minutes with no error. Wrap with the
    # coreutils timeout(1) binary via the shared run_command_with_timeout()
    # helper (same mechanism used fleet-wide for #59). Unlike other callers
    # of that helper, require the binary up front (required=True) rather than
    # silently degrading to unbounded — this call site is the one that
    # actually caused the incident, so a missing timeout(1) should fail loudly
    # here instead of quietly reintroducing the hang risk.
    module.get_bin_path("timeout", required=True)
    install_timeout = module.params["install_timeout"]

    if module.params["detached_install"]:
        reason = install_detached(module, device, package, apk, user, install_timeout)
        module.exit_json(changed=True, reason=reason)

    # Clean reinstall: uninstall before install so the installer re-extracts
    # native libs. Fire OS 8 does not re-extract libs on an in-place upgrade
    # (`adb install -r`), which leaves e.g. shizuku_server unable to load
    # librish.so from the extracted lib dir; a fresh install always extracts.
    # Only runs when we are actually installing (the already-installed
    # idempotency check above has already returned), so steady-state deploys
    # with an unchanged version never uninstall.
    if module.params["clean"] and present:
        sys.stderr.write("🚨📱🚨 USING — %s — clean uninstall before reinstall — ~3 min\n" % device)
        clean_uninstall_rc, clean_uninstall_out, clean_uninstall_err = run_command_with_timeout(
            module.run_command,
            ["adb", "-s", device, "uninstall", package],
            timeout=install_timeout,
            get_bin_path_fn=module.get_bin_path,
        )
        sys.stderr.write("🟢📱🟢 FREE — %s — clean uninstall complete\n" % device)
        if clean_uninstall_rc != 0 or "Success" not in normalize_adb_output(clean_uninstall_out):
            module.fail_json(
                msg="adb uninstall failed during clean reinstall: %s"
                % normalize_adb_output(clean_uninstall_out + "\n" + clean_uninstall_err)
            )

    cmd = ["adb", "-s", device, "install", "-r", "--user", user]
    if module.params["installer"]:
        cmd += ["-i", module.params["installer"]]
    cmd += module.params["extra_args"]
    cmd.append(apk)

    # Disable the Play Protect adb-install scan for the duration of the
    # install (it otherwise blocks sideloads with an on-device dialog), and
    # restore whatever was set before — including on failure. fail_json
    # raises SystemExit, so the finally block covers every exit path.
    verifier_before = read_verifier_settings(module.run_command, device)
    write_verifier_settings(module.run_command, device, {key: "0" for key in verifier_before})
    try:
        sys.stderr.write("🚨📱🚨 USING — %s — install %s — ~3 min\n" % (device, package))
        rc, out, err = run_command_with_timeout(
            module.run_command, cmd, timeout=install_timeout, get_bin_path_fn=module.get_bin_path
        )
        sys.stderr.write("🟢📱🟢 FREE — %s — install complete\n" % device)
        ok, reason = parse_install_result(out + "\n" + err)
        if (
            present
            and not module.params["clean"]
            and module.params["clean_on_incompatible"]
            and (rc != 0 or not ok)
            and incompatible_install_failure(reason)
        ):
            module.warn("clean fallback: uninstalling %s (application data will be lost) after %s" % (package, reason))
            sys.stderr.write("🚨📱🚨 USING — %s — clean fallback uninstall+reinstall — ~3 min\n" % device)
            uninstall_rc, uninstall_out, uninstall_err = run_command_with_timeout(
                module.run_command,
                ["adb", "-s", device, "uninstall", package],
                timeout=install_timeout,
                get_bin_path_fn=module.get_bin_path,
            )
            if uninstall_rc != 0 or "Success" not in normalize_adb_output(uninstall_out):
                sys.stderr.write("🟢📱🟢 FREE — %s — clean fallback uninstall+reinstall complete\n" % device)
                module.fail_json(
                    msg="adb install failed (%s); clean fallback uninstall failed: %s"
                    % (reason, normalize_adb_output(uninstall_out + "\n" + uninstall_err))
                )
            rc, out, err = run_command_with_timeout(
                module.run_command, cmd, timeout=install_timeout, get_bin_path_fn=module.get_bin_path
            )
            sys.stderr.write("🟢📱🟢 FREE — %s — clean fallback uninstall+reinstall complete\n" % device)
            ok, retry_reason = parse_install_result(out + "\n" + err)
            reason = "%s (clean fallback after %s)" % (retry_reason, reason)
    finally:
        write_verifier_settings(module.run_command, device, verifier_before)

    if rc == 124:
        module.fail_json(
            msg="adb install timed out after %ss (device may be showing an install confirmation dialog)"
            % install_timeout
        )
    if rc != 0 or not ok:
        fail_install(module, package, reason)

    if module.params["work_profile"]:
        wp_cmd = [
            "adb",
            "-s",
            device,
            "install",
            "-r",
            "--user",
            module.params["work_profile_user"],
            apk,
        ]
        sys.stderr.write("🚨📱🚨 USING — %s — work profile install %s — ~3 min\n" % (device, package))
        rc2, _out2, _err2 = run_command_with_timeout(
            module.run_command, wp_cmd, timeout=install_timeout, get_bin_path_fn=module.get_bin_path
        )
        sys.stderr.write("🟢📱🟢 FREE — %s — work profile install complete\n" % device)
        if rc2 == 0:
            reason += " (also installed for user %s)" % module.params["work_profile_user"]
        elif rc2 == 124:
            module.warn(
                "work profile install timed out after %ss (device may be showing an install confirmation "
                "dialog) — app may not be available in work profile" % install_timeout
            )
        else:
            module.warn("work profile install failed (rc=%d) — app may not be available in work profile" % rc2)

    module.exit_json(changed=True, reason=reason)


if __name__ == "__main__":
    main()
