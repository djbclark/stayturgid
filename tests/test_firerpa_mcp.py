from unittest import mock

import pytest

from control.bin.firerpa_mcp import (
    _resolve_host,
    device_status,
    get_tailscale_ip,
    heal_device,
    restart_sshd,
)
from control.lib.firerpa_fleet import FirerpaTarget


def test_get_tailscale_ip():
    mock_res = mock.Mock()
    mock_res.returncode = 0
    mock_res.stdout = "Warning: out of date\n100.123.123.123\n"
    with mock.patch("subprocess.run", return_value=mock_res):
        assert get_tailscale_ip() == "100.123.123.123"


def test_resolve_host():
    fleet = [FirerpaTarget(alias="s24", ip="1.2.3.4")]
    with mock.patch("control.bin.firerpa_mcp.get_fleet", return_value=fleet):
        assert _resolve_host("s24").ip == "1.2.3.4"
        assert _resolve_host("unknown") is None


def test_device_status_error():
    with mock.patch("control.bin.firerpa_mcp._connect", side_effect=ValueError("foo")):
        res = device_status("unknown")
        assert "error" in res


@pytest.mark.asyncio
async def test_heal_device_refused():
    mock_ctx = mock.Mock()
    with mock.patch("control.bin.firerpa_mcp.check_consent", return_value=False):
        res = await heal_device("s24", mock_ctx)
        assert res == {"status": "refused"}


@pytest.mark.asyncio
async def test_heal_device_proceed():
    mock_ctx = mock.Mock()
    mock_device = mock.Mock()

    with (
        mock.patch("control.bin.firerpa_mcp.check_consent", return_value=True),
        mock.patch("control.bin.firerpa_mcp._connect", return_value=mock_device),
        mock.patch("control.bin.firerpa_mcp._resolve_host", return_value=True),
        mock.patch("control.bin.firerpa_heal.is_sshd_alive", return_value=True),
        mock.patch("control.bin.firerpa_heal.is_port_5555_alive", return_value=True),
        mock.patch("control.bin.firerpa_heal.is_bootloop_alive", return_value=True),
        mock.patch("control.bin.firerpa_mcp.HealSession") as mock_session,
    ):
        res = await heal_device("s24", mock_ctx)
        assert res["sshd_final"] == "up"
        assert res["shizuku_final"] == "up"

        mock_session.return_value.close.assert_called_once()


@pytest.mark.asyncio
async def test_restart_sshd():
    mock_ctx = mock.Mock()
    mock_device = mock.Mock()

    with (
        mock.patch("control.bin.firerpa_mcp.check_consent", return_value=True),
        mock.patch("control.bin.firerpa_mcp._connect", return_value=mock_device),
        mock.patch("control.bin.firerpa_heal.remove_sshd_down"),
        mock.patch("control.bin.firerpa_heal.restart_sshd", return_value="up"),
        mock.patch("control.bin.firerpa_mcp.HealSession") as mock_session,
    ):
        res = await restart_sshd("s24", mock_ctx)
        assert res == {"status": "up", "consent": "proceeded"}
        mock_session.return_value.add_action.assert_any_call("remove_sshd_down")
        mock_session.return_value.add_action.assert_any_call("restart_sshd")
