"""Daily backup and restore check (Phase 5b acceptance: the backup restores into a working database)."""

import gzip
import time

import pytest

from guildledger_bot.collection import backup
from guildledger_bot.store import Archive


@pytest.fixture
def archive(tmp_path):
    a = Archive(tmp_path / "guildledger.db")
    a.import_rows("1", "Guild", [{"id": "1:1", "t": 1794355200, "s": "g", "a": "Alia Testwood", "m": "hi",
                                  "src": "live"}], [], "c1")
    yield a
    a.close()


def test_backup_restores_while_the_bot_keeps_writing(archive, tmp_path):
    f = backup.make_backup(tmp_path / "guildledger.db", tmp_path / "backups")
    archive.import_rows("1", "Guild", [{"id": "2:2", "t": 1794355300, "s": "g", "a": "Bram", "m": "later",
                                        "src": "live"}], [], "c1")
    assert f.name.startswith("guildledger-") and f.name.endswith(".db.gz")
    assert backup.verify(f) == {"chat": 1, "events": 0, "uploads": 0}


def test_old_backups_are_pruned(archive, tmp_path):
    out = tmp_path / "backups"
    old = backup.make_backup(tmp_path / "guildledger.db", out, now=time.time() - 20 * 86400)
    import os
    os.utime(old, (time.time() - 20 * 86400,) * 2)
    new = backup.make_backup(tmp_path / "guildledger.db", out, keep_days=14)
    assert not old.exists() and new.exists() and backup.newest(out) == new


def test_corrupt_backup_fails_verification(tmp_path):
    bad = tmp_path / "guildledger-x.db.gz"
    bad.write_bytes(gzip.compress(b"this is not a database" * 100))
    with pytest.raises(Exception):
        backup.verify(bad)
