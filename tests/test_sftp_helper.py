"""Tests for sftp_helper.

The module now drives the system OpenSSH ``sftp`` client through
``os_helper.system``. Instead of a live server, we monkeypatch
``os_helper.system`` with a fake that records the command line and the ``sftp``
batch file it would have run, and returns a programmable ``{"out", "err"}``
result. ``shutil.which`` is patched too so the tests are hermetic regardless of
whether ``sftp`` / ``sshpass`` are installed on the machine running them.

Related scenarios are grouped into one test function per behaviour (rather
than one test per input) so a single read shows the whole picture and a
single failure still pinpoints the exact case via its assertion message or
its position in the function.
"""

import json
import os
import shlex
import zipfile
from types import SimpleNamespace

import pytest
import yaml

import sftp_helper as sftph
from sftp_helper import main as sftph_main

# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def test_normalize_path():
    cases = {
        "foo/bar": "/foo/bar",
        "/foo/bar": "/foo/bar",
        "/foo/bar/": "/foo/bar",
        "/foo/bar///": "/foo/bar",
        "/": "/",
        "": "/",
    }
    for raw, expected in cases.items():
        assert sftph.normalize_path(raw) == expected, raw


def test_normalize_path_rejects_unsafe_characters():
    # Every remote-path funnel (normalize_path, and strip_sftp_path which
    # calls it) must reject characters that could break out of an sftp -b
    # batch command's quoting: a bare '"' breaks the quoted argument, '\n'/
    # '\r' inject an extra batch-file line (including OpenSSH sftp's local
    # shell escape, "!command"), and '\x00' can't occur in a real path.
    for unsafe in ('/foo"bar', "/foo\nbar", "/foo\rbar", "/foo\x00bar"):
        with pytest.raises(ValueError):
            sftph.normalize_path(unsafe)
    cred = {"sftp_host": "example.com"}
    with pytest.raises(ValueError):
        sftph.strip_sftp_path("sftp://example.com/foo\nbar", cred)


def test_strip_sftp_path():
    cred = {"sftp_host": "example.com"}
    assert sftph.strip_sftp_path("sftp://example.com/folder/file.txt", cred) == "/folder/file.txt"
    assert sftph.strip_sftp_path("example.com/folder/file.txt", cred) == "/folder/file.txt"
    # Idempotent: re-stripping an already-stripped path changes nothing.
    once = sftph.strip_sftp_path("/folder/file.txt", cred)
    twice = sftph.strip_sftp_path(once, cred)
    assert once == twice == "/folder/file.txt"


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


def test_credentials_from_file(tmp_path):
    for fmt, dump in (
        ("json", lambda p: p.write_text(json.dumps(CRED_KEYS))),
        ("yaml", lambda p: p.write_text(yaml.safe_dump(CRED_KEYS))),
    ):
        cfg = tmp_path / f"settings.{fmt}"
        dump(cfg)
        cred = sftph.credentials(str(cfg))
        for k, v in CRED_KEYS.items():
            assert cred[k] == v, f"{fmt}:{k}"


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
    cfg = tmp_path / "settings.json"
    cfg.write_text(json.dumps(incomplete))
    with pytest.raises(RuntimeError):
        sftph.credentials(str(cfg))


def test_credentials_minimal_config_defaults(tmp_path):
    """No password, no destination path: both fall back to documented defaults."""
    minimal = {
        "sftp_host": "sftp.example.com",
        "sftp_login": "alice",
        "sftp_https": "https://example.com/uploads",
    }
    cfg = tmp_path / "settings.json"
    cfg.write_text(json.dumps(minimal))
    cred = sftph.credentials(str(cfg))
    assert cred["sftp_login"] == "alice"
    assert "sftp_passwd" not in cred or sftph_main.osh.emptystring(cred.get("sftp_passwd"))
    assert cred["sftp_destination_path"] == "/"  # empty/absent -> server root


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
            # Emulate ``get``/``reget`` materializing the local (part) file so
            # downstream checks succeed, exactly as a real transfer would.
            for line in batch.splitlines():
                cmd = line.lstrip("-").split(maxsplit=1)[0] if line.lstrip("-") else ""
                if cmd in ("get", "reget"):
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
    # Retry backoff (`_upload_resumable` / `_download_resumable`) is real
    # `time.sleep` in production; tests exercise the retry loop without
    # actually waiting.
    monkeypatch.setattr(sftph_main.time, "sleep", lambda _seconds: None)

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
# Command construction (auth, host-key policy, port, key, sshpass, binary)
# ---------------------------------------------------------------------------


def test_command_reflects_credentials(sftp, cred, tmp_path):
    """argv construction across the cred fields that shape it, one call each."""
    sftph.remote_file_exists("/folder/x.txt", cred)
    argv = sftp.calls[0].argv
    assert argv[0] == "sftp"
    assert "-i" in argv and argv[argv.index("-i") + 1] == os.path.expanduser("~/.ssh/id_ed25519")
    assert "-P" in argv and argv[argv.index("-P") + 1] == "22"
    assert "BatchMode=yes" in argv
    assert "StrictHostKeyChecking=yes" in argv
    assert f"{cred['sftp_login']}@{cred['sftp_host']}" in argv
    assert "sshpass" not in argv

    cred["sftp_port"] = "2022"
    sftph.remote_file_exists("/folder/x.txt", cred)
    assert sftp.calls[-1].argv[sftp.calls[-1].argv.index("-P") + 1] == "2022"

    cred.pop("sftp_key")
    sftph.remote_file_exists("/folder/x.txt", cred)
    assert "-i" not in sftp.calls[-1].argv

    extra = tmp_path / "known_hosts"
    extra.write_text("")
    cred["sftp_known_hosts"] = str(extra)
    sftph.remote_file_exists("/folder/x.txt", cred)
    ukh = [a for a in sftp.calls[-1].argv if a.startswith("UserKnownHostsFile=")]
    assert ukh and str(extra) in ukh[0]


def test_password_without_sshpass_raises_with_os_specific_hint(sftp, cred, monkeypatch):
    cred["sftp_passwd"] = "secret"
    # sshpass is unavailable by default in the fixture; the base message
    # always names it, so `match="sshpass"` holds regardless of platform —
    # the (None) case exercises the real, un-mocked test-runner platform.
    for system, expected in [
        (None, "sshpass"),
        ("Darwin", "macOS:"),
        ("Linux", "Linux:"),
        ("Windows", "Windows:"),
        ("FreeBSD", "Install 'sshpass'"),  # unrecognized platform -> generic fallback
    ]:
        if system is not None:
            monkeypatch.setattr(sftph_main.platform, "system", lambda system=system: system)
        with pytest.raises(Exception, match=expected):
            sftph.remote_file_exists("/folder/x.txt", cred)


def test_missing_sftp_binary_raises_with_os_specific_hint(sftp, cred, monkeypatch):
    sftp.hide_sftp()
    with pytest.raises(Exception, match="sftp"):
        sftph.remote_file_exists("/folder/x.txt", cred)  # real test-runner platform

    monkeypatch.setattr(sftph_main.platform, "system", lambda: "Windows")
    with pytest.raises(Exception, match="OpenSSH Client"):
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


# ---------------------------------------------------------------------------
# Existence / directory probes
# ---------------------------------------------------------------------------


def test_remote_file_exists(sftp, cred):
    assert sftph.remote_file_exists("/folder/x.txt", cred) is True
    assert 'ls "/folder/x.txt"' in sftp.calls[0].batch

    sftp.push(err="Can't ls: /folder/x.txt: No such file or directory")
    assert sftph.remote_file_exists("/folder/x.txt", cred) is False


def test_remote_file_exists_connection_error_raises(sftp, cred):
    sftp.push(err="alice@sftp.example.com: Permission denied (publickey).")
    with pytest.raises(Exception, match="Permission denied|reach"):
        sftph.remote_file_exists("/folder/x.txt", cred)


def test_remote_dir_exist(sftp, cred):
    assert sftph.remote_dir_exist("/srv/uploads", cred) is True
    assert 'cd "/srv/uploads"' in sftp.calls[0].batch

    sftp.push(err="Couldn't canonicalize: Not a directory")
    assert sftph.remote_dir_exist("/srv/uploads", cred) is False


# ---------------------------------------------------------------------------
# list_dir
# ---------------------------------------------------------------------------


def test_list_dir_flat(sftp, cred):
    sftp.push(out="a.txt\nb.txt\nsub\n")
    entries = sftph.list_dir("/srv/uploads", cred)
    assert entries == ["a.txt", "b.txt", "sub"]
    assert 'ls -1 "/srv/uploads"' in sftp.calls[0].batch

    sftp.push(out="")
    assert sftph.list_dir("/srv/uploads", cred) == []


def test_list_dir_missing_raises(sftp, cred):
    sftp.push(err="Can't ls: /srv/missing: No such file or directory")
    with pytest.raises(Exception, match="No such remote directory"):
        sftph.list_dir("/srv/missing", cred)


def test_list_dir_recursive(sftp, cred):
    # No native recursive `ls` in OpenSSH sftp (its `-r` means reverse-sort,
    # not recurse), so list_dir emulates it: `ls -1` the top, then a `cd`
    # probe per entry to tell files from sub-directories, recursing into the
    # latter. Nested layout: /srv/uploads/{a.txt, sub/{b.txt}}.
    sftp.push(out="a.txt\nsub\n")                                  # ls -1 /srv/uploads
    sftp.push(err="Couldn't stat: No such file or directory")      # cd a.txt -> not a dir
    sftp.push()                                                     # cd sub -> is a dir
    sftp.push(out="b.txt\n")                                       # ls -1 /srv/uploads/sub
    sftp.push(err="Couldn't stat: No such file or directory")      # cd sub/b.txt -> not a dir
    assert sftph.list_dir("/srv/uploads", cred, recursive=True) == ["a.txt", "sub/b.txt"]

    # Flat layout: no sub-directories at all.
    sftp.push(out="a.txt\nb.txt\n")
    sftp.push(err="Couldn't stat: No such file or directory")
    sftp.push(err="Couldn't stat: No such file or directory")
    assert sftph.list_dir("/srv/uploads", cred, recursive=True) == ["a.txt", "b.txt"]


# ---------------------------------------------------------------------------
# _parse_ls_long_line
# ---------------------------------------------------------------------------


def test_parse_ls_long_line():
    from datetime import datetime as _dt

    now = _dt(2026, 8, 11, 15, 0)

    row = sftph_main._parse_ls_long_line(
        "-rw-r--r--    1 user     group      1234 Aug 10 10:30 readme.txt", now=now
    )
    assert row == {"name": "readme.txt", "is_dir": False, "size": 1234, "mtime": _dt(2026, 8, 10, 10, 30)}

    row = sftph_main._parse_ls_long_line(
        "-rw-r--r--    1 user     group      1234 Jan 15  2023 old.txt", now=now
    )
    assert row["mtime"] == _dt(2023, 1, 15, 0, 0), "an explicit year is read as-is, not inferred"

    row = sftph_main._parse_ls_long_line(
        "drwxr-xr-x    3 user     group       512 Aug  5 09:00 sub", now=now
    )
    assert row["is_dir"] is True

    row = sftph_main._parse_ls_long_line(
        "-rw-r--r--    1 user     group      1234 Aug 10 10:30 my file (final).txt", now=now
    )
    assert row["name"] == "my file (final).txt", "a filename containing spaces parses whole"

    row = sftph_main._parse_ls_long_line(
        "-rw-r--r--    1 user     group      1234 Dec 25 10:30 futuredate.txt", now=now
    )
    assert row["mtime"].year == 2025, "a 'recent' date >1 day in the future rolls back a year"

    assert sftph_main._parse_ls_long_line("total 42", now=now) is None
    assert sftph_main._parse_ls_long_line("", now=now) is None

    # Some servers echo the full listed-directory path in front of each
    # entry's name instead of a bare filename; "/" can't be part of a real
    # filename, so the last path component is always the true name.
    row = sftph_main._parse_ls_long_line(
        "drwxr-xr-x  1 u g  512 Aug 10 10:30 /lamp0/web/vhosts/example.com/htdocs/css", now=now
    )
    assert row["name"] == "css"


# ---------------------------------------------------------------------------
# remote_stat / list_dir_stat
# ---------------------------------------------------------------------------


def test_remote_stat(sftp, cred):
    sftp.push(out="-rw-r--r--  1 u g  1234 Aug 10 10:30 x.txt\n")
    result = sftph.remote_stat("/srv/uploads/x.txt", cred)
    assert result is not None
    assert result["size"] == 1234
    assert 'ls -l "/srv/uploads"' in sftp.calls[0].batch

    sftp.push(out="other.txt\n")  # parent listing exists, but not our file
    assert sftph.remote_stat("/srv/uploads/missing.txt", cred) is None


def test_list_dir_stat_recursive(sftp, cred):
    sftp.push(out="-rw-r--r--  1 u g  100 Aug 10 10:30 a.txt\ndrwxr-xr-x 2 u g 512 Aug 5 09:00 sub\n")
    sftp.push(out="-rw-r--r--  1 u g  200 Aug 9 08:00 b.txt\n")
    tree = sftph.list_dir_stat("/srv/uploads", cred)
    assert set(tree.keys()) == {"a.txt", "sub/b.txt"}
    assert tree["a.txt"]["size"] == 100
    assert tree["sub/b.txt"]["size"] == 200

    # Regression: a server that prints "/srv/uploads/sub" (not "sub") as the
    # directory entry's name must not get that full path re-appended onto
    # the next recursive `ls -l` call (the path-doubling bug this guards).
    sftp.push(out="drwxr-xr-x 2 u g 512 Aug 5 09:00 /srv/uploads/sub\n")
    sftp.push(out="-rw-r--r--  1 u g  200 Aug 9 08:00 /srv/uploads/sub/b.txt\n")
    tree = sftph.list_dir_stat("/srv/uploads", cred)
    assert set(tree.keys()) == {"sub/b.txt"}
    assert 'ls -l "/srv/uploads/sub"' in sftp.calls[-1].batch


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


def test_delete(sftp, cred):
    assert sftph.delete("sftp://sftp.example.com/folder/x.txt", cred) is True
    assert 'rm "/folder/x.txt"' in sftp.calls[0].batch

    sftp.push(err="Couldn't delete file: No such file or directory")
    assert sftph.delete("/folder/x.txt", cred) is True  # idempotent when already absent


# ---------------------------------------------------------------------------
# upload / download
# ---------------------------------------------------------------------------


# NOTE on the ``remote_stat`` stubs below: OpenSSH's ``reput``/``put -a`` only
# actually resumes — empirically (see ``_upload_resumable``'s docstring) it
# errors both on a wholly absent remote temp file and on one already the same
# size or larger. So each attempt stats the temp file *before* choosing a
# command: ``put`` when absent, ``reput`` only for a genuine smaller partial,
# and no transfer when already complete. Tests stub ``remote_stat`` with an
# explicit sequence matching exactly the calls that sequence of decisions
# makes: one "before" stat per attempt, one "after" verify per successful
# transfer, and one final stat verifying the atomic publish.


def test_upload_resumable_branches(sftp, cred, tmp_path, monkeypatch):
    """The four branches of _upload_resumable's before-check decision table."""

    def upload_and_new_calls(name, content, stats_seq):
        local = tmp_path / name
        local.write_text(content)
        stats = iter(stats_seq)
        monkeypatch.setattr(sftph_main, "remote_stat", lambda _p, _c: next(stats))
        before = len(sftp.calls)
        result = sftph.upload(str(local), cred, f"/inbox/{name}")
        assert result == f"/inbox/{name}"
        return sftp.calls[before:]

    size2 = len("hi")
    # before-check: absent -> plain put
    calls = upload_and_new_calls(
        "a.txt", "hi", [None, {"size": size2, "mtime": None}, {"size": size2, "mtime": None}]
    )
    put = next(c for c in calls if "put -p" in (c.batch or "") and "reput" not in (c.batch or ""))
    assert f'put -p "{tmp_path / "a.txt"}" "/inbox/a.txt.sftp-helper-upload"' in put.batch

    size10 = len("0123456789")
    # before-check: a genuine smaller partial (5/10 bytes) already exists -> reput
    calls = upload_and_new_calls(
        "b.txt",
        "0123456789",
        [{"size": 5, "mtime": None}, {"size": size10, "mtime": None}, {"size": size10, "mtime": None}],
    )
    reput = next(c for c in calls if "reput -p" in (c.batch or ""))
    assert f'reput -p "{tmp_path / "b.txt"}" "/inbox/b.txt.sftp-helper-upload"' in reput.batch

    # before-check: a stale leftover LARGER than the current source -> rm, then put
    calls = upload_and_new_calls(
        "c.txt",
        "0123456789",
        [
            {"size": size10 + 100, "mtime": None},
            {"size": size10, "mtime": None},
            {"size": size10, "mtime": None},
        ],
    )
    assert any(c.batch and c.batch.strip() == '-rm "/inbox/c.txt.sftp-helper-upload"' for c in calls)
    put = next(c for c in calls if "put -p" in (c.batch or "") and "reput" not in (c.batch or ""))
    assert f'put -p "{tmp_path / "c.txt"}" "/inbox/c.txt.sftp-helper-upload"' in put.batch

    # before-check: already fully there from a previous run -> no transfer at all
    calls = upload_and_new_calls(
        "d.txt", "0123456789", [{"size": size10, "mtime": None}, {"size": size10, "mtime": None}]
    )
    assert not any("put -p" in (c.batch or "") or "reput -p" in (c.batch or "") for c in calls)


def test_upload_hashed_name_when_no_address(sftp, cred, tmp_path, monkeypatch):
    local = tmp_path / "clip.bin"
    local.write_text("payload")
    size = local.stat().st_size
    stats = iter([None, {"size": size, "mtime": None}, {"size": size, "mtime": None}])
    monkeypatch.setattr(sftph_main, "remote_stat", lambda _path, _cred: next(stats))
    result = sftph.upload(str(local), cred)
    assert result.startswith("/var/www/uploads/")
    assert result.endswith(".bin")


def test_upload_failure_raises(sftp, cred, tmp_path):
    local = tmp_path / "report.pdf"
    local.write_text("hi")
    sftp.push()  # parent isdir -> exists
    sftp.push()  # before-check remote_stat(temp) -> empty output -> absent -> put
    sftp.push(err="remote open failed: Permission denied")  # put fails (file perms)
    # remaining attempts default to success, but with no matching remote_stat
    # queued, verification never confirms — every retry exhausts the same way.
    with pytest.raises(Exception, match="Upload failed"):
        sftph.upload(str(local), cred, "/inbox/report.pdf")


def test_upload_retries_then_exhausts(sftp, cred, tmp_path, monkeypatch):
    # A transient failure on attempt 1 is retried with a fresh put (nothing
    # was actually created remotely) and succeeds on attempt 2...
    local = tmp_path / "clip.bin"
    local.write_text("0123456789")
    size = local.stat().st_size
    stats = iter([None, None, {"size": size, "mtime": None}, {"size": size, "mtime": None}])
    monkeypatch.setattr(sftph_main, "remote_stat", lambda _path, _cred: next(stats))
    sftp.push()  # parent isdir -> exists
    sftp.push(err="Connection reset")  # first put attempt fails
    result = sftph.upload(str(local), cred, "/inbox/clip.bin")
    assert result == "/inbox/clip.bin"
    put_calls = [c for c in sftp.calls if "put -p" in (c.batch or "") and "reput" not in (c.batch or "")]
    assert len(put_calls) == 2

    # ...whereas a partial that NEVER completes exhausts every retry and raises.
    local2 = tmp_path / "clip2.bin"
    local2.write_text("0123456789")
    monkeypatch.setattr(sftph_main, "remote_stat", lambda _path, _cred: {"size": 1, "mtime": None})
    with pytest.raises(Exception, match=r"Upload failed after 2 attempt"):
        sftph.upload(str(local2), cred, "/inbox/clip2.bin", retries=1)


# ---------------------------------------------------------------------------
# upload() overwrite / resume / progress knobs
# ---------------------------------------------------------------------------


def test_upload_overwrite_false_behavior(sftp, cred, tmp_path, monkeypatch):
    # Auto-hashed address: mere presence is proof enough (see upload()'s
    # docstring) — no size comparison needed, any remote size still skips.
    local_a = tmp_path / "a.txt"
    local_a.write_text("A")
    monkeypatch.setattr(sftph_main, "remote_stat", lambda _p, _c: {"size": 12345, "mtime": None})
    out = sftph.upload(str(local_a), cred, overwrite=False)
    assert out.startswith("/var/www/uploads/")
    assert sftp.calls == []

    # Explicit address, remote size matches local -> skip.
    local_b = tmp_path / "b.txt"
    local_b.write_text("AB")
    monkeypatch.setattr(sftph_main, "remote_stat", lambda _p, _c: {"size": 2, "mtime": None})
    out = sftph.upload(str(local_b), cred, "/inbox/b.txt", overwrite=False)
    assert out == "/inbox/b.txt"
    assert sftp.calls == []

    # Explicit address, remote size differs -> re-uploads for real.
    local_c = tmp_path / "c.txt"
    local_c.write_text("AB")
    size = local_c.stat().st_size
    stats = iter(
        [{"size": 999, "mtime": None}, None, {"size": size, "mtime": None}, {"size": size, "mtime": None}]
    )
    monkeypatch.setattr(sftph_main, "remote_stat", lambda _p, _c: next(stats))
    out = sftph.upload(str(local_c), cred, "/inbox/c.txt", overwrite=False)
    assert out == "/inbox/c.txt"
    put_call = next(c for c in sftp.calls if "put -p" in (c.batch or "") and "reput" not in (c.batch or ""))
    assert f'put -p "{local_c}" "/inbox/c.txt.sftp-helper-upload"' in put_call.batch


def test_upload_resume_false_discards_stale_temp_first(sftp, cred, tmp_path, monkeypatch):
    local = tmp_path / "a.txt"
    local.write_text("AB")
    size = local.stat().st_size
    stats = iter([None, {"size": size, "mtime": None}, {"size": size, "mtime": None}])
    monkeypatch.setattr(sftph_main, "remote_stat", lambda _path, _cred: next(stats))
    sftph.upload(str(local), cred, "/inbox/a.txt", resume=False)
    batches = [c.batch or "" for c in sftp.calls]
    rm_idx = next(i for i, b in enumerate(batches) if b.strip() == '-rm "/inbox/a.txt.sftp-helper-upload"')
    put_idx = next(i for i, b in enumerate(batches) if "put -p" in b and "reput" not in b)
    assert rm_idx < put_idx


def test_upload_progress_false_forwarded_to_run_sftp_with_progress(sftp, cred, tmp_path, monkeypatch):
    local = tmp_path / "a.txt"
    local.write_text("AB")
    size = local.stat().st_size
    stats = iter([None, {"size": size, "mtime": None}, {"size": size, "mtime": None}])
    monkeypatch.setattr(sftph_main, "remote_stat", lambda _path, _cred: next(stats))
    seen = {}
    real = sftph_main._run_sftp_with_progress

    def spy(cred_, commands, *, total, probe, desc, progress=True):
        seen["progress"] = progress
        return real(cred_, commands, total=total, probe=probe, desc=desc, progress=progress)

    monkeypatch.setattr(sftph_main, "_run_sftp_with_progress", spy)
    sftph.upload(str(local), cred, "/inbox/a.txt", progress=False)
    assert seen["progress"] is False


# ---------------------------------------------------------------------------
# _probe_exec — detecting whether the server accepts arbitrary shell exec
# ---------------------------------------------------------------------------


def test_probe_exec_true_when_marker_echoed(sftp, cred):
    sftp.push(out=f"{sftph_main._EXEC_PROBE_MARKER}\n")
    assert sftph_main._probe_exec(cred) is True
    # Plain `ssh`, not the `sftp` subsystem, and no -b batch file.
    assert sftp.calls[0].argv[0] not in ("sftp",) or "ssh" in sftp.calls[0].argv
    assert sftp.calls[0].batch is None


def test_probe_exec_false_when_forced_command_rejects(sftp, cred):
    # The real-world case this guards against: connection succeeds (exit 0)
    # but a forced-command / restricted-shell account never actually runs
    # our command, so the marker never comes back.
    sftp.push(out="", err="fatal: bad argument\n")
    assert sftph_main._probe_exec(cred) is False


def test_probe_exec_false_on_exception(sftp, cred, monkeypatch):
    def boom(_argv, _env):
        raise Exception("connection refused")

    monkeypatch.setattr(sftph_main, "_system", boom)
    assert sftph_main._probe_exec(cred) is False


# ---------------------------------------------------------------------------
# upload_many — archive acceleration with per-file fallback
# ---------------------------------------------------------------------------


def test_upload_many_empty_list(cred):
    assert sftph.upload_many([], cred) == {}


def test_upload_many_dispatch(cred, monkeypatch):
    """Which path upload_many takes, across exec support, an explicit archive
    override, an archive failure, and overwrite=False."""
    files = [("a.txt", "/inbox/a.txt")]

    # exec available, no override -> archive path used, per-file never touched.
    monkeypatch.setattr(sftph_main, "_probe_exec", lambda _c: True)
    archive_calls = []
    monkeypatch.setattr(sftph_main, "_upload_many_archive", lambda fs, _c: archive_calls.append(fs) or {})
    monkeypatch.setattr(sftph_main, "upload", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no per-file")))
    sftph.upload_many(files, cred)
    assert archive_calls == [files]

    # no exec -> falls back to per-file, archive never called.
    monkeypatch.setattr(sftph_main, "_probe_exec", lambda _c: False)
    monkeypatch.setattr(
        sftph_main, "_upload_many_archive", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no archive"))
    )
    seen = []
    monkeypatch.setattr(sftph_main, "upload", lambda local, _c, addr, **k: seen.append((local, addr)) or addr)
    result = sftph.upload_many(files, cred)
    assert seen == [("a.txt", "/inbox/a.txt")]
    assert result == {"a.txt": "/inbox/a.txt"}

    # exec available but archive raises -> degrades to per-file.
    monkeypatch.setattr(sftph_main, "_probe_exec", lambda _c: True)
    monkeypatch.setattr(
        sftph_main, "_upload_many_archive", lambda *a, **k: (_ for _ in ()).throw(Exception("unzip: not found"))
    )
    seen.clear()
    result = sftph.upload_many(files, cred)
    assert seen == [("a.txt", "/inbox/a.txt")]
    assert result == {"a.txt": "/inbox/a.txt"}

    # archive=True forces the archive path without ever probing.
    monkeypatch.setattr(
        sftph_main, "_probe_exec", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no probe"))
    )
    archive_calls.clear()
    monkeypatch.setattr(sftph_main, "_upload_many_archive", lambda fs, _c: archive_calls.append(fs) or {})
    sftph.upload_many(files, cred, archive=True)
    assert archive_calls == [files]

    # archive=False forces per-file without ever probing.
    seen.clear()
    monkeypatch.setattr(sftph_main, "upload", lambda local, _c, addr, **k: seen.append((local, addr)) or addr)
    sftph.upload_many(files, cred, archive=False)
    assert seen == [("a.txt", "/inbox/a.txt")]

    # overwrite=False forces per-file even when archive=True is explicit.
    monkeypatch.setattr(
        sftph_main, "_upload_many_archive", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no archive"))
    )
    kwargs_seen = []
    monkeypatch.setattr(sftph_main, "upload", lambda local, _c, addr, **k: kwargs_seen.append(k) or addr)
    sftph.upload_many(files, cred, archive=True, overwrite=False)
    assert kwargs_seen == [{"retries": 3, "overwrite": False, "resume": True, "progress": True}]


# ---------------------------------------------------------------------------
# _upload_many_archive — zip -> put -> remote unzip
# ---------------------------------------------------------------------------


def test_upload_many_archive_zips_uploads_and_unzips(cred, tmp_path, monkeypatch):
    a = tmp_path / "a.txt"
    a.write_text("A")
    sub = tmp_path / "sub"
    sub.mkdir()
    b = sub / "b.txt"
    b.write_text("B")

    uploaded = {}

    def fake_upload(local_path, _cred, sftp_address, **_k):
        uploaded["local"] = local_path
        uploaded["remote"] = sftp_address
        # Verify the zip actually contains the right entries at the right arcnames.
        with zipfile.ZipFile(local_path) as zf:
            names = set(zf.namelist())
            assert names == {"a.txt", "sub/b.txt"}
            assert zf.read("a.txt") == b"A"
        return sftp_address

    exec_calls = []

    def fake_exec(_cred, command):
        exec_calls.append(command)
        return {"code": 0, "out": "", "err": ""}

    deleted = []
    monkeypatch.setattr(sftph_main, "upload", fake_upload)
    monkeypatch.setattr(sftph_main, "_run_ssh_exec", fake_exec)
    monkeypatch.setattr(sftph_main, "delete", lambda addr, _cred: deleted.append(addr))

    files = [(str(a), "/var/www/uploads/a.txt"), (str(b), "/var/www/uploads/sub/b.txt")]
    result = sftph_main._upload_many_archive(files, cred)

    assert result == {str(a): "/var/www/uploads/a.txt", str(b): "/var/www/uploads/sub/b.txt"}
    # The remote zip's path comes from remote_tempfile, not hand-rolled naming.
    assert uploaded["remote"].startswith("/var/www/uploads/")
    assert uploaded["remote"].endswith(".zip")
    (cmd,) = exec_calls
    # Built with shlex.quote, not hand-rolled double quotes (see main.py) — a
    # plain path with no shell-special characters comes back unquoted.
    assert "cd /var/www/uploads" in cmd
    assert "unzip -o -q" in cmd
    # remote_tempfile's own cleanup deletes the remote zip on success — no
    # explicit "rm -f" baked into the unzip command anymore.
    assert "rm -f" not in cmd
    assert deleted == [uploaded["remote"]]


def test_upload_many_archive_rejects_file_outside_destination_root(cred, tmp_path, monkeypatch):
    a = tmp_path / "a.txt"
    a.write_text("A")
    monkeypatch.setattr(sftph_main, "upload", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no upload")))
    with pytest.raises(ValueError, match="outside the destination root"):
        sftph_main._upload_many_archive([(str(a), "/somewhere/else/a.txt")], cred)


def test_upload_many_archive_cleans_up_remote_zip_on_unzip_failure(cred, tmp_path, monkeypatch):
    a = tmp_path / "a.txt"
    a.write_text("A")
    monkeypatch.setattr(sftph_main, "upload", lambda *a, **k: None)
    monkeypatch.setattr(sftph_main, "_run_ssh_exec", lambda *a, **k: {"code": 1, "out": "", "err": "unzip: not found"})
    deleted = []
    monkeypatch.setattr(sftph_main, "delete", lambda addr, _cred: deleted.append(addr))
    with pytest.raises(Exception, match="Remote unzip failed"):
        sftph_main._upload_many_archive([(str(a), "/var/www/uploads/a.txt")], cred)
    # remote_tempfile's own except-path cleanup deletes the reserved remote
    # zip when the unzip command raises out of the with-block.
    assert len(deleted) == 1
    assert deleted[0].startswith("/var/www/uploads/")
    assert deleted[0].endswith(".zip")


# ---------------------------------------------------------------------------
# upload() folder auto-detection -> upload_many
# ---------------------------------------------------------------------------


def test_upload_folder_delegates_to_upload_many(cred, tmp_path, monkeypatch):
    (tmp_path / "a.txt").write_text("A")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("B")
    (tmp_path / ".hidden").write_text("skip me")

    calls = []
    monkeypatch.setattr(sftph_main, "upload_many", lambda files, _cred, **k: calls.append(files) or {})
    out = sftph.upload(str(tmp_path), cred, "/var/www/uploads/site")

    assert out == "/var/www/uploads/site"
    (files,) = calls
    assert sorted(files) == sorted(
        [
            (str(tmp_path / "a.txt"), "/var/www/uploads/site/a.txt"),
            (str(sub / "b.txt"), "/var/www/uploads/site/sub/b.txt"),
        ]
    )

    # An empty directory is a documented no-op — upload_many is never called.
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.setattr(
        sftph_main, "upload_many", lambda *a, **k: (_ for _ in ()).throw(AssertionError("nothing to upload"))
    )
    out = sftph.upload(str(empty_dir), cred, "/var/www/uploads/empty")
    assert out == "/var/www/uploads/empty"


def test_upload_folder_requires_explicit_address(cred, tmp_path):
    with pytest.raises(ValueError, match="sftp_address is required"):
        sftph.upload(str(tmp_path), cred)


# ---------------------------------------------------------------------------
# download() core: transfer, retries, verification, idempotency
# ---------------------------------------------------------------------------


def test_download_reget_and_default_local_name(sftp, cred, tmp_path, monkeypatch):
    local = tmp_path / "out.txt"
    monkeypatch.setattr(sftph_main, "remote_stat", lambda _path, _cred: {"size": 0, "mtime": None})
    monkeypatch.setattr(sftph_main, "remote_dir_exist", lambda _addr, _cred: False)
    out = sftph.download("sftp://sftp.example.com/folder/out.txt", cred, str(local))
    reget_call = next(c for c in sftp.calls if "reget" in (c.batch or ""))
    assert f'reget -p "/folder/out.txt" "{local}.part"' in reget_call.batch
    assert out == str(local)
    assert local.exists()
    assert not os.path.exists(str(local) + ".part")  # published, sidecar gone

    # No local_path given -> defaults to the remote basename in the CWD.
    monkeypatch.chdir(tmp_path)
    out = sftph.download("sftp://sftp.example.com/folder/out.txt", cred)
    assert out == "out.txt"
    assert (tmp_path / "out.txt").exists()


def test_download_retries_after_transient_failure(sftp, cred, tmp_path, monkeypatch):
    local = tmp_path / "out.txt"
    monkeypatch.setattr(sftph_main, "remote_stat", lambda _path, _cred: {"size": 0, "mtime": None})
    monkeypatch.setattr(sftph_main, "remote_dir_exist", lambda _addr, _cred: False)
    sftp.push(err="Connection reset")  # first reget attempt fails
    out = sftph.download("sftp://sftp.example.com/folder/out.txt", cred, str(local))
    assert out == str(local)
    reget_calls = [c for c in sftp.calls if "reget" in (c.batch or "")]
    assert len(reget_calls) == 2


def test_download_sha256_mismatch_raises_and_discards_part(sftp, cred, tmp_path, monkeypatch):
    local = tmp_path / "out.txt"
    monkeypatch.setattr(sftph_main, "remote_stat", lambda _path, _cred: {"size": 0, "mtime": None})
    monkeypatch.setattr(sftph_main, "remote_dir_exist", lambda _addr, _cred: False)
    with pytest.raises(ValueError, match="sha256 mismatch"):
        sftph.download("sftp://sftp.example.com/folder/out.txt", cred, str(local), sha256="0" * 64)
    assert not local.exists()
    assert not (tmp_path / "out.txt.part").exists()


def test_download_overwrite_false_skips_existing(sftp, cred, tmp_path):
    local = tmp_path / "out.txt"
    local.write_text("already here")
    out = sftph.download("sftp://sftp.example.com/folder/out.txt", cred, str(local), overwrite=False)
    assert out == str(local)
    assert sftp.calls == []  # pure local skip, no network round trip at all


# ---------------------------------------------------------------------------
# download() resume / progress knobs
# ---------------------------------------------------------------------------


def test_download_resumable_resume_false_discards_stale_part_first(sftp, cred, tmp_path, monkeypatch):
    local = tmp_path / "out.txt"
    part = tmp_path / "out.txt.part"
    part.write_text("stale partial content")
    monkeypatch.setattr(sftph_main, "remote_stat", lambda _path, _cred: {"size": 0, "mtime": None})

    original_remove = os.remove
    removed = []

    def spy_remove(path):
        removed.append(path)
        original_remove(path)

    monkeypatch.setattr(os, "remove", spy_remove)
    sftph_main._download_resumable(
        cred, "/folder/out.txt", str(local), desc="out.txt", retries=3, sha256=None, resume=False
    )
    assert str(part) in removed
    assert local.exists()


def test_download_progress_false_forwarded_to_run_sftp_with_progress(sftp, cred, tmp_path, monkeypatch):
    local = tmp_path / "out.txt"
    monkeypatch.setattr(sftph_main, "remote_stat", lambda _path, _cred: {"size": 0, "mtime": None})
    monkeypatch.setattr(sftph_main, "remote_dir_exist", lambda _addr, _cred: False)
    seen = {}
    real = sftph_main._run_sftp_with_progress

    def spy(cred_, commands, *, total, probe, desc, progress=True):
        seen["progress"] = progress
        return real(cred_, commands, total=total, probe=probe, desc=desc, progress=progress)

    monkeypatch.setattr(sftph_main, "_run_sftp_with_progress", spy)
    sftph.download("sftp://sftp.example.com/folder/out.txt", cred, str(local), progress=False)
    assert seen["progress"] is False


# ---------------------------------------------------------------------------
# download() folder auto-detection -> download_many
# ---------------------------------------------------------------------------


def test_download_folder_delegates_to_download_many(cred, tmp_path, monkeypatch):
    monkeypatch.setattr(sftph_main, "remote_dir_exist", lambda _addr, _cred: True)
    monkeypatch.setattr(sftph_main, "list_dir", lambda _addr, _cred, **k: ["a.txt", "sub/b.txt"])
    calls = []
    monkeypatch.setattr(sftph_main, "download_many", lambda files, _cred, **k: calls.append(files) or {})

    out = sftph.download("/var/www/uploads/site", cred, str(tmp_path / "site"))

    assert out == str(tmp_path / "site")
    assert os.path.isdir(str(tmp_path / "site"))
    (files,) = calls
    assert sorted(files) == sorted(
        [
            ("/var/www/uploads/site/a.txt", str(tmp_path / "site" / "a.txt")),
            ("/var/www/uploads/site/sub/b.txt", str(tmp_path / "site" / "sub" / "b.txt")),
        ]
    )

    # No local_path given -> defaults to the remote directory's basename in the CWD.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sftph_main, "list_dir", lambda _addr, _cred, **k: ["a.txt"])
    monkeypatch.setattr(sftph_main, "download_many", lambda files, _cred, **k: {})
    out = sftph.download("/var/www/uploads/site2", cred)
    assert out == "site2"
    assert os.path.isdir("site2")

    # An empty remote directory is a documented no-op — download_many is never called.
    monkeypatch.setattr(sftph_main, "list_dir", lambda _addr, _cred, **k: [])
    monkeypatch.setattr(
        sftph_main, "download_many", lambda *a, **k: (_ for _ in ()).throw(AssertionError("nothing to download"))
    )
    out = sftph.download("/var/www/uploads/empty", cred, str(tmp_path / "empty"))
    assert out == str(tmp_path / "empty")
    assert os.path.isdir(str(tmp_path / "empty"))


def test_download_folder_rejects_sha256(cred, tmp_path, monkeypatch):
    monkeypatch.setattr(sftph_main, "remote_dir_exist", lambda _addr, _cred: True)
    with pytest.raises(ValueError, match="not a directory"):
        sftph.download("/var/www/uploads/site", cred, str(tmp_path / "site"), sha256="0" * 64)


# ---------------------------------------------------------------------------
# download_many — archive acceleration with per-file fallback
# ---------------------------------------------------------------------------


def test_download_many_empty_list(cred):
    assert sftph.download_many([], cred) == {}


def test_download_many_dispatch(cred, monkeypatch):
    """Which path download_many takes, across exec support, an explicit archive
    override, an archive failure, and overwrite=False."""
    files = [("/inbox/a.txt", "a.txt")]

    monkeypatch.setattr(sftph_main, "_probe_exec", lambda _c: True)
    archive_calls = []
    monkeypatch.setattr(sftph_main, "_download_many_archive", lambda fs, _c: archive_calls.append(fs) or {})
    monkeypatch.setattr(sftph_main, "download", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no per-file")))
    sftph.download_many(files, cred)
    assert archive_calls == [files]

    monkeypatch.setattr(sftph_main, "_probe_exec", lambda _c: False)
    monkeypatch.setattr(
        sftph_main, "_download_many_archive", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no archive"))
    )
    seen = []
    monkeypatch.setattr(sftph_main, "download", lambda addr, _c, local, **k: seen.append((addr, local)) or local)
    result = sftph.download_many(files, cred)
    assert seen == [("/inbox/a.txt", "a.txt")]
    assert result == {"/inbox/a.txt": "a.txt"}

    monkeypatch.setattr(sftph_main, "_probe_exec", lambda _c: True)
    monkeypatch.setattr(
        sftph_main, "_download_many_archive", lambda *a, **k: (_ for _ in ()).throw(Exception("zip: not found"))
    )
    seen.clear()
    result = sftph.download_many(files, cred)
    assert seen == [("/inbox/a.txt", "a.txt")]
    assert result == {"/inbox/a.txt": "a.txt"}

    monkeypatch.setattr(
        sftph_main, "_probe_exec", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no probe"))
    )
    archive_calls.clear()
    monkeypatch.setattr(sftph_main, "_download_many_archive", lambda fs, _c: archive_calls.append(fs) or {})
    sftph.download_many(files, cred, archive=True)
    assert archive_calls == [files]

    seen.clear()
    monkeypatch.setattr(sftph_main, "download", lambda addr, _c, local, **k: seen.append((addr, local)) or local)
    sftph.download_many(files, cred, archive=False)
    assert seen == [("/inbox/a.txt", "a.txt")]

    monkeypatch.setattr(
        sftph_main, "_download_many_archive", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no archive"))
    )
    kwargs_seen = []
    monkeypatch.setattr(sftph_main, "download", lambda addr, _c, local, **k: kwargs_seen.append(k) or local)
    sftph.download_many(files, cred, archive=True, overwrite=False)
    assert kwargs_seen == [{"retries": 3, "overwrite": False, "resume": True, "progress": True}]


# ---------------------------------------------------------------------------
# _download_many_archive — remote stage+zip -> get -> local unzip
# ---------------------------------------------------------------------------


def test_download_many_archive_stages_zips_downloads_and_extracts(cred, tmp_path, monkeypatch):
    dest_a = tmp_path / "a.txt"
    dest_b = tmp_path / "nested" / "b.txt"

    exec_calls = []

    def fake_exec(_cred, command):
        exec_calls.append(command)
        return {"code": 0, "out": "", "err": ""}

    def fake_download(sftp_address, _cred, local_path, **_k):
        # Simulate the remote zip landing locally with the two requested
        # entries at their arcname (remote path minus leading slash).
        with zipfile.ZipFile(local_path, "w") as zf:
            zf.writestr("var/www/uploads/a.txt", "A")
            zf.writestr("var/www/uploads/sub/b.txt", "B")
        return local_path

    monkeypatch.setattr(sftph_main, "_run_ssh_exec", fake_exec)
    monkeypatch.setattr(sftph_main, "download", fake_download)
    deleted = []
    monkeypatch.setattr(sftph_main, "delete", lambda addr, _cred: deleted.append(addr))

    files = [
        ("/var/www/uploads/a.txt", str(dest_a)),
        ("/var/www/uploads/sub/b.txt", str(dest_b)),
    ]
    result = sftph_main._download_many_archive(files, cred)

    assert result == {"/var/www/uploads/a.txt": str(dest_a), "/var/www/uploads/sub/b.txt": str(dest_b)}
    assert dest_a.read_text() == "A"
    assert dest_b.read_text() == "B"
    # Two exec round trips: the scratch dir's own mkdir (_remote_scratch_dir),
    # then the stage+zip command; both cleaned up (rm -rf) afterwards.
    assert any("mkdir -p" in c and "cp -p" in c and "zip -rq" in c for c in exec_calls)
    assert any(c.startswith("rm -rf") for c in exec_calls)
    # remote_tempfile's own cleanup deletes the reserved remote zip.
    assert len(deleted) == 1
    assert deleted[0].endswith(".zip")


def test_download_many_archive_cleans_up_scratch_dir_on_zip_failure(cred, tmp_path, monkeypatch):
    exec_calls = []

    def fake_exec(_cred, command):
        exec_calls.append(command)
        # The scratch dir's own creation (_remote_scratch_dir) and its
        # eventual rm -rf both succeed; only the staging+zip command fails.
        if "zip -rq" in command:
            return {"code": 1, "out": "", "err": "zip: not found"}
        return {"code": 0, "out": "", "err": ""}

    monkeypatch.setattr(sftph_main, "_run_ssh_exec", fake_exec)
    monkeypatch.setattr(sftph_main, "download", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no download")))
    with pytest.raises(Exception, match="Remote archive staging/zip failed"):
        sftph_main._download_many_archive([("/var/www/uploads/a.txt", str(tmp_path / "a.txt"))], cred)
    assert any(c.startswith("rm -rf") for c in exec_calls)  # scratch dir still cleaned up


# ---------------------------------------------------------------------------
# Progress bar (threaded polling wrapper around _run_sftp)
# ---------------------------------------------------------------------------


def test_run_sftp_with_progress_off_tty_delegates_inline(sftp, cred):
    # pytest's stderr is never a TTY, so this exercises the default path every
    # upload/download test above already relies on.
    res = sftph_main._run_sftp_with_progress(cred, ["ls -l /"], total=100, probe=lambda: 0, desc="x")
    assert res["code"] == 0
    assert len(sftp.calls) == 1


def test_run_sftp_with_progress_tty_runs_on_worker_thread(sftp, cred, monkeypatch):
    monkeypatch.setattr(sftph_main, "_stderr_is_tty", lambda: True)
    probe_calls = {"n": 0}

    def probe():
        probe_calls["n"] += 1
        return min(probe_calls["n"] * 25, 100)

    res = sftph_main._run_sftp_with_progress(cred, ["ls -l /"], total=100, probe=probe, desc="x")
    assert res["code"] == 0
    assert len(sftp.calls) == 1  # the underlying transfer still ran exactly once
    assert probe_calls["n"] >= 1  # progress was actually polled


def test_run_sftp_with_progress_tty_survives_probe_errors(sftp, cred, monkeypatch):
    # A probe that always raises must never break the transfer itself.
    monkeypatch.setattr(sftph_main, "_stderr_is_tty", lambda: True)

    def bad_probe():
        raise RuntimeError("boom")

    res = sftph_main._run_sftp_with_progress(cred, ["ls -l /"], total=100, probe=bad_probe, desc="x")
    assert res["code"] == 0


def test_run_sftp_with_progress_tty_propagates_worker_exception(cred, monkeypatch):
    # Regression test: a Python-level exception inside the worker thread
    # (as opposed to an ordinary non-zero sftp exit code) used to be
    # swallowed by the thread's default excepthook, leaving `result` an
    # empty dict and surfacing as a confusing `KeyError: 'code'` at the
    # call site instead of the real failure. It must now propagate on the
    # main thread, exactly like the inline (non-TTY) path would raise.
    monkeypatch.setattr(sftph_main, "_stderr_is_tty", lambda: True)

    def raising_run_sftp(_cred, _commands, *, extra_env=None):
        raise RuntimeError("disk full")

    monkeypatch.setattr(sftph_main, "_run_sftp", raising_run_sftp)
    with pytest.raises(RuntimeError, match="disk full"):
        sftph_main._run_sftp_with_progress(cred, ["ls -l /"], total=100, probe=lambda: 0, desc="x")


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
