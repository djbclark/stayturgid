"""Tests for FIRERPA certificate resolution."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from control.lib import firerpa_auth


def test_certificate_path_uses_environment_override(tmp_path, monkeypatch):
    certificate = tmp_path / "service.pem"
    certificate.write_text("test certificate")
    monkeypatch.setenv("FIRERPA_CERTIFICATE", str(certificate))

    assert firerpa_auth.certificate_path() == str(certificate)


def test_certificate_path_fails_closed_when_missing(tmp_path, monkeypatch):
    missing = tmp_path / "missing.pem"
    monkeypatch.setenv("FIRERPA_CERTIFICATE", str(missing))

    with pytest.raises(FileNotFoundError, match="FIRERPA service certificate not found"):
        firerpa_auth.certificate_path()
