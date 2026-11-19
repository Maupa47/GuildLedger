"""Easy setup (0.6.0): finding the data files, the personal package, self-update, the first test upload."""

import hashlib
import io
import shutil
import zipfile

import pytest

from guildledger import __version__, detect, package, update
from guildledger.__main__ import main
from guildledger.config import load
from guildledger.discord import Response


def make_wow(root, accounts=("ACC1",), flavor="_forever_"):
    files = []
    for acc in accounts:
        d = root / "World of Warcraft" / flavor / "WTF" / "Account" / acc / "SavedVariables"
        d.mkdir(parents=True)
        (d / "GuildLedger.lua").write_text("GuildLedgerDB = {}\n", encoding="utf-8")
        files.append(d / "GuildLedger.lua")
    return root / "World of Warcraft", files


# ------------------------------------------------------------------------------------------- detect

@pytest.fixture(autouse=True)
def no_real_wow(monkeypatch, tmp_path):
    """The search looks only at the test's folders, never at a WoW installed on this machine (its drives,
    the Windows registry, the home folder)."""
    monkeypatch.setattr(detect, "_registry_roots", lambda: [])
    monkeypatch.setattr(detect.string, "ascii_uppercase", "")  # Windows: no drive letters to scan
    monkeypatch.setattr(detect.Path, "home", classmethod(lambda cls: tmp_path / "no-home"))


def test_finds_every_account_of_a_wow_folder(tmp_path):
    wow, files = make_wow(tmp_path, ("ACC1", "12345678#1"))
    (wow / "_forever_" / "WTF" / "Account" / "ACC1" / "SavedVariables" / "GuildLedger.lua.bak").write_text("x")
    assert detect.sv_files_in(wow) == sorted(files)
    assert detect.find_sv_files([wow]) == sorted(files)
    # the version folder or its WTF folder work as well
    assert detect.sv_files_in(wow / "_forever_") == sorted(files)
    assert detect.sv_files_in(wow / "_forever_" / "WTF") == sorted(files)


def test_other_game_versions_are_not_read(tmp_path):
    wow, _ = make_wow(tmp_path, ("ACC1",), flavor="_retail_")
    assert detect.sv_files_in(wow) == [], "a GuildLedger.lua of another WoW version may hold another guild"
    wow2, files = make_wow(tmp_path / "beta", ("ACC1",), flavor="_classic_beta_")
    assert detect.sv_files_in(wow2) == files


def test_watch_without_sv_path_reads_all_accounts(tmp_path, fixtures, caplog):
    wow, files = make_wow(tmp_path / "games", ("ACC1", "ACC2"))
    shutil.copy(fixtures / "basic.lua", files[0])
    shutil.copy(fixtures / "basic.lua", files[1])
    cfg = tmp_path / "config.toml"
    cfg.write_text(f"wow_dir = '{wow.as_posix()}'\ncollector = \"tester\"\n[general]\ntimezone = \"UTC\"\n"
                   "[watch]\nstable_seconds = 0.01\npoll_seconds = 0.01\n", encoding="utf-8")
    caplog.set_level("INFO")
    assert main(["--config", str(cfg), "watch", "--once", "--no-post"]) == 0
    assert caplog.text.count("watching ") == 2
    assert "chat +6" in caplog.text and "chat +0" in caplog.text, "the second account's copy adds nothing twice"


def test_watch_once_without_any_file_says_so(tmp_path, caplog, monkeypatch):
    monkeypatch.setattr(detect, "candidate_roots", lambda extra=None: list(extra or []))
    cfg = tmp_path / "config.toml"
    cfg.write_text('collector = "tester"\n', encoding="utf-8")
    assert main(["--config", str(cfg), "watch", "--once", "--no-post"]) == 1
    assert "no GuildLedger data file found" in caplog.text


# ------------------------------------------------------------------------------------------- package

def test_personal_package_has_a_working_config_and_no_other_secret():
    text = package.render_config("https://discord.com/api/webhooks/1/tok-en", 'Offi "Quote" Cer', "UTC")
    data = package.build_zip(config_text=text)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        assert {"start-companion.cmd", "autostart-on.cmd", "autostart-off.cmd", "config.example.toml",
                "COLLECTOR.md", "config.toml", "guildledger/__main__.py", "guildledger/update.py"} <= names
        assert not any("test" in n or n.endswith((".db", ".pyc")) for n in names)
        assert b"\r\n" in zf.read("start-companion.cmd") and b"\n" not in zf.read(
            "start-companion.cmd").replace(b"\r\n", b"")
        cfg_bytes = zf.read("config.toml")
    assert len(data) < 1024 * 1024, "small enough for a Discord attachment"


def test_rendered_config_loads(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(package.render_config("https://discord.com/api/webhooks/1/tok-en", 'Offi "Quote" Cer', "UTC"),
                 encoding="utf-8")
    cfg = load(p)
    assert cfg.mode == "upload" and cfg.collector == 'Offi "Quote" Cer' and cfg.timezone == "UTC"
    assert cfg.ingest_webhook.endswith("/tok-en") and cfg.sv_path is None


def test_public_package_is_reproducible_and_unpersonalised(tmp_path):
    a, b = package.build_zip(), package.build_zip()
    assert a == b
    with zipfile.ZipFile(io.BytesIO(a)) as zf:
        assert "config.toml" not in zf.namelist()
    zip_path, ver_path = package.write_release(tmp_path)
    version, sha = ver_path.read_text("utf-8").split()
    assert version == __version__ and sha == hashlib.sha256(zip_path.read_bytes()).hexdigest()


# ------------------------------------------------------------------------------------------- update

def release(version, data=None):
    data = data if data is not None else package.build_zip()
    files = {update.VERSION_NAME: f"{version} {hashlib.sha256(data).hexdigest()}\n".encode(), update.ZIP_NAME: data}
    return lambda url: files[url.rsplit("/", 1)[1]]


def officer_folder(tmp_path):
    root = tmp_path / "GuildLedger"
    (root / "guildledger").mkdir(parents=True)
    (root / "guildledger" / "__init__.py").write_text("old", encoding="utf-8")
    (root / "config.toml").write_text("SECRET", encoding="utf-8")
    (root / "spool.db").write_text("DATA", encoding="utf-8")
    return root


def test_update_replaces_code_and_keeps_settings(tmp_path):
    root = officer_folder(tmp_path)
    assert update.update(root, "0.5.0", release("9.9.9")) == "9.9.9"
    assert (root / "guildledger" / "__init__.py").read_text("utf-8") != "old"
    assert (root / "start-companion.cmd").is_file() and (root / "COLLECTOR.md").is_file()
    assert (root / "config.toml").read_text("utf-8") == "SECRET"
    assert (root / "spool.db").read_text("utf-8") == "DATA"
    assert not list(root.rglob("*.new"))


def test_no_update_when_not_newer(tmp_path):
    root = officer_folder(tmp_path)
    assert update.update(root, "9.9.9", release("9.9.9")) is None
    assert update.update(root, "10.0.0", release("9.9.9")) is None
    assert (root / "guildledger" / "__init__.py").read_text("utf-8") == "old"
    assert update.newer("0.10.0", "0.9.9") and not update.newer("0.6.0", "0.6.0")


def bad_zip(names):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("guildledger/__init__.py", "x")
        for n in names:
            zf.writestr(n, "evil")
    return buf.getvalue()


@pytest.mark.parametrize("name", ["config.toml", "../evil.py", "guildledger/../../evil.py", "evil.exe",
                                  "guildledger/sub/evil.py", "/abs.cmd", "spool.db"])
def test_update_refuses_unexpected_files(tmp_path, name):
    root = officer_folder(tmp_path)
    with pytest.raises(update.UpdateError):
        update.update(root, "0.5.0", release("9.9.9", bad_zip([name])))
    assert (root / "config.toml").read_text("utf-8") == "SECRET"
    assert (root / "guildledger" / "__init__.py").read_text("utf-8") == "old", "nothing written at all"
    assert not (tmp_path / "evil.py").exists()


def test_update_refuses_a_wrong_checksum(tmp_path):
    root = officer_folder(tmp_path)
    good = release("9.9.9")

    def fetch(url):
        data = good(url)
        return data + b"x" if url.endswith(update.ZIP_NAME) else data

    with pytest.raises(update.UpdateError, match="checksum"):
        update.update(root, "0.5.0", fetch)


def test_a_repository_checkout_never_self_updates():
    assert update.install_root() is None


# ------------------------------------------------------------------------------------------- first test upload

def test_first_start_sends_one_empty_test_upload(tmp_path, fixtures):
    from guildledger import __main__ as cli

    sent = []

    def transport(url, data, content_type="application/json"):
        sent.append((url, data))
        return Response(200, {}, b"{}")

    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(package.render_config("https://discord.invalid/api/webhooks/1/secret", "Offi Cer", "UTC"),
                        encoding="utf-8")
    cfg = load(cfg_path)
    state = {}
    cli._say_hello(cfg, state, transport)
    assert len(sent) == 1 and b"gl1 Offi Cer 0 " in sent[0][1]
    cli._say_hello(cfg, cli._load_state(cfg), transport)
    assert len(sent) == 1, "only once per upload link"
