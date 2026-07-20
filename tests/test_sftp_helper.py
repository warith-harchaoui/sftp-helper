"""Tests for sftp_helper.

paramiko's SSHClient is monkeypatched so the suite runs without a real SFTP
server: a MagicMock stands in for the connection and we assert against the
calls made to it.
"""

import json
import os
import stat as stat_mod
from unittest.mock import ANY, MagicMock

import paramiko
import pytest
import yaml

import sftp_helper as sftph
from sftp_helper import main as sftph_main

# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("foo/bar", "/foo/bar"),
        ("/foo/bar", "/foo/bar"),
        ("/foo/bar/", "/foo/bar"),
        ("/foo/bar///", "/foo/bar"),
        ("/", "/"),
        ("", "/"),
    ],
)
def test_normalize_path(raw, expected):
    assert sftph.normalize_path(raw) == expected


def test_strip_sftp_path_full_address():
    cred = {"sftp_host": "example.com"}
    assert sftph.strip_sftp_path("sftp://example.com/folder/file.txt", cred) == "/folder/file.txt"


def test_strip_sftp_path_idempotent_on_relative():
    cred = {"sftp_host": "example.com"}
    once = sftph.strip_sftp_path("/folder/file.txt", cred)
    twice = sftph.strip_sftp_path(once, cred)
    assert once == twice == "/folder/file.txt"


def test_strip_sftp_path_no_scheme():
    cred = {"sftp_host": "example.com"}
    assert sftph.strip_sftp_path("example.com/folder/file.txt", cred) == "/folder/file.txt"


# ---------------------------------------------------------------------------
# credentials() loader
# ---------------------------------------------------------------------------

CRED_KEYS = {
    "sftp_host": "sftp.example.com",
    "sftp_login": "alice",
    "sftp_passwd": "secret",
    "sftp_destination_path": "/var/www/uploads",
    "sftp_https": "https://example.com/uploads",
}


def test_credentials_from_json(tmp_path):
    cfg = tmp_path / "sftp_config.json"
    cfg.write_text(json.dumps(CRED_KEYS))
    cred = sftph.credentials(str(cfg))
    for k, v in CRED_KEYS.items():
        assert cred[k] == v


def test_credentials_from_yaml(tmp_path):
    cfg = tmp_path / "sftp_config.yaml"
    cfg.write_text(yaml.safe_dump(CRED_KEYS))
    cred = sftph.credentials(str(cfg))
    for k, v in CRED_KEYS.items():
        assert cred[k] == v


def test_credentials_from_env(monkeypatch, tmp_path):
    for k, v in CRED_KEYS.items():
        monkeypatch.setenv(k.upper(), v)
    # Point at a directory that contains no config so the loader falls back to env.
    cred = sftph.credentials(str(tmp_path))
    for k, v in CRED_KEYS.items():
        assert cred[k] == v


def test_credentials_missing_key_raises(tmp_path):
    """os_helper >= v1.2.0 raises RuntimeError when no source provides the keys."""
    incomplete = {k: v for k, v in CRED_KEYS.items() if k != "sftp_https"}
    cfg = tmp_path / "sftp_config.json"
    cfg.write_text(json.dumps(incomplete))
    with pytest.raises(RuntimeError):
        sftph.credentials(str(cfg))


# ---------------------------------------------------------------------------
# Mocked SFTP fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_ssh(monkeypatch):
    """Replace paramiko.SSHClient with a MagicMock factory.

    Returns ``(sftp, ssh, factory)`` where ``sftp`` is the mock SFTPClient
    instance handed to callers via ``open_sftp``.
    """
    sftp = MagicMock(name="SFTPClient")
    ssh = MagicMock(name="SSHClient")
    ssh.open_sftp.return_value = sftp
    factory = MagicMock(return_value=ssh)
    monkeypatch.setattr(sftph_main.paramiko, "SSHClient", factory)
    return sftp, ssh, factory


@pytest.fixture
def cred():
    return dict(CRED_KEYS)


def _exists_map(sftp, present):
    """Wire sftp.stat so that paths in ``present`` succeed and others raise."""
    file_mode = stat_mod.S_IFREG | 0o644
    dir_mode = stat_mod.S_IFDIR | 0o755

    def fake_stat(path):
        if path in present:
            st = MagicMock()
            st.st_mode = dir_mode if present[path] == "dir" else file_mode
            st.st_atime = 1700000000
            st.st_mtime = 1700000000
            return st
        raise FileNotFoundError(path)

    sftp.stat.side_effect = fake_stat


# ---------------------------------------------------------------------------
# Connection-level
# ---------------------------------------------------------------------------


def test_get_client_sftp_uses_reject_policy(mock_ssh, cred):
    _, ssh, _ = mock_ssh
    with sftph.get_client_sftp(cred):
        pass
    policy_arg = ssh.set_missing_host_key_policy.call_args.args[0]
    assert isinstance(policy_arg, paramiko.RejectPolicy)


def test_get_client_sftp_loads_system_host_keys(mock_ssh, cred):
    _, ssh, _ = mock_ssh
    with sftph.get_client_sftp(cred):
        pass
    ssh.load_system_host_keys.assert_called_once()


def test_get_client_sftp_loads_extra_known_hosts(mock_ssh, cred, tmp_path):
    extra = tmp_path / "known_hosts"
    extra.write_text("")
    cred["sftp_known_hosts"] = str(extra)
    _, ssh, _ = mock_ssh
    with sftph.get_client_sftp(cred):
        pass
    ssh.load_host_keys.assert_called_once_with(str(extra))


def test_get_client_sftp_connection_failure_raises_clean_exception(mock_ssh, cred):
    _, ssh, _ = mock_ssh
    ssh.connect.side_effect = paramiko.SSHException("boom")
    with pytest.raises(Exception) as excinfo, sftph.get_client_sftp(cred):
        pass
    # The previous pysftp-era f-string crashed with NameError; verify we surface
    # the real failure with the host info embedded in the message.
    assert "NameError" not in str(excinfo.value)
    assert cred["sftp_host"] in str(excinfo.value)
    assert "boom" in str(excinfo.value)
    ssh.close.assert_called()


def test_get_client_sftp_closes_on_normal_exit(mock_ssh, cred):
    sftp, ssh, _ = mock_ssh
    with sftph.get_client_sftp(cred):
        pass
    sftp.close.assert_called_once()
    ssh.close.assert_called_once()


# ---------------------------------------------------------------------------
# File ops
# ---------------------------------------------------------------------------


def test_upload_puts_then_overwrites(mock_ssh, cred, tmp_path):
    sftp, _, _ = mock_ssh
    local = tmp_path / "hello.txt"
    local.write_text("hi")
    target = f"{cred['sftp_destination_path']}/hello.txt"
    # File exists pre-upload (forces a remove), and after upload.
    _exists_map(sftp, {"/var/www/uploads/hello.txt": "file"})

    result = sftph.upload(str(local), cred, target)

    assert result == target
    sftp.remove.assert_called_once_with("/var/www/uploads/hello.txt")
    # A progress callback is now threaded through for the transfer bar.
    sftp.put.assert_called_once_with(
        str(local), "/var/www/uploads/hello.txt", callback=ANY, confirm=True
    )
    sftp.utime.assert_called_once()


def test_upload_skips_remove_when_target_absent(mock_ssh, cred, tmp_path):
    sftp, _, _ = mock_ssh
    local = tmp_path / "fresh.txt"
    local.write_text("hi")
    target = f"{cred['sftp_destination_path']}/fresh.txt"
    # First stat: missing. Second stat (post-put assertion): present.
    file_mode = stat_mod.S_IFREG | 0o644
    st = MagicMock(st_mode=file_mode, st_atime=0, st_mtime=0)
    sftp.stat.side_effect = [FileNotFoundError(), st]

    sftph.upload(str(local), cred, target)

    sftp.remove.assert_not_called()
    sftp.put.assert_called_once()


def test_download_calls_get_and_preserves_mtime(mock_ssh, cred, tmp_path, monkeypatch):
    sftp, _, _ = mock_ssh
    local = tmp_path / "out.txt"

    # download() now stats first (for the bar total + mtime), then sftp.get()
    # with a progress callback, then os.utime(). Have sftp.get materialize the
    # local file so checkfile succeeds; accept the callback kwarg paramiko gets.
    def fake_get(remote, local_path, callback=None):
        open(local_path, "w").close()

    sftp.get.side_effect = fake_get
    file_mode = stat_mod.S_IFREG | 0o644
    sftp.stat.return_value = MagicMock(
        st_mode=file_mode, st_size=0, st_atime=10, st_mtime=20
    )

    captured = {}
    real_utime = os.utime

    def fake_utime(path, times):
        captured["path"] = str(path)
        captured["times"] = times
        real_utime(path, times)

    monkeypatch.setattr(sftph_main.os, "utime", fake_utime)

    sftph.download(f"sftp://{cred['sftp_host']}/folder/out.txt", cred, str(local))

    sftp.get.assert_called_once_with("/folder/out.txt", str(local), callback=ANY)
    assert captured["times"] == (10, 20)


def test_delete_skips_when_remote_absent(mock_ssh, cred):
    sftp, _, _ = mock_ssh
    _exists_map(sftp, {})
    assert sftph.delete(f"sftp://{cred['sftp_host']}/folder/x.txt", cred) is True
    sftp.remove.assert_not_called()


def test_delete_removes_existing(mock_ssh, cred):
    sftp, _, _ = mock_ssh
    # First stat: present (exists check). Second stat: missing (post-remove check).
    file_mode = stat_mod.S_IFREG | 0o644
    st = MagicMock(st_mode=file_mode, st_atime=0, st_mtime=0)
    sftp.stat.side_effect = [st, FileNotFoundError()]

    assert sftph.delete(f"sftp://{cred['sftp_host']}/folder/x.txt", cred) is True
    sftp.remove.assert_called_once_with("/folder/x.txt")


def test_remote_file_exists_true(mock_ssh, cred):
    sftp, _, _ = mock_ssh
    _exists_map(sftp, {"/folder/x.txt": "file"})
    assert sftph.remote_file_exists(f"sftp://{cred['sftp_host']}/folder/x.txt", cred) is True


def test_remote_file_exists_false(mock_ssh, cred):
    sftp, _, _ = mock_ssh
    _exists_map(sftp, {})
    assert sftph.remote_file_exists(f"sftp://{cred['sftp_host']}/folder/x.txt", cred) is False


def test_remote_dir_exist_true(mock_ssh, cred):
    sftp, _, _ = mock_ssh
    _exists_map(sftp, {"/srv/uploads": "dir"})
    assert sftph.remote_dir_exist("/srv/uploads", cred) is True


def test_remote_dir_exist_false_when_file(mock_ssh, cred):
    sftp, _, _ = mock_ssh
    _exists_map(sftp, {"/srv/uploads": "file"})
    assert sftph.remote_dir_exist("/srv/uploads", cred) is False


def test_make_remote_directory_creates_nested(mock_ssh, cred):
    sftp, _, _ = mock_ssh
    created = set()

    def stat(path):
        if path in created:
            return MagicMock(st_mode=stat_mod.S_IFDIR | 0o755)
        raise FileNotFoundError(path)

    def mkdir(path):
        created.add(path)

    sftp.stat.side_effect = stat
    sftp.mkdir.side_effect = mkdir

    sftph.make_remote_directory("/a/b/c", cred)

    assert [c.args[0] for c in sftp.mkdir.call_args_list] == ["/a", "/a/b", "/a/b/c"]


def test_make_remote_directory_noop_when_exists(mock_ssh, cred):
    sftp, _, _ = mock_ssh
    _exists_map(sftp, {"/a/b/c": "dir"})
    sftph.make_remote_directory("/a/b/c", cred)
    sftp.mkdir.assert_not_called()


# ---------------------------------------------------------------------------
# remote_tempfile
# ---------------------------------------------------------------------------


def test_remote_tempfile_cleanup_on_success(mock_ssh, cred):
    sftp, _, _ = mock_ssh
    # Inside the with-block we pretend the user uploaded the file.
    state = {"present": False}
    file_mode = stat_mod.S_IFREG | 0o644

    def stat(path):
        if state["present"]:
            return MagicMock(st_mode=file_mode, st_atime=0, st_mtime=0)
        raise FileNotFoundError(path)

    sftp.stat.side_effect = stat

    with sftph.remote_tempfile(cred, ext="txt") as (addr, url):
        assert addr.startswith(cred["sftp_destination_path"] + "/")
        assert addr.endswith(".txt")
        assert url.startswith(cred["sftp_https"] + "/")
        state["present"] = True
        state["present"] = (
            False  # simulate the caller's delete; tempfile cleanup must still be a safe no-op
        )

    # On exit, tempfile calls delete(); since file is "absent" by now, no remove() call expected.
    sftp.remove.assert_not_called()


def test_remote_tempfile_deletes_existing_on_exit(mock_ssh, cred):
    sftp, _, _ = mock_ssh
    file_mode = stat_mod.S_IFREG | 0o644
    # First exists check (inside delete()): present. Second exists check (post-remove): missing.
    sftp.stat.side_effect = [
        MagicMock(st_mode=file_mode, st_atime=0, st_mtime=0),
        FileNotFoundError(),
    ]

    with sftph.remote_tempfile(cred) as (addr, _):
        pass

    sftp.remove.assert_called_once()


def test_remote_tempfile_preserves_original_exception(mock_ssh, cred):
    sftp, _, _ = mock_ssh
    # Make cleanup itself blow up; the user's exception must still win.
    sftp.stat.side_effect = paramiko.SSHException("cleanup-stat-failure")

    class UserError(RuntimeError):
        pass

    with pytest.raises(UserError), sftph.remote_tempfile(cred) as (_, _):
        raise UserError("the real problem")


def test_remote_tempfile_includes_subdir(mock_ssh, cred):
    sftp, _, _ = mock_ssh
    # subdir triggers make_remote_directory; track mkdir calls so subsequent
    # stat() lookups can report those paths as existing dirs.
    created_dirs = set()

    def stat(path):
        if path in created_dirs:
            return MagicMock(st_mode=stat_mod.S_IFDIR | 0o755)
        raise FileNotFoundError(path)

    sftp.stat.side_effect = stat
    sftp.mkdir.side_effect = lambda p: created_dirs.add(p)

    with sftph.remote_tempfile(cred, subdir="batch-42") as (addr, url):
        assert "/batch-42/" in addr
        assert "/batch-42/" in url
