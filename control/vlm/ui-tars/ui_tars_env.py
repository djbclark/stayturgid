#!/usr/bin/env python3
"""UI-TARS / llama-server configuration (vendor-neutral layout).

Replaces ui_tars_env.sh. Callable from shell or importable from Python.

Shell usage:
  python3 control/vlm/ui-tars/ui_tars_env.py --get port
  python3 control/vlm/ui-tars/ui_tars_env.py --get model_dir

Python usage:
  from ui_tars_env import UiTarsConfig
  cfg = UiTarsConfig()
  print(cfg.port)
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class UiTarsConfig:
    home: str = field(default_factory=lambda: os.environ.get(
        "UI_TARS_HOME",
        str(Path.home() / ".local" / "share" / "ui-tars"),
    ))

    @property
    def model_dir(self) -> str:
        return (
            os.environ.get("UI_TARS_MODEL_DIR")
            or os.environ.get("STAYTURGID_VLM_MODEL_DIR")
            or os.environ.get("QSS_VLM_MODEL_DIR")
            or os.path.join(self.home, "models", "1.5-7b")
        )

    @property
    def port(self) -> str:
        return os.environ.get(
            "UI_TARS_PORT",
            os.environ.get("STAYTURGID_VLM_PORT",
                           os.environ.get("QSS_VLM_PORT", "8081")),
        )

    @property
    def pid_file(self) -> str:
        return os.environ.get(
            "UI_TARS_PID_FILE",
            os.path.join(self.home, "server", "server.pid"),
        )

    @property
    def log_file(self) -> str:
        return (
            os.environ.get("UI_TARS_LOG")
            or os.environ.get("STAYTURGID_VLM_LOG")
            or os.environ.get("QSS_VLM_LOG")
            or (
                str(Path.home() / "Library" / "Logs" / "ui-tars" / "server.log")
                if platform.system() == "Darwin"
                else os.path.join(self.home, "server", "server.log")
            )
        )

    @property
    def working_dir(self) -> str:
        return os.path.join(
            os.environ.get("UI_TARS_HOME", self.home),
            "server",
        )

    @property
    def ngl(self) -> str:
        val = os.environ.get(
            "UI_TARS_NGL",
            os.environ.get("STAYTURGID_VLM_NGL",
                           os.environ.get("QSS_VLM_NGL", "")),
        )
        if val:
            return val
        return "99" if platform.system() == "Darwin" else "0"

    @property
    def llama_server_bin(self) -> str:
        for env_name in ("UI_TARS_LLAMA_SERVER", "STAYTURGID_VLM_LLAMA_SERVER", "QSS_VLM_LLAMA_SERVER"):
            val = os.environ.get(env_name, "")
            if val and os.access(val, os.X_OK):
                return val
        found = shutil.which("llama-server")
        if found:
            return found
        brew_prefix = self._brew_prefix("llama.cpp")
        if brew_prefix:
            path = os.path.join(brew_prefix, "bin", "llama-server")
            if os.access(path, os.X_OK):
                return path
        return ""

    @staticmethod
    def _brew_prefix(pkg: str) -> str:
        try:
            r = subprocess.run(
                ["brew", "--prefix", pkg],
                capture_output=True, text=True, timeout=5,
            )
            return r.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            return ""

    @property
    def health_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/health"

    def is_healthy(self) -> bool:
        import urllib.request
        try:
            urllib.request.urlopen(self.health_url, timeout=5)
            return True
        except Exception:
            return False

    @property
    def service_label(self) -> str:
        return "homebrew.mxcl.ui-tars"

    @property
    def service_plist(self) -> str:
        return str(Path.home() / "Library" / "LaunchAgents" / f"{self.service_label}.plist")

    @property
    def legacy_service_label(self) -> str:
        return "homebrew.mxcl.qss-ui-tars"

    @property
    def legacy_service_plist(self) -> str:
        return str(Path.home() / "Library" / "LaunchAgents" / f"{self.legacy_service_label}.plist")

    def service_installed(self) -> bool:
        return os.path.isfile(self.service_plist)

    def _get(self, key: str) -> str:
        mapping: dict[str, Any] = {
            "home": self.home,
            "model_dir": self.model_dir,
            "port": self.port,
            "pid_file": self.pid_file,
            "log_file": self.log_file,
            "working_dir": self.working_dir,
            "ngl": self.ngl,
            "llama_server_bin": self.llama_server_bin,
            "health_url": self.health_url,
            "service_label": self.service_label,
            "service_plist": self.service_plist,
            "legacy_service_label": self.legacy_service_label,
            "legacy_service_plist": self.legacy_service_plist,
        }
        if key in mapping:
            val = mapping[key]() if callable(mapping[key]) else mapping[key]
            return str(val) if val is not None else ""
        return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="UI-TARS configuration resolver")
    parser.add_argument("--get", required=True, metavar="KEY",
                        help="Configuration key to resolve")
    args = parser.parse_args()

    cfg = UiTarsConfig()
    result = cfg._get(args.get)
    print(result)
    return 0 if result else 1


if __name__ == "__main__":
    sys.exit(main())
