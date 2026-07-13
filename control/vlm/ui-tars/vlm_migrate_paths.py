#!/usr/bin/env python3
"""One-time UI-TARS path migration: ~/.config/stayturgid/ -> vendor-neutral layout.

Replaces vlm_migrate_paths.sh. Moves old models, logs, pid files from the
stayturgid-embedded path to ~/.local/share/ui-tars/.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ui_tars_env import UiTarsConfig


def move_path(src: str, dst: str) -> None:
    if not os.path.exists(src):
        return
    if os.path.exists(dst):
        print(f"  skip {src} (destination exists: {dst})")
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.move(src, dst)
    print(f"  moved {src} -> {dst}")


def move_tree(src: str, dst: str) -> None:
    if not os.path.isdir(src):
        return
    entries = [e for e in os.listdir(src) if not e.startswith(".")]
    if not entries:
        return
    os.makedirs(dst, exist_ok=True)
    dst_entries = os.listdir(dst) if os.path.isdir(dst) else []
    if not dst_entries:
        for entry in entries:
            shutil.move(os.path.join(src, entry), os.path.join(dst, entry))
        print(f"  moved {src}/* -> {dst}/")
    else:
        print(f"  merge {src} -> {dst} (destination not empty)")
        for entry in entries:
            sp = os.path.join(src, entry)
            dp = os.path.join(dst, entry)
            if not os.path.exists(dp):
                shutil.move(sp, dp)
                print(f"    moved {entry}")


def unload_legacy_agent(cfg: UiTarsConfig) -> None:
    legacy = cfg.legacy_service_plist
    if os.path.isfile(legacy):
        try:
            domain = f"gui/{os.getuid()}"
            subprocess.run(
                ["launchctl", "bootout", domain, legacy],
                capture_output=True, timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        os.remove(legacy)
        print(f"  removed legacy LaunchAgent {os.path.basename(legacy)}")


def prune_empty(start_dir: str, root_prefix: str) -> None:
    d = os.path.abspath(start_dir)
    prefix = os.path.abspath(root_prefix)
    while d.startswith(prefix) and os.path.isdir(d):
        try:
            entries = os.listdir(d)
            if entries:
                return
            os.rmdir(d)
            print(f"  removed empty {d}")
        except OSError:
            return
        d = os.path.dirname(d)


def main() -> int:
    cfg = UiTarsConfig()
    old_stay = str(Path.home() / ".config" / "stayturgid")

    print("==> UI-TARS path migration (stayturgid -> vendor-neutral)")
    unload_legacy_agent(cfg)

    move_tree(f"{old_stay}/models/ui-tars-1.5-7b", cfg.model_dir)
    move_path(f"{old_stay}/logs/ui-tars-server.log", cfg.log_file)
    move_path(f"{old_stay}/ui-tars-server.pid", cfg.pid_file)

    prune_empty(f"{old_stay}/models/ui-tars-1.5-7b", old_stay)
    prune_empty(f"{old_stay}/models", old_stay)

    print(f"==> Done. UI-TARS home: {cfg.home}")
    print(f"    stayturgid fleet data unchanged under {old_stay}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
