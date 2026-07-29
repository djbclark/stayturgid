import os
from unittest import mock

import pytest

from control.lib.firerpa_consent import HealSession, check_consent


@pytest.fixture
def mock_device():
    device = mock.Mock()
    return device


def test_heal_session_notifications(mock_device):
    session = HealSession(mock_device, "s24")
    session.add_action("restart_sshd")
    session.add_action("restart_shizuku")

    # Should have called termux-notification twice
    assert mock_device.execute_script.call_count == 2

    with mock.patch("subprocess.run") as mock_run:
        session.close()
        # Should remove notification
        assert mock_device.execute_script.call_count == 3
        # Should call osascript
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "healed s24: restart_sshd, restart_shizuku (2 actions)" in args[2]


@pytest.mark.asyncio
async def test_check_consent_env_skip():
    with mock.patch.dict(os.environ, {"STAYTURGID_FIRERPA_HEAL_NOCONSENT": "1"}):
        assert await check_consent("test") is True

    with mock.patch.dict(os.environ, {"STAYTURGID_FIRERPA_HEAL_QUIET": "1"}):
        assert await check_consent("test") is True


@pytest.mark.asyncio
async def test_check_consent_osascript_proceed():
    mock_run = mock.Mock()
    mock_run.stdout = "proceed"
    with mock.patch.dict(os.environ, clear=True), mock.patch("subprocess.run", return_value=mock_run):
        assert await check_consent("test") is True


@pytest.mark.asyncio
async def test_check_consent_osascript_refuse():
    mock_run = mock.Mock()
    mock_run.stdout = "refuse"
    with mock.patch.dict(os.environ, clear=True), mock.patch("subprocess.run", return_value=mock_run):
        assert await check_consent("test") is False


@pytest.mark.asyncio
async def test_check_consent_elicitation():
    mock_context = mock.AsyncMock()

    mock_result = mock.Mock()
    mock_result.action = "accept"
    mock_result.data.consent = "proceed"
    mock_context.elicit.return_value = mock_result

    with mock.patch.dict(os.environ, clear=True):
        assert await check_consent("test", mock_context) is True


@pytest.mark.asyncio
async def test_check_consent_elicitation_refuse():
    mock_context = mock.AsyncMock()

    # Test accept with refuse data
    mock_result = mock.Mock()
    mock_result.action = "accept"
    mock_result.data.consent = "refuse"
    mock_context.elicit.return_value = mock_result

    with mock.patch.dict(os.environ, clear=True):
        assert await check_consent("test", mock_context) is False

    # Test decline action
    mock_result = mock.Mock()
    mock_result.action = "decline"
    mock_context.elicit.return_value = mock_result

    with mock.patch.dict(os.environ, clear=True):
        assert await check_consent("test", mock_context) is False

    # Test cancel action
    mock_result = mock.Mock()
    mock_result.action = "cancel"
    mock_context.elicit.return_value = mock_result

    with mock.patch.dict(os.environ, clear=True):
        assert await check_consent("test", mock_context) is False
