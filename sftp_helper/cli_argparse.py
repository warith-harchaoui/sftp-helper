"""
SFTP Helper — argparse-based command-line interface.

Thin wrapper around the pure functions in :mod:`sftp_helper.main` that
exposes the whole toolkit as subcommands under a single ``sftp-helper``
entry point. Written with :mod:`argparse` from the standard library so
the CLI works out of the box on any Python install that has the package
installed — no extra dependency required.

Every subcommand accepts ``--config`` (path to a JSON/YAML file or a
directory containing one). When omitted, ``sftp_helper.credentials`` falls
back to environment variables / ``.env`` — same discovery order as the
library.

Subcommands
-----------
- ``upload``           — upload a local file to the SFTP server
- ``download``         — download a remote file to the local disk
- ``delete``           — delete a remote file
- ``exists``           — check whether a remote file exists (exit code 0/1)
- ``dir-exists``       — check whether a remote directory exists (exit code 0/1)
- ``mkdir``            — create a remote directory (mkdir -p semantics)
- ``normalize-path``   — normalize a remote path (leading '/', no trailing '/')
- ``strip-path``       — strip ``sftp://<host>`` prefix from an SFTP address
- ``tempfile``         — reserve a unique remote path (no upload) and print it
- ``show-credentials`` — print the resolved credentials (secret masked)

Usage Example
-------------
>>> #   sftp-helper upload         --config sftp_config.json --input local.txt --remote /uploads/local.txt
>>> #   sftp-helper download       --config sftp_config.json --remote /uploads/local.txt --output out.txt
>>> #   sftp-helper delete         --config sftp_config.json --remote /uploads/local.txt
>>> #   sftp-helper exists         --config sftp_config.json --remote /uploads/local.txt
>>> #   sftp-helper dir-exists     --config sftp_config.json --remote /uploads
>>> #   sftp-helper mkdir          --config sftp_config.json --remote /uploads/a/b/c
>>> #   sftp-helper normalize-path --path //foo/bar/
>>> #   sftp-helper strip-path     --config sftp_config.json --address sftp://host/foo/bar
>>> #   sftp-helper tempfile       --config sftp_config.json --ext txt --subdir batch-42
>>> #   sftp-helper show-credentials --config sftp_config.json

Author
------
Warith Harchaoui, Ph.D. — https://linkedin.com/in/warith-harchaoui/
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

# Import the pure functions once here — every subcommand is a thin dispatch
# on top of these, no logic duplication.
from . import (
    credentials,
    delete,
    download,
    make_remote_directory,
    normalize_path,
    remote_dir_exist,
    remote_file_exists,
    remote_tempfile,
    strip_sftp_path,
    upload,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_cred(config: str | None) -> dict:
    """Resolve credentials for a subcommand from an optional config path.

    Parameters
    ----------
    config : str or None
        Path to a JSON/YAML file or a directory containing one; ``None``
        falls back to env vars / ``.env``.

    Returns
    -------
    dict
        The resolved credentials dict.
    """
    # Central credentials loader — mirrors the library entry point so the
    # CLI has one place to change if the discovery order ever evolves.
    return credentials(config)


def _mask(cred: dict) -> dict:
    """Return a copy of ``cred`` with the SFTP password redacted for stdout.

    Parameters
    ----------
    cred : dict
        Resolved credentials, potentially containing ``sftp_passwd``.

    Returns
    -------
    dict
        A shallow copy whose ``sftp_passwd`` (when set) is replaced by
        ``"***"`` while the key itself is kept so downstream scripts see a
        stable schema.
    """
    # Never echo the SFTP password to stdout. We keep the key so a caller
    # scripting on top of ``show-credentials`` still gets a stable schema.
    masked = dict(cred)
    if masked.get("sftp_passwd"):
        masked["sftp_passwd"] = "***"
    return masked


# ---------------------------------------------------------------------------
# Subcommand handlers
#
# Each handler receives the parsed ``argparse.Namespace`` and returns a
# process exit code (``0`` on success). Handlers deliberately stay short:
# they translate CLI arguments into keyword arguments for the underlying
# library function, print a machine-friendly result, and let exceptions
# propagate as non-zero exit codes.
# ---------------------------------------------------------------------------


def _handle_upload(ns: argparse.Namespace) -> int:
    """Handle ``upload``: send a local file, print its remote address.

    Parameters
    ----------
    ns : argparse.Namespace
        Parsed args (``config``, ``input``, ``remote``).

    Returns
    -------
    int
        ``0`` on success.
    """
    # upload() returns the ``sftp://`` (or plain remote) address of the
    # uploaded file. Emit it so shell pipelines can chain on stdout.
    cred = _load_cred(ns.config)
    addr = upload(ns.input, cred, ns.remote or "")
    print(addr)
    return 0


def _handle_download(ns: argparse.Namespace) -> int:
    """Handle ``download``: fetch a remote file, print the local path.

    Parameters
    ----------
    ns : argparse.Namespace
        Parsed args (``config``, ``remote``, ``output``).

    Returns
    -------
    int
        ``0`` on success.
    """
    # download() returns the local path (falls back to the remote basename).
    cred = _load_cred(ns.config)
    local = download(ns.remote, cred, ns.output or "")
    print(local)
    return 0


def _handle_delete(ns: argparse.Namespace) -> int:
    """Handle ``delete``: remove a remote file (idempotent).

    Parameters
    ----------
    ns : argparse.Namespace
        Parsed args (``config``, ``remote``).

    Returns
    -------
    int
        ``0`` when the file is gone afterwards, ``1`` otherwise.
    """
    # delete() returns True even when the target never existed — we surface
    # a boolean-shaped exit code so shell scripts can rely on ``$?``.
    cred = _load_cred(ns.config)
    ok = delete(ns.remote, cred)
    return 0 if ok else 1


def _handle_exists(ns: argparse.Namespace) -> int:
    """Handle ``exists``: probe a remote file, print true/false.

    Parameters
    ----------
    ns : argparse.Namespace
        Parsed args (``config``, ``remote``).

    Returns
    -------
    int
        ``0`` if the file exists, ``1`` if missing (``test -e`` convention).
    """
    # Exit code 0 = exists, 1 = missing. This mirrors the Unix ``test -e``
    # convention so ``if sftp-helper exists ...; then ...`` reads naturally.
    cred = _load_cred(ns.config)
    if remote_file_exists(ns.remote, cred):
        print("true")
        return 0
    print("false")
    return 1


def _handle_dir_exists(ns: argparse.Namespace) -> int:
    """Handle ``dir-exists``: probe a remote directory, print true/false.

    Parameters
    ----------
    ns : argparse.Namespace
        Parsed args (``config``, ``remote``).

    Returns
    -------
    int
        ``0`` if the directory exists, ``1`` otherwise.
    """
    # Same convention as ``exists`` but for directories.
    cred = _load_cred(ns.config)
    if remote_dir_exist(ns.remote, cred):
        print("true")
        return 0
    print("false")
    return 1


def _handle_mkdir(ns: argparse.Namespace) -> int:
    """Handle ``mkdir``: create a remote directory (mkdir -p).

    Parameters
    ----------
    ns : argparse.Namespace
        Parsed args (``config``, ``remote``).

    Returns
    -------
    int
        ``0`` on success.
    """
    # ``make_remote_directory`` has ``mkdir -p`` semantics.
    cred = _load_cred(ns.config)
    make_remote_directory(ns.remote, cred)
    print(ns.remote)
    return 0


def _handle_normalize_path(ns: argparse.Namespace) -> int:
    """Handle ``normalize-path``: print the canonical form of a path.

    Parameters
    ----------
    ns : argparse.Namespace
        Parsed args (``path``).

    Returns
    -------
    int
        ``0`` — pure helper, no credentials or network.
    """
    # Pure helper — no credentials needed, no network hit.
    print(normalize_path(ns.path))
    return 0


def _handle_strip_path(ns: argparse.Namespace) -> int:
    """Handle ``strip-path``: print an address with ``sftp://<host>`` removed.

    Parameters
    ----------
    ns : argparse.Namespace
        Parsed args (``config``, ``address``).

    Returns
    -------
    int
        ``0`` on success.
    """
    # Needs the host from credentials to strip ``sftp://<host>``.
    cred = _load_cred(ns.config)
    print(strip_sftp_path(ns.address, cred))
    return 0


def _handle_tempfile(ns: argparse.Namespace) -> int:
    """Handle ``tempfile``: print reserved ``{sftp_address, url}`` as JSON.

    Parameters
    ----------
    ns : argparse.Namespace
        Parsed args (``config``, ``ext``, ``subdir``).

    Returns
    -------
    int
        ``0`` on success.
    """
    # Reserve a unique remote path and print ``{sftp_address, url}`` as JSON
    # for machine consumption. The remote file is *not* created; the caller
    # is expected to upload to that address if they want it on disk.
    # We do NOT actually enter the context here because that would delete
    # the file on exit — the CLI just reports the reserved coordinates.
    cred = _load_cred(ns.config)
    with remote_tempfile(cred, ext=ns.ext, subdir=ns.subdir) as (addr, url):
        payload = {"sftp_address": addr, "url": url}
        print(json.dumps(payload, indent=2))
    return 0


def _handle_show_credentials(ns: argparse.Namespace) -> int:
    """Handle ``show-credentials``: print resolved credentials (masked) as JSON.

    Parameters
    ----------
    ns : argparse.Namespace
        Parsed args (``config``).

    Returns
    -------
    int
        ``0`` on success.
    """
    # Prints the resolved credentials as JSON with the password masked.
    # Useful to debug config discovery (JSON vs env vs .env).
    cred = _load_cred(ns.config)
    print(json.dumps(_mask(cred), indent=2))
    return 0


# ---------------------------------------------------------------------------
# Parser construction
#
# One helper per subcommand keeps ``build_parser`` readable and lets the
# click twin (:mod:`sftp_helper.cli_click`) mirror the exact same flag
# names without any risk of drift.
# ---------------------------------------------------------------------------


def _add_common_config(p: argparse.ArgumentParser) -> None:
    """Attach the shared ``--config`` option to a subparser.

    Parameters
    ----------
    p : argparse.ArgumentParser
        The subparser to receive the ``--config`` option.
    """
    # Every network-touching subcommand takes ``--config``; keep the option
    # definition centralised so help text and defaults stay in sync.
    p.add_argument(
        "--config",
        default=None,
        help="Path to a JSON/YAML config file, or a directory containing one. "
        "Falls back to env vars / .env when omitted.",
    )


def _add_upload(sub: argparse._SubParsersAction) -> None:
    """Register the ``upload`` subcommand and its flags on ``sub``."""
    p = sub.add_parser("upload", help="Upload a local file to the SFTP server.")
    _add_common_config(p)
    p.add_argument("--input", required=True, help="Local file path.")
    p.add_argument(
        "--remote",
        default=None,
        help="Full sftp:// address (or plain remote path). If omitted, a "
        "content-hashed name under sftp_destination_path is used.",
    )
    p.set_defaults(func=_handle_upload)


def _add_download(sub: argparse._SubParsersAction) -> None:
    """Register the ``download`` subcommand and its flags on ``sub``."""
    p = sub.add_parser("download", help="Download a remote file to the local disk.")
    _add_common_config(p)
    p.add_argument("--remote", required=True, help="Full sftp:// address or plain remote path.")
    p.add_argument(
        "--output", default=None, help="Local output path (defaults to remote basename)."
    )
    p.set_defaults(func=_handle_download)


def _add_delete(sub: argparse._SubParsersAction) -> None:
    """Register the ``delete`` subcommand and its flags on ``sub``."""
    p = sub.add_parser("delete", help="Delete a remote file (no-op if absent).")
    _add_common_config(p)
    p.add_argument("--remote", required=True, help="Full sftp:// address or plain remote path.")
    p.set_defaults(func=_handle_delete)


def _add_exists(sub: argparse._SubParsersAction) -> None:
    """Register the ``exists`` subcommand and its flags on ``sub``."""
    p = sub.add_parser("exists", help="Check whether a remote file exists (exit 0 = yes, 1 = no).")
    _add_common_config(p)
    p.add_argument("--remote", required=True, help="Full sftp:// address or plain remote path.")
    p.set_defaults(func=_handle_exists)


def _add_dir_exists(sub: argparse._SubParsersAction) -> None:
    """Register the ``dir-exists`` subcommand and its flags on ``sub``."""
    p = sub.add_parser(
        "dir-exists", help="Check whether a remote directory exists (exit 0 = yes, 1 = no)."
    )
    _add_common_config(p)
    p.add_argument("--remote", required=True, help="Remote directory path.")
    p.set_defaults(func=_handle_dir_exists)


def _add_mkdir(sub: argparse._SubParsersAction) -> None:
    """Register the ``mkdir`` subcommand and its flags on ``sub``."""
    p = sub.add_parser("mkdir", help="Create a remote directory (mkdir -p semantics).")
    _add_common_config(p)
    p.add_argument("--remote", required=True, help="Remote directory path to create.")
    p.set_defaults(func=_handle_mkdir)


def _add_normalize_path(sub: argparse._SubParsersAction) -> None:
    """Register the ``normalize-path`` subcommand and its flags on ``sub``."""
    p = sub.add_parser(
        "normalize-path", help="Normalize a remote path (single leading '/', no trailing '/')."
    )
    p.add_argument("--path", required=True, help="Path to normalize.")
    p.set_defaults(func=_handle_normalize_path)


def _add_strip_path(sub: argparse._SubParsersAction) -> None:
    """Register the ``strip-path`` subcommand and its flags on ``sub``."""
    p = sub.add_parser("strip-path", help="Strip 'sftp://<host>' prefix from an SFTP address.")
    _add_common_config(p)
    p.add_argument("--address", required=True, help="Full sftp:// address.")
    p.set_defaults(func=_handle_strip_path)


def _add_tempfile(sub: argparse._SubParsersAction) -> None:
    """Register the ``tempfile`` subcommand and its flags on ``sub``."""
    p = sub.add_parser(
        "tempfile",
        help="Reserve a unique remote path and print {sftp_address, url} as JSON. "
        "The file is deleted on exit — for scripting, use the library.",
    )
    _add_common_config(p)
    p.add_argument("--ext", default="", help="Optional file extension (without the leading dot).")
    p.add_argument(
        "--subdir", default="", help="Optional subdirectory under sftp_destination_path."
    )
    p.set_defaults(func=_handle_tempfile)


def _add_show_credentials(sub: argparse._SubParsersAction) -> None:
    """Register the ``show-credentials`` subcommand and its flags on ``sub``."""
    p = sub.add_parser(
        "show-credentials", help="Print the resolved credentials as JSON (password masked)."
    )
    _add_common_config(p)
    p.set_defaults(func=_handle_show_credentials)


def build_parser() -> argparse.ArgumentParser:
    """
    Assemble the top-level ``sftp-helper`` argument parser.

    Returns
    -------
    argparse.ArgumentParser
        Fully wired parser with every subcommand attached.
    """
    parser = argparse.ArgumentParser(
        prog="sftp-helper",
        description=(
            "SFTP Helper — utility CLI for upload / download / delete / exists / "
            "mkdir / normalize-path / strip-path / tempfile / show-credentials. "
            "Strict host-key verification is always on."
        ),
    )
    # Every non-trivial CLI benefits from ``--version`` — cheap to add and
    # oncall people always look for it. We resolve it lazily to avoid a
    # circular import if importlib.metadata blows up in some edge case.
    try:
        from importlib.metadata import version as _pkg_version

        parser.add_argument(
            "--version",
            action="version",
            version=f"%(prog)s {_pkg_version('sftp-helper')}",
        )
    except Exception:  # pragma: no cover — never fatal
        pass

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True

    # Register every subcommand. Order matters for help output only.
    _add_upload(subparsers)
    _add_download(subparsers)
    _add_delete(subparsers)
    _add_exists(subparsers)
    _add_dir_exists(subparsers)
    _add_mkdir(subparsers)
    _add_normalize_path(subparsers)
    _add_strip_path(subparsers)
    _add_tempfile(subparsers)
    _add_show_credentials(subparsers)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """
    Entry point invoked by ``sftp-helper`` (see ``[project.scripts]``).

    Parameters
    ----------
    argv : sequence of str, optional
        Arguments to parse. Defaults to ``sys.argv[1:]`` when None.

    Returns
    -------
    int
        Process exit code (``0`` on success).
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    # Every subparser sets ``func`` via ``set_defaults`` — no dispatch table
    # needed, argparse resolved it for us.
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
