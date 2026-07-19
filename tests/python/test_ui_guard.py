import json
import threading
import time

import ui_guard


def _wait_for_state(path):
    for _ in range(100):
        if path.is_file():
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError:
                pass
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting for valid state in {path}")


def test_ui_guard_allow(monkeypatch):
    monkeypatch.setenv("STAYTURGID_ALLOW_UI_AUTOMATION", "1")
    assert ui_guard.check_ui_guard("test_host", "test_action", "test message") is True


def test_ui_guard_block_and_done(monkeypatch, tmp_path):
    monkeypatch.setenv("STAYTURGID_ALLOW_UI_AUTOMATION", "0")

    # Override get_state_file to write to our tmp directory
    state_file = tmp_path / "pending_ui.json"
    monkeypatch.setattr(ui_guard, "get_state_file", lambda: state_file)

    # We will run check_ui_guard in a separate thread so it blocks
    result = []

    def run_guard():
        res = ui_guard.check_ui_guard("test_host", "test_action", "test message")
        result.append(res)

    t = threading.Thread(target=run_guard, daemon=True)
    t.start()

    try:
        data = _wait_for_state(state_file)
        assert data["host"] == "test_host"
        assert data["status"] == "pending"

        # Now simulate user clicking "Done" on the dashboard
        data["status"] = "done"
        state_file.write_text(json.dumps(data))
    finally:
        if t.is_alive():
            state_file.write_text(json.dumps({"status": "done"}))
            t.join(timeout=5)

    assert not t.is_alive()
    assert result == [True]
    assert not state_file.is_file()  # Cleaned up


def test_ui_guard_block_and_detect(monkeypatch, tmp_path):
    monkeypatch.setenv("STAYTURGID_ALLOW_UI_AUTOMATION", "0")

    state_file = tmp_path / "pending_ui.json"
    monkeypatch.setattr(ui_guard, "get_state_file", lambda: state_file)

    # Detect function that returns True after a bit
    state = {"detected": False}

    def detect_fn():
        return state["detected"]

    result = []

    def run_guard():
        res = ui_guard.check_ui_guard("test_host", "test_action", "test message", detect_fn=detect_fn)
        result.append(res)

    t = threading.Thread(target=run_guard, daemon=True)
    t.start()

    try:
        _wait_for_state(state_file)
    finally:
        # Simulate action completed, including assertion-failure cleanup.
        state["detected"] = True
        t.join(timeout=5)

    assert not t.is_alive()
    assert result == [True]
    assert not state_file.is_file()
