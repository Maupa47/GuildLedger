import shutil

import pytest

from guildledger.__main__ import main
from guildledger.config import ConfigError, load, resolve_tz


def write_config(tmp_path, sv, extra=""):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        f'sv_path = "{sv.as_posix()}"\ntimezone = "UTC"\nmode = "direct"\ncollector = "tester"\n'
        f'[direct]\nchat_webhook = "https://discord.invalid/secret-chat"\n{extra}',
        encoding="utf-8",
    )
    return cfg


def test_import_twice_and_stats(tmp_path, fixtures, capsys):
    sv = tmp_path / "GuildLedger.lua"
    shutil.copy(fixtures / "basic.lua", sv)
    cfg = write_config(tmp_path, sv)

    assert main(["--config", str(cfg), "import", str(sv)]) == 0
    assert (tmp_path / "spool.db").exists()
    assert (tmp_path / "logs" / "Synthetic Guild" / "chat-2026-11-11.log").exists()
    assert main(["--config", str(cfg), "import", str(sv)]) == 0

    assert main(["--config", str(cfg), "stats"]) == 0
    out = capsys.readouterr().out
    assert "Synthetic Guild (club 100200300)" in out
    assert "6 rows: 5 with text, 1 without text" in out
    assert "secret-chat" not in out


def test_watch_once(tmp_path, fixtures, caplog):
    sv = tmp_path / "GuildLedger.lua"
    shutil.copy(fixtures / "basic.lua", sv)
    cfg = write_config(tmp_path, sv, "[watch]\nstable_seconds = 0.01\npoll_seconds = 0.01\n")
    caplog.set_level("INFO")
    assert main(["--config", str(cfg), "watch", "--once", "--no-post"]) == 0
    assert "chat +6" in caplog.text
    assert "secret-chat" not in caplog.text


def test_watch_once_bad_file(tmp_path, caplog):
    sv = tmp_path / "GuildLedger.lua"
    sv.write_text("GuildLedgerDB = {", encoding="utf-8")
    cfg = write_config(tmp_path, sv, "[watch]\nstable_seconds = 0.01\npoll_seconds = 0.01\n")
    assert main(["--config", str(cfg), "watch", "--once", "--no-post"]) == 0
    assert "retrying once" in caplog.text and "giving up" in caplog.text


def test_export_since(tmp_path, fixtures, capsys):
    sv = tmp_path / "GuildLedger.lua"
    shutil.copy(fixtures / "basic.lua", sv)
    cfg = write_config(tmp_path, sv)
    main(["--config", str(cfg), "import", "--no-export", str(sv)])
    assert not (tmp_path / "logs").exists()
    assert main(["--config", str(cfg), "export", "--since", "2026-11-12"]) == 0
    assert "wrote 1 file(s)" in capsys.readouterr().out  # the yearly roster file is always whole
    assert [p.name for p in (tmp_path / "logs").rglob("*.log")] == ["roster-2026.log"]
    assert main(["--config", str(cfg), "export", "--since", "2026-11-11"]) == 0
    assert "wrote 2 file(s)" in capsys.readouterr().out


def test_config_errors(tmp_path):
    bad = tmp_path / "c.toml"
    bad.write_text('mode = "carrier-pigeon"\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        load(bad)
    with pytest.raises(ConfigError):
        load(tmp_path / "missing.toml")


def test_config_repr_hides_webhooks(tmp_path, fixtures):
    cfg = load(write_config(tmp_path, tmp_path / "x.lua"))
    assert cfg.chat_webhook.endswith("secret-chat")
    assert "secret-chat" not in repr(cfg)


def test_resolve_tz_fallbacks():
    from datetime import timezone

    assert resolve_tz("UTC") is timezone.utc
    assert resolve_tz("local") is None
    assert resolve_tz("Not/AZone") is None


def test_single_instance_lock(tmp_path):
    from guildledger.lock import InstanceLock
    first, second = InstanceLock(tmp_path / "watch.lock"), InstanceLock(tmp_path / "watch.lock")
    assert first.acquire()
    assert not second.acquire()  # a second companion on the same folder is refused
    first.release()
    assert second.acquire()
    second.release()


def test_watch_refuses_to_run_twice(tmp_path, fixtures, caplog):
    from guildledger.lock import InstanceLock
    sv = tmp_path / "GuildLedger.lua"
    shutil.copy(fixtures / "basic.lua", sv)
    cfg = write_config(tmp_path, sv, "[watch]\nstable_seconds = 0.01\npoll_seconds = 0.01\n")
    with InstanceLock(tmp_path / "watch.lock") as held:
        assert held.acquire()
        assert main(["--config", str(cfg), "watch", "--once", "--no-post"]) == 1
    assert "already running" in caplog.text
