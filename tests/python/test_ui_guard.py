import json
import threading
import time

import ui_guard


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

    t = threading.Thread(target=run_guard)
    t.start()

    # Wait for the state file to be written
    for _ in range(20):
        if state_file.is_file():
            break
        time.sleep(0.1)

    assert state_file.is_file()
    data = json.loads(state_file.read_text())
    assert data["host"] == "test_host"
    assert data["status"] == "pending"

    # Now simulate user clicking "Done" on the dashboard
    data["status"] = "done"
    state_file.write_text(json.dumps(data))

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

    t = threading.Thread(target=run_guard)
    t.start()

    # Wait for state file
    for _ in range(20):
        if state_file.is_file():
            break
        time.sleep(0.1)

    assert state_file.is_file()

    # Simulate action completed
    state["detected"] = True

    t.join(timeout=5)
    assert not t.is_alive()
    assert result == [True]
    assert not state_file.is_file()
