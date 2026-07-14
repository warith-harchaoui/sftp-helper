"""
Smoke tests for the argparse and click CLIs.

These tests exercise the CLI *parsing* layer and the trivial subcommands
that do not need a live SFTP server. The goal here is to prevent
regressions in the CLI entry points — flag names, subcommand names,
dispatch wiring — without pulling in the full paramiko / network stack.

Usage Example
-------------
>>> #   pytest tests/test_cli.py

Author
------
Warith Harchaoui, Ph.D. — https://linkedin.com/in/warith-harchaoui/
"""

from __future__ import annotations

import pytest

# The click CLI needs the ``click`` runtime dep, which lives in the
# ``[cli]`` optional extra. Skip cleanly if it is not installed.
click = pytest.importorskip("click")

from click.testing import CliRunner  # noqa: E402

# ---------------------------------------------------------------------------
# argparse CLI
# ---------------------------------------------------------------------------


EXPECTED_SUBCOMMANDS = {
    "upload",
    "download",
    "delete",
    "exists",
    "dir-exists",
    "mkdir",
    "normalize-path",
    "strip-path",
    "tempfile",
    "show-credentials",
}


def test_argparse_parser_builds_without_error():
    """Building the parser should never fail (imports, subcommand wiring)."""
    from sftp_helper.cli_argparse import build_parser

    parser = build_parser()
    # A parser with at least one subcommand exposes them via _subparsers.
    # We assert on the expected list of subcommand names to catch drift.
    subparsers_action = next(
        a for a in parser._actions if a.__class__.__name__ == "_SubParsersAction"
    )
    assert EXPECTED_SUBCOMMANDS.issubset(set(subparsers_action.choices.keys()))


def test_argparse_help_exits_zero(capsys):
    """``sftp-helper --help`` should exit with code 0 and print usage."""
    from sftp_helper.cli_argparse import main

    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "sftp-helper" in captured.out.lower()


@pytest.mark.parametrize("sub", sorted(EXPECTED_SUBCOMMANDS))
def test_argparse_subcommand_help_exits_zero(sub, capsys):
    """Every subcommand's ``--help`` should exit 0 (no wiring bug)."""
    from sftp_helper.cli_argparse import main

    with pytest.raises(SystemExit) as exc:
        main([sub, "--help"])
    assert exc.value.code == 0


def test_argparse_normalize_path_pure(capsys):
    """``normalize-path`` needs no credentials and no network — pure helper."""
    from sftp_helper.cli_argparse import main

    rc = main(["normalize-path", "--path", "foo/bar///"])
    assert rc == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "/foo/bar"


# ---------------------------------------------------------------------------
# click CLI
# ---------------------------------------------------------------------------


def test_click_group_has_expected_subcommands():
    """The click group must expose the same subcommands as the argparse CLI."""
    from sftp_helper.cli_click import cli

    assert EXPECTED_SUBCOMMANDS.issubset(set(cli.commands.keys()))


def test_click_help_exits_zero():
    """``sftp-helper-click --help`` should exit 0."""
    from sftp_helper.cli_click import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "sftp helper" in result.output.lower()


@pytest.mark.parametrize("sub", sorted(EXPECTED_SUBCOMMANDS))
def test_click_subcommand_help_exits_zero(sub):
    """Every click subcommand's ``--help`` should exit 0."""
    from sftp_helper.cli_click import cli

    runner = CliRunner()
    result = runner.invoke(cli, [sub, "--help"])
    assert result.exit_code == 0


def test_click_normalize_path_pure():
    """``normalize-path`` needs no credentials and no network — pure helper."""
    from sftp_helper.cli_click import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["normalize-path", "--path", "foo/bar///"])
    assert result.exit_code == 0
    assert result.output.strip() == "/foo/bar"
