"""
Tests for the argparse and click CLIs.

Both CLIs (:mod:`sftp_helper.cli_argparse`, :mod:`sftp_helper.cli_click`)
mirror the same subcommands and flag names by design, so every
subcommand's actual behaviour is tested *once*, through the ``cli_driver``
fixture parametrized over both backends, rather than hand-duplicated per
backend. Each functional test monkeypatches only the underlying
``sftp_helper.main`` function a handler calls — the same boundary
``test_sftp_helper.py`` mocks at — so these exercise the CLI's real
argument-translation and output-formatting layer, not just parser/group
wiring.

Two tests are kept backend-specific rather than folded into
``cli_driver``: the "clean error, not a traceback" checks call each
module's actual ``main()`` console-script entry point directly. Click's
``CliRunner`` (used by ``cli_driver``) has its own exception handling that
would not catch a regression in ``cli_click.main()``'s own try/except, so
that one behaviour needs the real entry point, not the test harness.

Usage Example
-------------
>>> #   pytest tests/test_cli.py

Author
------
Warith Harchaoui, Ph.D. — https://linkedin.com/in/warith-harchaoui/
"""

from __future__ import annotations

import contextlib
import io
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

EXPECTED_SUBCOMMANDS = {
    "upload",
    "download",
    "delete",
    "exists",
    "dir-exists",
    "list",
    "remote-stat",
    "mkdir",
    "normalize-path",
    "strip-path",
    "tempfile",
    "show-credentials",
}

# Shared fake credentials for every functional test below. Includes a
# password so test_cli_show_credentials_masks_password has something to
# mask.
FAKE_CRED = {
    "sftp_host": "sftp.example.com",
    "sftp_login": "alice",
    "sftp_https": "https://example.com/uploads",
    "sftp_destination_path": "/var/www/uploads",
    "sftp_passwd": "hunter2",
}


def _run_argparse(args: list[str]) -> tuple[int, str]:
    from sftp_helper.cli_argparse import main

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            code = main(args)
        except SystemExit as exc:
            code = exc.code
    return code, buf.getvalue()


def _run_click(args: list[str]) -> tuple[int, str]:
    from click.testing import CliRunner
    from sftp_helper.cli_click import cli

    result = CliRunner().invoke(cli, args)
    return result.exit_code, result.output


@dataclass
class CLIDriver:
    """One CLI backend, abstracted to a uniform ``run()`` + patchable module."""

    name: str
    module: object
    run: Callable[[list[str]], tuple[int, str]]


@pytest.fixture(params=["argparse", "click"])
def cli_driver(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> CLIDriver:
    """Both CLI backends expose identical subcommands/flags (by design), so
    every functional test below runs once per backend through this fixture
    instead of being hand-duplicated. Also pre-patches ``credentials`` to
    ``FAKE_CRED`` since every credentialed subcommand needs it."""
    if request.param == "click":
        pytest.importorskip("click")
        from sftp_helper import cli_click as module

        driver = CLIDriver("click", module, _run_click)
    else:
        from sftp_helper import cli_argparse as module

        driver = CLIDriver("argparse", module, _run_argparse)
    monkeypatch.setattr(module, "credentials", lambda *_a, **_k: dict(FAKE_CRED))
    return driver


# ---------------------------------------------------------------------------
# Wiring: parser/group construction and help output (not handler behaviour)
# ---------------------------------------------------------------------------


def test_argparse_parser_builds_with_expected_subcommands():
    """Building the parser should never fail, and exposes every documented
    subcommand (catches wiring drift)."""
    from sftp_helper.cli_argparse import build_parser

    parser = build_parser()
    subparsers_action = next(
        a for a in parser._actions if a.__class__.__name__ == "_SubParsersAction"
    )
    assert EXPECTED_SUBCOMMANDS.issubset(set(subparsers_action.choices.keys()))


def test_click_group_has_expected_subcommands():
    """The click group must expose the same subcommands as the argparse CLI."""
    pytest.importorskip("click")
    from sftp_helper.cli_click import cli

    assert EXPECTED_SUBCOMMANDS.issubset(set(cli.commands.keys()))


def test_cli_top_level_and_subcommand_help_exit_zero(cli_driver: CLIDriver):
    """``--help`` at the top level and for every subcommand should exit 0 —
    a subparser/command left unattached would break at least one of these."""
    code, out = cli_driver.run(["--help"])
    assert code == 0
    assert "sftp" in out.lower()
    for sub in sorted(EXPECTED_SUBCOMMANDS):
        code, _out = cli_driver.run([sub, "--help"])
        assert code == 0, f"{cli_driver.name} {sub} --help exited {code}"


# ---------------------------------------------------------------------------
# Entry-point error handling — the real main(), not the test harness's own
# exception catching (see module docstring).
# ---------------------------------------------------------------------------


def test_argparse_main_turns_library_error_into_clean_message(capsys):
    """A library exception (e.g. an unsafe path) prints one clean line and
    exits 1 — not a raw Python traceback."""
    from sftp_helper.cli_argparse import main

    rc = main(["normalize-path", "--path", "foo\nbar"])
    assert rc == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("Error: ")
    assert "Traceback" not in captured.err


def test_click_main_turns_library_error_into_clean_message(monkeypatch, capsys):
    """Same contract as the argparse twin, but for ``sftp-helper-click``'s
    own ``main()`` wrapper (not click's ``cli`` group alone)."""
    pytest.importorskip("click")
    from sftp_helper.cli_click import main

    monkeypatch.setattr(sys, "argv", ["sftp-helper-click", "normalize-path", "--path", "foo\nbar"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("Error: ")
    assert "Traceback" not in captured.err


# ---------------------------------------------------------------------------
# Functional: every subcommand's real argument-translation + output,
# against a monkeypatched sftp_helper.main function.
# ---------------------------------------------------------------------------


def test_cli_normalize_path_is_pure_no_credentials_needed(cli_driver: CLIDriver):
    """No config, no network — the one subcommand that needs neither."""
    code, out = cli_driver.run(["normalize-path", "--path", "foo/bar///"])
    assert code == 0
    assert out.strip() == "/foo/bar"


def test_cli_upload_translates_flags_and_prints_remote_address(
    cli_driver: CLIDriver, tmp_path, monkeypatch
):
    """``--no-overwrite``/``--no-resume``/``--no-progress`` invert to the
    library's ``overwrite``/``resume``/``progress`` kwargs; the printed
    line is exactly the address ``upload()`` returned."""
    local = tmp_path / "in.txt"
    local.write_text("data")
    calls = []

    def fake_upload(local_path, cred, remote, *, overwrite, resume, progress):
        calls.append((local_path, cred, remote, overwrite, resume, progress))
        return "/var/www/uploads/in.txt"

    monkeypatch.setattr(cli_driver.module, "upload", fake_upload)

    code, out = cli_driver.run(
        ["upload", "--input", str(local), "--remote", "/var/www/uploads/in.txt"]
    )
    assert code == 0
    assert out.strip() == "/var/www/uploads/in.txt"
    (call,) = calls
    assert call[0] == str(local)
    assert call[2] == "/var/www/uploads/in.txt"
    assert call[3:] == (True, True, True)  # no --no-* flags -> every knob True

    calls.clear()
    code, _out = cli_driver.run(
        [
            "upload",
            "--input",
            str(local),
            "--remote",
            "/var/www/uploads/in.txt",
            "--no-overwrite",
            "--no-resume",
            "--no-progress",
        ]
    )
    assert code == 0
    (call,) = calls
    assert call[3:] == (False, False, False)


def test_cli_download_translates_flags_and_prints_local_path(
    cli_driver: CLIDriver, tmp_path, monkeypatch
):
    """Mirrors the upload test: same three flags, ``download()`` instead."""
    out_path = tmp_path / "out.txt"
    calls = []

    def fake_download(remote, cred, local, *, overwrite, resume, progress):
        calls.append((remote, cred, local, overwrite, resume, progress))
        return str(out_path)

    monkeypatch.setattr(cli_driver.module, "download", fake_download)

    code, out = cli_driver.run(
        [
            "download",
            "--remote",
            "/var/www/uploads/in.txt",
            "--output",
            str(out_path),
            "--no-overwrite",
            "--no-resume",
            "--no-progress",
        ]
    )
    assert code == 0
    assert out.strip() == str(out_path)
    (call,) = calls
    assert call[0] == "/var/www/uploads/in.txt"
    assert call[3:] == (False, False, False)


def test_cli_delete_exit_code_reflects_result(cli_driver: CLIDriver, monkeypatch):
    """``delete``'s exit code is a boolean read of the library result — 0
    when the file is gone afterwards, 1 otherwise. No stdout either way."""
    monkeypatch.setattr(cli_driver.module, "delete", lambda *_a, **_k: True)
    code, out = cli_driver.run(["delete", "--remote", "/var/www/uploads/a.txt"])
    assert code == 0
    assert out == ""

    monkeypatch.setattr(cli_driver.module, "delete", lambda *_a, **_k: False)
    code, out = cli_driver.run(["delete", "--remote", "/var/www/uploads/a.txt"])
    assert code == 1


def test_cli_exists_prints_true_false_with_matching_exit_code(cli_driver: CLIDriver, monkeypatch):
    """``exists`` follows the Unix ``test -e`` convention: exit 0 + "true",
    or exit 1 + "false"."""
    monkeypatch.setattr(cli_driver.module, "remote_file_exists", lambda *_a, **_k: True)
    code, out = cli_driver.run(["exists", "--remote", "/var/www/uploads/a.txt"])
    assert (code, out.strip()) == (0, "true")

    monkeypatch.setattr(cli_driver.module, "remote_file_exists", lambda *_a, **_k: False)
    code, out = cli_driver.run(["exists", "--remote", "/var/www/uploads/a.txt"])
    assert (code, out.strip()) == (1, "false")


def test_cli_dir_exists_prints_true_false_with_matching_exit_code(
    cli_driver: CLIDriver, monkeypatch
):
    """Same convention as ``exists``, backed by ``remote_dir_exist``."""
    monkeypatch.setattr(cli_driver.module, "remote_dir_exist", lambda *_a, **_k: True)
    code, out = cli_driver.run(["dir-exists", "--remote", "/var/www/uploads"])
    assert (code, out.strip()) == (0, "true")

    monkeypatch.setattr(cli_driver.module, "remote_dir_exist", lambda *_a, **_k: False)
    code, out = cli_driver.run(["dir-exists", "--remote", "/var/www/uploads"])
    assert (code, out.strip()) == (1, "false")


def test_cli_list_prints_entries_and_forwards_recursive_flag(
    cli_driver: CLIDriver, monkeypatch
):
    """One entry per line; ``--recursive`` reaches ``list_dir`` unchanged."""
    calls = []

    def fake_list_dir(remote, cred, *, recursive):
        calls.append((remote, recursive))
        return ["a.txt", "sub/b.txt"] if recursive else ["a.txt"]

    monkeypatch.setattr(cli_driver.module, "list_dir", fake_list_dir)

    code, out = cli_driver.run(["list", "--remote", "/var/www/uploads"])
    assert code == 0
    assert out.splitlines() == ["a.txt"]
    assert calls[-1] == ("/var/www/uploads", False)

    code, out = cli_driver.run(["list", "--remote", "/var/www/uploads", "--recursive"])
    assert code == 0
    assert out.splitlines() == ["a.txt", "sub/b.txt"]
    assert calls[-1] == ("/var/www/uploads", True)


def test_cli_remote_stat_prints_json_or_null_with_matching_exit_code(
    cli_driver: CLIDriver, monkeypatch
):
    """Found -> JSON ``{size, mtime}`` + exit 0; missing -> "null" + exit 1
    (matching ``exists``/``dir-exists``'s convention)."""
    mtime = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    monkeypatch.setattr(
        cli_driver.module, "remote_stat", lambda *_a, **_k: {"size": 42, "mtime": mtime}
    )
    code, out = cli_driver.run(["remote-stat", "--remote", "/var/www/uploads/a.txt"])
    assert code == 0
    assert '"size": 42' in out
    assert mtime.isoformat() in out

    monkeypatch.setattr(cli_driver.module, "remote_stat", lambda *_a, **_k: None)
    code, out = cli_driver.run(["remote-stat", "--remote", "/var/www/uploads/missing.txt"])
    assert (code, out.strip()) == (1, "null")


def test_cli_mkdir_creates_and_prints_remote_path(cli_driver: CLIDriver, monkeypatch):
    calls = []
    monkeypatch.setattr(
        cli_driver.module, "make_remote_directory", lambda remote, cred: calls.append(remote)
    )
    code, out = cli_driver.run(["mkdir", "--remote", "/var/www/uploads/a/b/c"])
    assert code == 0
    assert out.strip() == "/var/www/uploads/a/b/c"
    assert calls == ["/var/www/uploads/a/b/c"]


def test_cli_strip_path_prints_stripped_address(cli_driver: CLIDriver, monkeypatch):
    monkeypatch.setattr(cli_driver.module, "strip_sftp_path", lambda *_a, **_k: "/foo/bar")
    code, out = cli_driver.run(["strip-path", "--address", "sftp://host/foo/bar"])
    assert code == 0
    assert out.strip() == "/foo/bar"


def test_cli_tempfile_prints_reserved_address_and_url(cli_driver: CLIDriver, monkeypatch):
    @contextlib.contextmanager
    def fake_remote_tempfile(cred, ext="", subdir=""):
        assert ext == "txt"
        assert subdir == "batch-42"
        yield ("/var/www/uploads/abc123.txt", "https://example.com/uploads/abc123.txt")

    monkeypatch.setattr(cli_driver.module, "remote_tempfile", fake_remote_tempfile)
    code, out = cli_driver.run(["tempfile", "--ext", "txt", "--subdir", "batch-42"])
    assert code == 0
    assert "/var/www/uploads/abc123.txt" in out
    assert "https://example.com/uploads/abc123.txt" in out


def test_cli_show_credentials_masks_password(cli_driver: CLIDriver):
    """The password is redacted; every other resolved field passes through."""
    code, out = cli_driver.run(["show-credentials"])
    assert code == 0
    assert '"sftp_passwd": "***"' in out
    assert FAKE_CRED["sftp_passwd"] not in out
    assert FAKE_CRED["sftp_host"] in out
