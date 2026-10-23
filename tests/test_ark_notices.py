from __future__ import annotations

from unittest.mock import patch

import pytest

from functions import json_db_cache
from functions.ark_notices import (
    consume_ark_notice_update,
    is_crash_dump_notice,
    is_execsave_notice,
    is_restart_countdown_notice,
    is_server_removal_notice,
    replaces_previous_ark_notice,
    restart_notice_is_expired,
)
from functions.asa_client import parse_announcement
from functions.asa_models import AsaAnnouncement
import db.files as files


@pytest.fixture(autouse=True)
def reset_json_cache():
    json_db_cache.reset()
    yield
    json_db_cache.reset()


def test_announcement_dotdot_is_empty():
    assert parse_announcement("..").text is None
    assert parse_announcement(".").text is None
    assert parse_announcement("").text is None


def test_announcement_keeps_br_newlines():
    parsed = parse_announcement("Servers <br> coming down<br/>for maintenance")
    assert parsed.fetch_ok
    assert parsed.text is not None
    assert "\n" in parsed.text
    assert "Servers" in parsed.text
    assert "maintenance" in parsed.text


def test_files_ark_notification_set_get_clear(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "DATA_DIR", tmp_path)
    monkeypatch.setattr(files, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(files, "RATE_STATE_DIR", tmp_path / "rate_state")
    files.set_ark_notification("111", "222")
    assert files.get_ark_notification("111") == {"channel_id": "222"}
    assert files.get_ark_notification_channels() == [
        {"guild_id": "111", "channel_id": "222", "last_message_id": None}
    ]
    assert files.clear_ark_notification("111") is True
    assert files.get_ark_notification("111") is None
    assert files.get_ark_notification_channels() == []
    assert files.clear_ark_notification("111") is False


def test_files_previous_ark_notice(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "DATA_DIR", tmp_path)
    monkeypatch.setattr(files, "RATE_STATE_DIR", tmp_path / "rate_state")
    monkeypatch.setattr(files, "ARK_NOTICE_STATE_FILE", tmp_path / "rate_state" / "ark_notice.json")
    assert files.get_previous_ark_notice() is None
    files.save_previous_ark_notice("hello")
    assert files.get_previous_ark_notice() == "hello"
    files.save_previous_ark_notice("")
    assert files.get_previous_ark_notice() == ""


def test_consume_first_run_seeds_without_posting():
    with patch(
        "functions.ark_notices.current_announcement",
        return_value=AsaAnnouncement(fetch_ok=True, text="Servers down"),
    ):
        with patch("functions.ark_notices.db.get_previous_ark_notice", return_value=None):
            with patch("functions.ark_notices.db.save_previous_ark_notice") as save:
                text, channels = consume_ark_notice_update()
    assert text is None
    assert channels == []
    save.assert_called_once_with("Servers down")


def test_consume_new_text_posts_to_channels():
    channels = [{"guild_id": "1", "channel_id": "2"}]
    with patch(
        "functions.ark_notices.current_announcement",
        return_value=AsaAnnouncement(fetch_ok=True, text="New notice"),
    ):
        with patch("functions.ark_notices.db.get_previous_ark_notice", return_value=""):
            with patch("functions.ark_notices.db.save_previous_ark_notice") as save:
                with patch(
                    "functions.ark_notices.db.get_ark_notification_channels",
                    return_value=channels,
                ):
                    text, dest = consume_ark_notice_update()
    assert text == "New notice"
    assert dest == channels
    save.assert_called_once_with("New notice")


def test_consume_same_text_does_not_post():
    with patch(
        "functions.ark_notices.current_announcement",
        return_value=AsaAnnouncement(fetch_ok=True, text="Same"),
    ):
        with patch("functions.ark_notices.db.get_previous_ark_notice", return_value="Same"):
            with patch("functions.ark_notices.db.save_previous_ark_notice") as save:
                text, channels = consume_ark_notice_update()
    assert text is None
    assert channels == []
    save.assert_not_called()


def test_consume_empty_after_text_does_not_post():
    with patch(
        "functions.ark_notices.current_announcement",
        return_value=AsaAnnouncement(fetch_ok=True, text=None),
    ):
        with patch("functions.ark_notices.db.get_previous_ark_notice", return_value="Old"):
            with patch("functions.ark_notices.db.save_previous_ark_notice") as save:
                text, channels = consume_ark_notice_update()
    assert text is None
    assert channels == []
    save.assert_called_once_with("")


def test_consume_skips_failed_fetch():
    with patch(
        "functions.ark_notices.current_announcement",
        return_value=AsaAnnouncement(fetch_ok=False, text=None, error="fetch_failed"),
    ):
        with patch("functions.ark_notices.db.get_previous_ark_notice") as get_prev:
            with patch("functions.ark_notices.db.save_previous_ark_notice") as save:
                text, channels = consume_ark_notice_update()
    assert text is None
    assert channels == []
    get_prev.assert_not_called()
    save.assert_not_called()


def test_execsave_and_countdown_helpers():
    assert is_execsave_notice("execsave")
    assert is_execsave_notice("ExecSave")
    assert is_execsave_notice("  execsave.  ")
    assert not is_execsave_notice("Servers down in 5 minutes")
    assert is_restart_countdown_notice("Official servers restart in 15 minutes")
    assert is_restart_countdown_notice("10 min remaining")
    assert is_restart_countdown_notice("Going down in 5 minutes")
    assert is_restart_countdown_notice("Going down in 4 minutes")
    assert is_restart_countdown_notice("Restart in 3 mins")
    assert is_restart_countdown_notice("1 minute remaining")
    assert not is_restart_countdown_notice("Maintenance in 30 minutes")
    assert not is_restart_countdown_notice("execsave")
    assert is_crash_dump_notice("ExecEnableFullCrashDumps")
    assert is_crash_dump_notice("ExecDisableFullCrashDumps")
    assert is_crash_dump_notice("Command: execenablefullcrashdumps now")
    assert is_crash_dump_notice("Command: execdisablefullcrashdumps now")
    assert not is_crash_dump_notice("Servers coming down for maintenance")
    assert is_server_removal_notice("The following servers will be removed from the official list")
    assert is_server_removal_notice("Servers have been decommissioned")
    assert not is_server_removal_notice("Servers restart in 5 minutes")
    assert replaces_previous_ark_notice("Restart in 5 minutes")
    assert replaces_previous_ark_notice("Servers will be removed from the official list")
    assert not replaces_previous_ark_notice("Servers coming down for maintenance")


def test_restart_notice_is_expired():
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
    assert not restart_notice_is_expired(now - timedelta(hours=23, minutes=59), now=now, ttl_hours=24)
    assert restart_notice_is_expired(now - timedelta(hours=24), now=now, ttl_hours=24)
    assert not restart_notice_is_expired(now - timedelta(hours=48), now=now, ttl_hours=0)


def test_consume_execsave_does_not_post():
    with patch(
        "functions.ark_notices.current_announcement",
        return_value=AsaAnnouncement(fetch_ok=True, text="execsave"),
    ):
        with patch(
            "functions.ark_notices.db.get_previous_ark_notice",
            return_value="5 minutes",
        ):
            with patch("functions.ark_notices.db.save_previous_ark_notice") as save:
                with patch(
                    "functions.ark_notices.db.get_ark_notification_channels"
                ) as channels:
                    text, dest = consume_ark_notice_update()
    assert text is None
    assert dest == []
    save.assert_called_once_with("execsave")
    channels.assert_not_called()


def test_consume_crash_dump_notice_does_not_post():
    notice = "ExecEnableFullCrashDumps"
    with patch(
        "functions.ark_notices.current_announcement",
        return_value=AsaAnnouncement(fetch_ok=True, text=notice),
    ):
        with patch(
            "functions.ark_notices.db.get_previous_ark_notice",
            return_value="5 minutes",
        ):
            with patch("functions.ark_notices.db.save_previous_ark_notice") as save:
                with patch(
                    "functions.ark_notices.db.get_ark_notification_channels"
                ) as channels:
                    text, dest = consume_ark_notice_update()
    assert text is None
    assert dest == []
    save.assert_called_once_with(notice)
    channels.assert_not_called()


def test_files_preserves_last_message_on_same_channel(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "DATA_DIR", tmp_path)
    monkeypatch.setattr(files, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(files, "RATE_STATE_DIR", tmp_path / "rate_state")
    files.set_ark_notification("111", "222")
    files.set_ark_notice_last_message("111", "999")
    files.set_ark_notification("111", "222")
    assert files.get_ark_notification("111")["last_message_id"] == "999"
    files.set_ark_notification("111", "333")
    assert files.get_ark_notification("111").get("last_message_id") is None
