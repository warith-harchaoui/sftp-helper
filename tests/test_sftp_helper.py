"""Tests for sftp_helper.

The module now drives the system OpenSSH ``sftp`` client through
``os_helper.system``. Instead of a live server, we monkeypatch
``os_helper.system`` with a fake that records the command line and the ``sftp``
batch file it would have run, and returns a programmable ``{"out", "err"}``
result. ``shutil.which`` is patched too so the tests are hermetic regardless of
whether ``sftp`` / ``sshpass`` are installed on the machine running them.
"""

import json
import os
import shlex
from types import SimpleNamespace

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

# A full config (every key). host/login/https are required; the rest optional.
CRED_KEYS = {
    "sftp_host": "sftp.example.com",
    "sftp_login": "alice",
    "sftp_https": "https://example.com/uploads",
    "sftp_key": "~/.ssh/id_ed25519",
    "sftp_destination_path": "/var/www/uploads",
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
    # Point at a directory that contains no config so the loader falls back to
    # env; optional keys must be backfilled from the environment too.
    cred = sftph.credentials(str(tmp_path))
    for k, v in CRED_KEYS.items():
        assert cred[k] == v


def test_credentials_missing_required_key_raises(tmp_path):
    """Dropping a *required* key (https) makes the loader raise."""
    incomplete = {k: v for k, v in CRED_KEYS.items() if k != "sftp_https"}
    cfg = tmp_path / "sftp_config.json"
    cfg.write_text(json.dumps(incomplete))
    with pytest.raises(RuntimeError):
        sftph.credentials(str(cfg))


def test_credentials_password_is_optional(tmp_path):
    """A key-based config with no password loads fine (passwd is optional now)."""
    minimal = {
        "sftp_host": "sftp.example.com",
        "sftp_login": "alice",
        "sftp_https": "https://example.com/uploads",
    }
    cfg = tmp_path / "sftp_config.json"
    cfg.write_text(json.dumps(minimal))
    cred = sftph.credentials(str(cfg))
    assert cred["sftp_login"] == "alice"
    assert "sftp_passwd" not in cred or sftph_main.osh.emptystring(cred.get("sftp_passwd"))


def test_credentials_destination_defaults_to_root(tmp_path):
    """An absent/empty destination path resolves to the server root."""
    cfg = tmp_path / "sftp_config.json"
    cfg.write_text(
        json.dumps(
            {
                "sftp_host": "sftp.example.com",
                "sftp_login": "alice",
                "sftp_https": "https://example.com/uploads",
            }
        )
    )
    cred = sftph.credentials(str(cfg))
    assert cred["sftp_destination_path"] == "/"


# ---------------------------------------------------------------------------
# Fake ``sftp`` backend
# ---------------------------------------------------------------------------


@pytest.fixture
def sftp(monkeypatch):
    """Patch ``_system`` + ``shutil.which`` and record what would have run.

    ``_system`` is the direct-subprocess runner; the fake returns
    ``(returncode, stdout, stderr)`` so tests exercise the same exit-code-based
    logic the real code uses.

    Returns a handle with:
      * ``.calls`` — one SimpleNamespace per invocation (``argv``, ``batch``,
        ``sshpass`` env passed to the call).
      * ``.push(code=..., out=..., err=...)`` — queue a result for the next
        call. A queued ``err`` with no explicit ``code`` defaults to a non-zero
        exit (so "not found" / connection errors read as failures); calls past
        the queue get a clean success ``(0, "", "")``.
      * ``.enable_sshpass()`` / ``.hide_sftp()`` — toggle binary availability.
    """
    calls = []
    results = []
    which = {"sftp": "/usr/bin/sftp", "sshpass": None}

    def fake_system(argv, env):
        batch = None
        if "-b" in argv:
            batch_path = argv[argv.index("-b") + 1]
            with open(batch_path) as fh:
                batch = fh.read()
            # Emulate ``get`` materializing the local file so downstream
            # ``osh.checkfile`` succeeds, exactly as a real transfer would.
            for line in batch.splitlines():
                if line.startswith("get"):
                    local = shlex.split(line)[-1]
                    open(local, "w").close()
        calls.append(SimpleNamespace(argv=argv, batch=batch, sshpass=env.get("SSHPASS")))
        res = results.pop(0) if results else {}
        code = res.get("code", 1 if res.get("err") else 0)
        return code, res.get("out", ""), res.get("err", "")

    def fake_which(name):
        return which.get(name)

    monkeypatch.setattr(sftph_main, "_system", fake_system)
    monkeypatch.setattr(sftph_main.shutil, "which", fake_which)

    return SimpleNamespace(
        calls=calls,
        push=lambda **kw: results.append(kw),
        enable_sshpass=lambda: which.__setitem__("sshpass", "/usr/bin/sshpass"),
        hide_sftp=lambda: which.__setitem__("sftp", None),
    )


@pytest.fixture
def cred():
    return {
        "sftp_host": "sftp.example.com",
        "sftp_login": "alice",
        "sftp_https": "https://example.com/uploads",
        "sftp_destination_path": "/var/www/uploads",
        "sftp_key": "~/.ssh/id_ed25519",
        "sftp_port": "22",
    }


# ---------------------------------------------------------------------------
# Command construction (auth, host-key policy, port, key)
# ---------------------------------------------------------------------------


def test_command_uses_key_and_strict_host_checking(sftp, cred):
    sftph.remote_file_exists("/folder/x.txt", cred)
    argv = sftp.calls[0].argv
    assert argv[0] == "sftp"
    assert "-i" in argv and argv[argv.index("-i") + 1] == os.path.expanduser("~/.ssh/id_ed25519")
    assert "-P" in argv and argv[argv.index("-P") + 1] == "22"
    assert "BatchMode=yes" in argv
    assert "StrictHostKeyChecking=yes" in argv
    assert f"{cred['sftp_login']}@{cred['sftp_host']}" in argv
    assert "sshpass" not in argv


def test_custom_port_is_passed(sftp, cred):
    cred["sftp_port"] = "2022"
    sftph.remote_file_exists("/folder/x.txt", cred)
    argv = sftp.calls[0].argv
    assert argv[argv.index("-P") + 1] == "2022"


def test_no_key_omits_identity_flag(sftp, cred):
    cred.pop("sftp_key")
    sftph.remote_file_exists("/folder/x.txt", cred)
    assert "-i" not in sftp.calls[0].argv


def test_extra_known_hosts_added(sftp, cred, tmp_path):
    extra = tmp_path / "known_hosts"
    extra.write_text("")
    cred["sftp_known_hosts"] = str(extra)
    sftph.remote_file_exists("/folder/x.txt", cred)
    argv = sftp.calls[0].argv
    ukh = [a for a in argv if a.startswith("UserKnownHostsFile=")]
    assert ukh and str(extra) in ukh[0]


def test_password_without_sshpass_raises(sftp, cred):
    cred["sftp_passwd"] = "secret"
    # sshpass is unavailable by default in the fixture.
    with pytest.raises(Exception, match="sshpass"):
        sftph.remote_file_exists("/folder/x.txt", cred)


def test_password_with_sshpass_uses_it(sftp, cred):
    cred["sftp_passwd"] = "secret"
    sftp.enable_sshpass()
    sftph.remote_file_exists("/folder/x.txt", cred)
    call = sftp.calls[0]
    assert call.argv[0] == "sshpass"
    assert "-e" in call.argv
    assert "BatchMode=no" in call.argv
    # The password is passed via the environment (SSHPASS), never in the argv.
    assert call.sshpass == "secret"
    assert "secret" not in " ".join(call.argv)
    assert os.environ.get("SSHPASS") is None


def test_missing_sftp_binary_raises(sftp, cred):
    sftp.hide_sftp()
    with pytest.raises(Exception, match="sftp"):
        sftph.remote_file_exists("/folder/x.txt", cred)


# ---------------------------------------------------------------------------
# Existence / directory probes
# ---------------------------------------------------------------------------


def test_remote_file_exists_true(sftp, cred):
    assert sftph.remote_file_exists("/folder/x.txt", cred) is True
    assert 'ls "/folder/x.txt"' in sftp.calls[0].batch


def test_remote_file_exists_false(sftp, cred):
    sftp.push(err="Can't ls: /folder/x.txt: No such file or directory")
    assert sftph.remote_file_exists("/folder/x.txt", cred) is False


def test_remote_file_exists_connection_error_raises(sftp, cred):
    sftp.push(err="alice@sftp.example.com: Permission denied (publickey).")
    with pytest.raises(Exception, match="Permission denied|reach"):
        sftph.remote_file_exists("/folder/x.txt", cred)


def test_remote_dir_exist_true(sftp, cred):
    assert sftph.remote_dir_exist("/srv/uploads", cred) is True
    assert 'cd "/srv/uploads"' in sftp.calls[0].batch


def test_remote_dir_exist_false_when_file(sftp, cred):
    sftp.push(err="Couldn't canonicalize: Not a directory")
    assert sftph.remote_dir_exist("/srv/uploads", cred) is False


# ---------------------------------------------------------------------------
# mkdir -p
# ---------------------------------------------------------------------------


def test_make_remote_directory_creates_nested(sftp, cred):
    # First cd (isdir probe) says "missing", then the mkdir batch, then a final
    # cd confirming the target now exists.
    sftp.push(err="Couldn't stat remote file: No such file or directory")  # initial isdir -> False
    sftp.push()  # the -mkdir batch succeeds
    sftp.push()  # final isdir verify -> True
    sftph.make_remote_directory("/a/b/c", cred)
    mkdir_batch = sftp.calls[1].batch
    assert '-mkdir "/a"' in mkdir_batch
    assert '-mkdir "/a/b"' in mkdir_batch
    assert '-mkdir "/a/b/c"' in mkdir_batch


def test_make_remote_directory_noop_when_exists(sftp, cred):
    # The very first isdir probe succeeds -> no mkdir batch is ever run.
    sftph.make_remote_directory("/a/b/c", cred)
    assert len(sftp.calls) == 1
    assert sftp.calls[0].batch.startswith('cd "/a/b/c"')


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def test_delete_removes_existing(sftp, cred):
    assert sftph.delete("sftp://sftp.example.com/folder/x.txt", cred) is True
    assert 'rm "/folder/x.txt"' in sftp.calls[0].batch


def test_delete_idempotent_when_absent(sftp, cred):
    sftp.push(err="Couldn't delete file: No such file or directory")
    assert sftph.delete("/folder/x.txt", cred) is True


# ---------------------------------------------------------------------------
# upload / download
# ---------------------------------------------------------------------------


def test_upload_creates_parent_then_puts(sftp, cred, tmp_path):
    local = tmp_path / "report.pdf"
    local.write_text("hi")
    # calls: [0] isdir("/inbox") -> exists (default success), [1] put
    result = sftph.upload(str(local), cred, "/inbox/report.pdf")
    assert result == "/inbox/report.pdf"
    put_batch = sftp.calls[-1].batch
    assert f'put -p "{local}" "/inbox/report.pdf"' in put_batch


def test_upload_hashed_name_when_no_address(sftp, cred, tmp_path):
    local = tmp_path / "clip.bin"
    local.write_text("payload")
    result = sftph.upload(str(local), cred)
    assert result.startswith("/var/www/uploads/")
    assert result.endswith(".bin")


def test_upload_failure_raises(sftp, cred, tmp_path):
    local = tmp_path / "report.pdf"
    local.write_text("hi")
    sftp.push()  # parent isdir -> exists
    sftp.push(err="remote open failed: Permission denied")  # put fails (file perms)
    with pytest.raises(Exception, match="Upload failed"):
        sftph.upload(str(local), cred, "/inbox/report.pdf")


def test_download_calls_get(sftp, cred, tmp_path):
    local = tmp_path / "out.txt"
    sftph.download("sftp://sftp.example.com/folder/out.txt", cred, str(local))
    get_batch = sftp.calls[0].batch
    assert f'get -p "/folder/out.txt" "{local}"' in get_batch
    assert local.exists()


def test_download_default_local_name(sftp, cred, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = sftph.download("sftp://sftp.example.com/folder/out.txt", cred)
    assert out == "out.txt"
    assert (tmp_path / "out.txt").exists()


# ---------------------------------------------------------------------------
# Progress-bar transfer path (scp under a pseudo-terminal)
# ---------------------------------------------------------------------------


def test_can_progress_false_off_tty(sftp, cred):
    # The fixture's fake ``which`` has no scp, and pytest's stderr is not a TTY,
    # so transfers take the plain sftp path — which is what all the upload /
    # download tests above rely on.
    assert sftph_main._can_progress(cred) is False


def test_scp_argv_builds_expected_transfer(cred):
    argv, _env = sftph_main._scp_argv(cred, "local.txt", "alice@host:/remote.txt")
    assert argv[0] == "scp"
    assert "-p" in argv  # preserve times
    assert "StrictHostKeyChecking=yes" in argv
    assert argv[-2:] == ["local.txt", "alice@host:/remote.txt"]


def test_scp_pty_runs_and_captures(tmp_path):
    # Drive the pty runner with a stand-in that emits a percentage meter, to
    # exercise the read loop + percent parsing + success return without scp.
    rc, out = sftph_main._scp_pty(
        ["sh", "-c", "printf '25%%\\n100%%\\n'; exit 0"], {}, total=1000, desc="x"
    )
    assert rc == 0
    assert "25%" in out


def test_scp_pty_reports_failure(tmp_path):
    rc, out = sftph_main._scp_pty(["sh", "-c", "echo boom 1>&2; exit 3"], {}, total=None, desc="x")
    assert rc == 3
    assert "boom" in out


def test_send_uses_scp_when_progress_available(sftp, cred, tmp_path, monkeypatch):
    # Force the progress path and capture the scp argv it would run.
    local = tmp_path / "clip.mp4"
    local.write_text("data")
    monkeypatch.setattr(sftph_main, "_can_progress", lambda _c: True)
    seen = {}

    def fake_pty(argv, env, total, desc):
        seen["argv"] = argv
        seen["total"] = total
        return 0, ""

    monkeypatch.setattr(sftph_main, "_scp_pty", fake_pty)
    sftph_main._send(cred, str(local), "/inbox/clip.mp4", upload=True, desc="clip.mp4")
    assert seen["argv"][0] == "scp"
    assert seen["argv"][-1] == "alice@sftp.example.com:/inbox/clip.mp4"
    assert seen["total"] == local.stat().st_size  # byte-accurate bar total


def test_send_progress_failure_raises(sftp, cred, tmp_path, monkeypatch):
    local = tmp_path / "clip.mp4"
    local.write_text("data")
    monkeypatch.setattr(sftph_main, "_can_progress", lambda _c: True)
    monkeypatch.setattr(
        sftph_main, "_scp_pty", lambda *a, **k: (1, "scp: /inbox: Permission denied")
    )
    with pytest.raises(Exception, match="Permission denied"):
        sftph_main._send(cred, str(local), "/inbox/clip.mp4", upload=True, desc="clip.mp4")


# ---------------------------------------------------------------------------
# remote_tempfile
# ---------------------------------------------------------------------------


def test_remote_tempfile_cleanup_on_success(sftp, cred):
    with sftph.remote_tempfile(cred, ext="txt") as (addr, url):
        assert addr.startswith(cred["sftp_destination_path"] + "/")
        assert addr.endswith(".txt")
        assert url.startswith(cred["sftp_https"] + "/")
    # On exit, a delete (rm) is issued for the reserved path.
    assert any(c.batch and c.batch.startswith("rm ") for c in sftp.calls)


def test_remote_tempfile_includes_subdir(sftp, cred):
    with sftph.remote_tempfile(cred, subdir="batch-42") as (addr, url):
        assert "/batch-42/" in addr
        assert "/batch-42/" in url


def test_remote_tempfile_preserves_original_exception(sftp, cred):
    class UserError(RuntimeError):
        pass

    # Make the cleanup delete fail; the user's exception must still win.
    def boom(*_a, **_k):
        raise RuntimeError("cleanup blew up")

    # Patch delete only for this test so the finally-branch cleanup raises.
    import sftp_helper.main as m

    original_delete = m.delete
    m.delete = boom
    try:
        with pytest.raises(UserError), sftph.remote_tempfile(cred) as (_addr, _url):
            raise UserError("the real problem")
    finally:
        m.delete = original_delete
