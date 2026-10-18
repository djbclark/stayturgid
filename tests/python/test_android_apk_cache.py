"""android_apk: a checksum-pinned APK downloads once per control node and every caller gets its own copy."""

import hashlib
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "android_apk",
    Path(__file__).resolve().parents[2]
    / "ansible_collections/stayturgid/android_common/plugins/modules/android_apk.py",
)
assert _spec is not None and _spec.loader is not None
android_apk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(android_apk)


class _Fail(Exception):
    pass


class _Module:
    def __init__(self, tmp_path, checksum):
        self.tmpdir = str(tmp_path / "mod")
        Path(self.tmpdir).mkdir(exist_ok=True)
        self.params = {"checksum": checksum}

    def fail_json(self, **kw):
        raise _Fail(kw["msg"])


def _fetcher(tmp_path, data, calls):
    def fetch():
        calls.append(1)
        p = tmp_path / ("dl%d.apk" % len(calls))
        p.write_bytes(data)
        return str(p)

    return fetch


def test_second_caller_uses_the_cache_and_gets_a_private_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(android_apk, "APK_CACHE_DIR", str(tmp_path / "cache"))
    data = b"apk bytes"
    mod = _Module(tmp_path, "sha256:" + hashlib.sha256(data).hexdigest())
    calls = []
    first = android_apk.cached_download(mod, _fetcher(tmp_path, data, calls))
    second = android_apk.cached_download(mod, _fetcher(tmp_path, data, calls))
    assert len(calls) == 1
    assert first != second
    assert Path(second).read_bytes() == data
    Path(first).write_bytes(b"resigned")  # resign_apk rewrites its copy in place
    assert Path(android_apk.cached_download(mod, _fetcher(tmp_path, data, calls))).read_bytes() == data


def test_a_bad_download_is_never_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(android_apk, "APK_CACHE_DIR", str(tmp_path / "cache"))
    mod = _Module(tmp_path, "sha256:" + hashlib.sha256(b"good").hexdigest())
    with pytest.raises(_Fail):
        android_apk.cached_download(mod, _fetcher(tmp_path, b"evil", []))
    assert not list((tmp_path / "cache").glob("*.apk"))


def test_no_checksum_means_no_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(android_apk, "APK_CACHE_DIR", str(tmp_path / "cache"))
    calls = []
    android_apk.cached_download(_Module(tmp_path, None), _fetcher(tmp_path, b"x", calls))
    android_apk.cached_download(_Module(tmp_path, None), _fetcher(tmp_path, b"x", calls))
    assert len(calls) == 2
