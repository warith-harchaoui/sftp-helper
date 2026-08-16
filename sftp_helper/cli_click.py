"""
SFTP Helper — click-based command-line interface.

Twin of :mod:`sftp_helper.cli_argparse`: same public surface (identical
subcommand names, identical flag semantics), but implemented with
:mod:`click` so users who already have a click-native shell setup
(bash / zsh completion via ``click.shell_completion``, colored `--help`,
nested command groups) can plug it in without friction. Installed as
the ``sftp-helper-click`` entry point in ``pyproject.toml``.

Design notes
------------
- Subcommands mirror ``sftp-helper`` (the argparse twin) so both CLIs
  can be introspected identically by higher layers (FastAPI).
- Flags reuse the argparse names (``--config`` / ``--remote`` / …) rather
  than the more idiomatic click positional style: consistency across
  the two CLIs beats micro-idiomaticity here.
- Errors from the library propagate unchanged; click handles the
  formatting.

Usage Example
-------------
>>> #   sftp-helper-click upload   --config settings.yaml --input local.txt --remote /uploads/local.txt
>>> #   sftp-helper-click download --config settings.yaml --remote /uploads/local.txt --output out.txt
>>> #   sftp-helper-click exists   --config settings.yaml --remote /uploads/local.txt
>>> #   sftp-helper-click mkdir    --config settings.yaml --remote /uploads/a/b/c

Author
------
Warith Harchaoui, Ph.D. — https://linkedin.com/in/warith-harchaoui/
"""

from __future__ import annotations

import json
import sys

try:
    import click
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "The click CLI requires the [cli] extra. Install with: pip install 'sftp-helper[cli]'"
    ) from exc

# Same underlying functions as the argparse twin — one source of truth.
from . import (
    credentials,
    delete,
    download,
    list_dir,
    make_remote_directory,
    normalize_path,
    remote_dir_exist,
    remote_file_exists,
    remote_stat,
    remote_tempfile,
    strip_sftp_path,
    upload,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _mask(cred: dict) -> dict:
    """Return a copy of ``cred`` with the SFTP password redacted for stdout.

    Parameters
    ----------
    cred : dict
        Resolved credentials, potentially containing ``sftp_passwd``.

    Returns
    -------
    dict
        A shallow copy whose ``sftp_passwd`` (when set) is replaced by ``"***"``.
    """
    # Never leak the SFTP password to stdout.
    masked = dict(cred)
    if masked.get("sftp_passwd"):
        masked["sftp_passwd"] = "***"
    return masked


# ---------------------------------------------------------------------------
# Top-level group
#
# ``invoke_without_command=False`` forces the user to name a subcommand;
# ``context_settings`` widens the help output so long option lists stay
# readable on modern terminals.
# ---------------------------------------------------------------------------


@click.group(
    context_settings={"help_option_names": ["-h", "--help"], "max_content_width": 100},
)
@click.version_option(package_name="sftp-helper", prog_name="sftp-helper-click")
def cli() -> None:
    """SFTP Helper — click twin of the argparse CLI. Same subcommands."""
    # Nothing to do at the group level — every subcommand carries its
    # own arguments and side effects.


# ---------------------------------------------------------------------------
# upload
# ---------------------------------------------------------------------------


@cli.command(name="upload")
@click.option(
    "--config",
    "config_",
    default=None,
    type=click.Path(),
    help="Path to a JSON/YAML config file or dir.",
)
@click.option(
    "--input",
    "input_",
    required=True,
    type=click.Path(exists=True),
    help="Local file or directory path.",
)
@click.option("--remote", default=None, type=str, help="Full sftp:// address or plain remote path.")
@click.option(
    "--no-overwrite",
    "no_overwrite",
    is_flag=True,
    default=False,
    help="Skip destinations already present with a matching size (incremental sync).",
)
@click.option(
    "--no-resume",
    "no_resume",
    is_flag=True,
    default=False,
    help="Discard any stale partial transfer instead of resuming it.",
)
@click.option(
    "--no-progress",
    "no_progress",
    is_flag=True,
    default=False,
    help="Suppress the progress bar.",
)
def upload_cmd(
    config_: str | None,
    input_: str,
    remote: str | None,
    no_overwrite: bool,
    no_resume: bool,
    no_progress: bool,
) -> None:
    """Upload a local file or directory to the SFTP server."""
    cred = credentials(config_)
    click.echo(
        upload(
            input_,
            cred,
            remote or "",
            overwrite=not no_overwrite,
            resume=not no_resume,
            progress=not no_progress,
        )
    )


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------


@cli.command(name="download")
@click.option(
    "--config",
    "config_",
    default=None,
    type=click.Path(),
    help="Path to a JSON/YAML config file or dir.",
)
@click.option(
    "--remote", required=True, type=str, help="Full sftp:// address or plain remote path."
)
@click.option(
    "--output",
    default=None,
    type=click.Path(),
    help="Local output path (defaults to remote basename).",
)
@click.option(
    "--no-overwrite",
    "no_overwrite",
    is_flag=True,
    default=False,
    help="Skip destinations already present with a matching size (incremental sync).",
)
@click.option(
    "--no-resume",
    "no_resume",
    is_flag=True,
    default=False,
    help="Discard any stale partial transfer instead of resuming it.",
)
@click.option(
    "--no-progress",
    "no_progress",
    is_flag=True,
    default=False,
    help="Suppress the progress bar.",
)
def download_cmd(
    config_: str | None,
    remote: str,
    output: str | None,
    no_overwrite: bool,
    no_resume: bool,
    no_progress: bool,
) -> None:
    """Download a remote file or directory to the local disk."""
    cred = credentials(config_)
    click.echo(
        download(
            remote,
            cred,
            output or "",
            overwrite=not no_overwrite,
            resume=not no_resume,
            progress=not no_progress,
        )
    )


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@cli.command(name="delete")
@click.option(
    "--config",
    "config_",
    default=None,
    type=click.Path(),
    help="Path to a JSON/YAML config file or dir.",
)
@click.option(
    "--remote", required=True, type=str, help="Full sftp:// address or plain remote path."
)
def delete_cmd(config_: str | None, remote: str) -> None:
    """Delete a remote file (no-op if absent)."""
    cred = credentials(config_)
    if not delete(remote, cred):
        sys.exit(1)


# ---------------------------------------------------------------------------
# exists
# ---------------------------------------------------------------------------


@cli.command()
@click.option(
    "--config",
    "config_",
    default=None,
    type=click.Path(),
    help="Path to a JSON/YAML config file or dir.",
)
@click.option(
    "--remote", required=True, type=str, help="Full sftp:// address or plain remote path."
)
def exists(config_: str | None, remote: str) -> None:
    """Check whether a remote file exists (exit 0 = yes, 1 = no)."""
    cred = credentials(config_)
    if remote_file_exists(remote, cred):
        click.echo("true")
    else:
        click.echo("false")
        sys.exit(1)


# ---------------------------------------------------------------------------
# dir-exists
# ---------------------------------------------------------------------------


@cli.command(name="dir-exists")
@click.option(
    "--config",
    "config_",
    default=None,
    type=click.Path(),
    help="Path to a JSON/YAML config file or dir.",
)
@click.option("--remote", required=True, type=str, help="Remote directory path.")
def dir_exists(config_: str | None, remote: str) -> None:
    """Check whether a remote directory exists (exit 0 = yes, 1 = no)."""
    cred = credentials(config_)
    if remote_dir_exist(remote, cred):
        click.echo("true")
    else:
        click.echo("false")
        sys.exit(1)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@cli.command(name="list")
@click.option(
    "--config",
    "config_",
    default=None,
    type=click.Path(),
    help="Path to a JSON/YAML config file or dir.",
)
@click.option("--remote", required=True, type=str, help="Remote directory path.")
@click.option(
    "--recursive",
    is_flag=True,
    default=False,
    help="Walk sub-directories too (paths relative to --remote).",
)
def list_cmd(config_: str | None, remote: str, recursive: bool) -> None:
    """List a remote directory's entries, one per line."""
    cred = credentials(config_)
    for entry in list_dir(remote, cred, recursive=recursive):
        click.echo(entry)


# ---------------------------------------------------------------------------
# remote-stat
# ---------------------------------------------------------------------------


@cli.command(name="remote-stat")
@click.option(
    "--config",
    "config_",
    default=None,
    type=click.Path(),
    help="Path to a JSON/YAML config file or dir.",
)
@click.option(
    "--remote", required=True, type=str, help="Full sftp:// address or plain remote path."
)
def remote_stat_cmd(config_: str | None, remote: str) -> None:
    """Print a remote file's size/mtime as JSON (exit 1 if missing)."""
    cred = credentials(config_)
    info = remote_stat(remote, cred)
    if info is None:
        click.echo("null")
        sys.exit(1)
    click.echo(json.dumps({"size": info["size"], "mtime": info["mtime"].isoformat()}, indent=2))


# ---------------------------------------------------------------------------
# mkdir
# ---------------------------------------------------------------------------


@cli.command()
@click.option(
    "--config",
    "config_",
    default=None,
    type=click.Path(),
    help="Path to a JSON/YAML config file or dir.",
)
@click.option("--remote", required=True, type=str, help="Remote directory path to create.")
def mkdir(config_: str | None, remote: str) -> None:
    """Create a remote directory (mkdir -p semantics)."""
    cred = credentials(config_)
    make_remote_directory(remote, cred)
    click.echo(remote)


# ---------------------------------------------------------------------------
# normalize-path
# ---------------------------------------------------------------------------


@cli.command(name="normalize-path")
@click.option("--path", "path_", required=True, type=str, help="Path to normalize.")
def normalize_path_cmd(path_: str) -> None:
    """Normalize a remote path (single leading '/', no trailing '/')."""
    click.echo(normalize_path(path_))


# ---------------------------------------------------------------------------
# strip-path
# ---------------------------------------------------------------------------


@cli.command(name="strip-path")
@click.option(
    "--config",
    "config_",
    default=None,
    type=click.Path(),
    help="Path to a JSON/YAML config file or dir.",
)
@click.option("--address", required=True, type=str, help="Full sftp:// address.")
def strip_path_cmd(config_: str | None, address: str) -> None:
    """Strip 'sftp://<host>' prefix from an SFTP address."""
    cred = credentials(config_)
    click.echo(strip_sftp_path(address, cred))


# ---------------------------------------------------------------------------
# tempfile
# ---------------------------------------------------------------------------


@cli.command(name="tempfile")
@click.option(
    "--config",
    "config_",
    default=None,
    type=click.Path(),
    help="Path to a JSON/YAML config file or dir.",
)
@click.option("--ext", default="", type=str, help="Optional file extension (without leading dot).")
@click.option(
    "--subdir", default="", type=str, help="Optional subdirectory under sftp_destination_path."
)
def tempfile_cmd(config_: str | None, ext: str, subdir: str) -> None:
    """Reserve a unique remote path and print {sftp_address, url} as JSON."""
    cred = credentials(config_)
    with remote_tempfile(cred, ext=ext, subdir=subdir) as (addr, url):
        click.echo(json.dumps({"sftp_address": addr, "url": url}, indent=2))


# ---------------------------------------------------------------------------
# show-credentials
# ---------------------------------------------------------------------------


@cli.command(name="show-credentials")
@click.option(
    "--config",
    "config_",
    default=None,
    type=click.Path(),
    help="Path to a JSON/YAML config file or dir.",
)
def show_credentials(config_: str | None) -> None:
    """Print the resolved credentials as JSON (password masked)."""
    cred = credentials(config_)
    click.echo(json.dumps(_mask(cred), indent=2))


def main() -> None:
    """Console entry point (``sftp-helper-click``).

    Click's own ``main()`` only special-cases ``ClickException``/``Abort``
    (and a broken pipe); a plain library exception (e.g. from ``upload()``)
    would otherwise propagate as a raw Python traceback instead of a clean
    CLI error. This wraps the whole invocation and translates that last
    case into a one-line stderr message + exit 1 — click's own control flow
    (usage errors, ``--help``, an explicit ``sys.exit(1)`` in a subcommand)
    already raises ``SystemExit``, a ``BaseException`` this does not catch,
    so it passes through untouched.
    """
    try:
        cli()
    except Exception as err:  # noqa: BLE001 — last resort: see docstring
        click.echo(f"Error: {err}", err=True)
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
