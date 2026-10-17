#!/usr/bin/env bash
# Copied from Plektra (djbclark/plektra-djbclark, plk/base .forgejo/scripts/fast-disk.sh), 2026-10-17.
# fast-disk.sh — run as root right after checkout in a Hyades job. Moves the workspace and the
# Gradle home off the job's virtiofs root (small-file operations at 0.03-0.2x of a laptop) onto an
# ext4 image on a loop device. Same commit, 2026-10-14: 458 s as-is, 393 s on a guest tmpfs, 324 s
# on the loop image. Not /dev/shm (noexec: aapt2 would not run); not podman --tmpfs (served by the
# host through the same virtiofs). @xy (SIPB/hyades#2) recommends a guest tmpfs (CI RAM limit 64 GB);
# keep the loop: it measured faster, and it does not pin the Gradle home in guest RAM. libkrun#924
# (slp): the other transient-data option is virtio-blk; crun has no scratch-disk annotation yet.
# Details: docs/comparison.md and docs/hyades-disk-research.md in
# https://forgejo.mit.edu/djbclark/loopback-port-shim
set -euo pipefail

img=/root/fast.img
fast=/mnt/fast
command -v mkfs.ext4 >/dev/null || { apt-get update -qq && apt-get install -y -qq e2fsprogs; }
truncate -s 40G "$img"
mkfs.ext4 -q -F -E lazy_itable_init=1,lazy_journal_init=1 "$img"
mkdir -p "$fast"
mount -o loop,noatime "$img" "$fast"
mkdir -p "$fast/ws" "$fast/gradle"
cp -a "$GITHUB_WORKSPACE/." "$fast/ws/"
# Hyades runs every step in the job's initial cwd (SIPB's crun krun exec ignores the step's working
# directory, and with it `working-directory:`), which is now the directory under this mount. Java,
# resolving the path by name, sees the mount; a relative open() in bash or Python does not. So
# every later run step must begin with `cd "$PWD"` (or cd to an absolute path).
mount --bind "$fast/ws" "$GITHUB_WORKSPACE"
echo "GRADLE_USER_HOME=$fast/gradle" >>"$GITHUB_ENV"
df -hT "$GITHUB_WORKSPACE" "$fast"
