"""
SFTP Helper

This module provides functions to interact with an SFTP server, allowing users
to perform file uploads, downloads, and deletions, as well as to check file
existence remotely.

Backed by paramiko's SFTPClient. Host key verification is on by default:
``~/.ssh/known_hosts`` is loaded, and unknown hosts are rejected. A caller
who wants to trust a specific server may pass an additional known_hosts file
via ``cred["sftp_known_hosts"]`` -- there is no flag to disable verification.

Author:
- Warith HARCHAOUI (https://linkedin.com/in/warith-harchaoui)
"""

# ``from __future__ import annotations`` keeps every annotation a lazy string
# so the modern ``X | None`` / ``tuple[...]`` spellings evaluate on any of the
# supported interpreters (3.10+) without importing them at runtime.
from __future__ import annotations

import os
import secrets
import stat as stat_mod
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import os_helper as osh
import paramiko

# Diagnostics go through os-helper's logging surface (``osh.info`` /
# ``osh.warning``) rather than the stdlib logger or bare ``print``. This is
# the suite-wide convention: every helper package funnels its verbosity
# through the same os-helper channel so applications tune it in one place.


def credentials(config_path: str | None = None) -> dict:
    """
    Retrieve SFTP credentials from a configuration file, folder, or environment.

    Parameters
    ----------
    config_path : str
        Path to a JSON/YAML file, a directory containing one, or ``None`` to
        fall back to environment variables / ``.env``.

    Returns
    -------
    dict
        Dictionary with keys: sftp_host, sftp_login, sftp_passwd,
        sftp_destination_path, sftp_https. ``sftp_port`` and
        ``sftp_known_hosts`` are optional.
    """
    # The five keys below are the mandatory contract every SFTP target must
    # satisfy. ``osh.get_config`` resolves them from (in order) an explicit
    # file, a directory containing one, then env vars / ``.env`` — and raises
    # if none of those sources provides the full set, so callers never get a
    # half-populated credentials dict.
    keys = ["sftp_host", "sftp_login", "sftp_passwd", "sftp_destination_path", "sftp_https"]
    return osh.get_config(keys, "SFTP", config_path)


@contextmanager
def get_client_sftp(cred: dict) -> Iterator[paramiko.SFTPClient]:
    """
    Open an SFTP connection with strict host key verification.

    The system ``~/.ssh/known_hosts`` is loaded automatically. If
    ``cred["sftp_known_hosts"]`` is set, that file is loaded as well.
    Connecting to a host whose key is not in either store raises
    ``paramiko.SSHException`` -- there is no opt-out.

    Authentication tries password first (if ``sftp_passwd`` is non-empty),
    then falls back to the SSH agent and default identity files
    (``~/.ssh/id_rsa``, ``~/.ssh/id_ed25519`` ...).

    Yields
    ------
    paramiko.SFTPClient
    """
    ssh = paramiko.SSHClient()
    # Always load the operator's ``~/.ssh/known_hosts`` first — this is what
    # makes strict verification meaningful for the common single-user case.
    ssh.load_system_host_keys()
    # Optionally trust an extra known_hosts file (e.g. a project-pinned key)
    # when the caller supplied one. ``emptystring`` guards against "" / None.
    extra_known_hosts = cred.get("sftp_known_hosts")
    if not osh.emptystring(extra_known_hosts):
        ssh.load_host_keys(extra_known_hosts)
    # RejectPolicy is the whole point of this wrapper: an unknown host key is
    # a hard failure, never a silent "auto-add". There is no opt-out flag.
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())

    # Prefer explicit password auth, but treat an empty password as "unset"
    # so paramiko falls through to the SSH agent / default identity files.
    password = cred.get("sftp_passwd")
    if osh.emptystring(password):
        password = None

    try:
        ssh.connect(
            hostname=cred["sftp_host"],
            port=int(cred.get("sftp_port") or 22),
            username=cred["sftp_login"],
            password=password,
            look_for_keys=True,
            allow_agent=True,
        )
    except Exception as err:
        # Close the transport before re-raising so a failed connect never
        # leaks a half-open socket, and surface a message that names the
        # target (login@host) to make debugging misconfigured creds quick.
        ssh.close()
        target = f"sftp://{cred['sftp_login']}@{cred['sftp_host']}"
        raise Exception(f"Failed to establish SFTP connection:\n\t{target}\nError: {err}") from err

    sftp = ssh.open_sftp()
    try:
        # Hand the live SFTP channel to the caller for the duration of the
        # ``with`` block.
        yield sftp
    finally:
        # Nested try/finally guarantees the underlying SSH transport is closed
        # even if closing the SFTP channel itself raises — no leaked sockets.
        try:
            sftp.close()
        finally:
            ssh.close()


def normalize_path(path: str) -> str:
    """Normalize a remote path: ensure single leading '/', strip trailing slashes.

    Parameters
    ----------
    path : str
        A raw remote path, possibly missing the leading slash or carrying
        redundant trailing slashes.

    Returns
    -------
    str
        The canonical form (single leading '/', no trailing '/'); the root
        ``"/"`` is preserved rather than collapsed to the empty string.

    Examples
    --------
    >>> normalize_path("foo/bar///")
    '/foo/bar'
    """
    # Guarantee an absolute-looking path so downstream string comparisons and
    # ``sftp://host`` stripping behave predictably.
    if not path.startswith("/"):
        path = "/" + path
    # Drop trailing slashes, but fall back to "/" so the root never becomes "".
    return path.rstrip("/") or "/"


def strip_sftp_path(sftp_address: str, cred: dict) -> str:
    """
    Strip ``sftp://`` and the host from an SFTP address.

    Idempotent: passing an already-stripped path returns it unchanged
    (modulo normalization).

    Parameters
    ----------
    sftp_address : str
        Either a full ``sftp://host/path`` address or a plain remote path.
    cred : dict
        Credentials dict; only ``cred["sftp_host"]`` is read, to know which
        host token to remove.

    Returns
    -------
    str
        The normalized remote path with scheme and host removed.
    """
    # Remove the scheme and the host token so what remains is a plain remote
    # path. Doing both replacements makes the function idempotent: a path that
    # was already stripped has nothing left to remove.
    stripped = sftp_address.replace("sftp://", "").replace(cred["sftp_host"], "")
    return normalize_path(stripped)


def _sftp_exists(sftp: paramiko.SFTPClient, remote_path: str) -> bool:
    """Return whether ``remote_path`` exists on an open SFTP channel.

    Parameters
    ----------
    sftp : paramiko.SFTPClient
        An already-open SFTP client.
    remote_path : str
        Absolute remote path to probe.

    Returns
    -------
    bool
        ``True`` if a ``stat`` call succeeds, ``False`` if the server reports
        the path as missing.
    """
    # ``stat`` is the cheapest existence probe: success means "present",
    # FileNotFoundError means "absent". Any other error is a real fault and is
    # allowed to propagate to the caller.
    try:
        sftp.stat(remote_path)
        return True
    except FileNotFoundError:
        return False


def _sftp_isdir(sftp: paramiko.SFTPClient, remote_path: str) -> bool:
    """Return whether ``remote_path`` exists *and* is a directory.

    Parameters
    ----------
    sftp : paramiko.SFTPClient
        An already-open SFTP client.
    remote_path : str
        Absolute remote path to probe.

    Returns
    -------
    bool
        ``True`` only when the path exists and its mode bits mark it a
        directory; ``False`` when it is missing or is a plain file.
    """
    # Inspect the POSIX mode bits from ``stat`` to distinguish a directory from
    # a regular file. A missing path is simply "not a directory".
    try:
        return stat_mod.S_ISDIR(sftp.stat(remote_path).st_mode)
    except FileNotFoundError:
        return False


def remote_file_exists(sftp_address: str, cred: dict) -> bool:
    """Return True iff the remote path exists.

    Parameters
    ----------
    sftp_address : str
        Full ``sftp://`` address or a plain remote path.
    cred : dict
        Credentials dict passed straight to :func:`get_client_sftp`.

    Returns
    -------
    bool
        Whether the remote file exists.

    Raises
    ------
    Exception
        Wrapped with the address if the connection or probe fails.
    """
    # Normalize the address to a plain remote path before opening a connection.
    remote_path = strip_sftp_path(sftp_address, cred)
    try:
        # One short-lived connection per call keeps the API stateless; the
        # context manager guarantees the transport is torn down afterwards.
        with get_client_sftp(cred) as sftp:
            exists = _sftp_exists(sftp, remote_path)
            osh.info(f"SFTP file {sftp_address} existence check: {exists}")
            return exists
    except Exception as err:
        # Re-wrap with the address so the caller sees *which* file failed.
        raise Exception(
            f"Failed to check SFTP file existence for {sftp_address}.\nError: {err}"
        ) from err


def remote_dir_exist(ftp_dir: str, cred: dict) -> bool:
    """Return True iff the remote directory exists.

    Parameters
    ----------
    ftp_dir : str
        Full ``sftp://`` address or a plain remote directory path.
    cred : dict
        Credentials dict passed straight to :func:`get_client_sftp`.

    Returns
    -------
    bool
        Whether the remote path exists and is a directory.
    """
    # Normalize first, then probe over a short-lived connection.
    remote_path = strip_sftp_path(ftp_dir, cred)
    with get_client_sftp(cred) as sftp:
        return _sftp_isdir(sftp, remote_path)


def make_remote_directory(ftp_directory: str, cred: dict) -> None:
    """Ensure the specified remote directory exists, creating intermediate levels as needed.

    Parameters
    ----------
    ftp_directory : str
        Full ``sftp://`` address or a plain remote directory path. Every
        missing intermediate level is created (``mkdir -p`` semantics).
    cred : dict
        Credentials dict passed straight to :func:`get_client_sftp`.

    Raises
    ------
    AssertionError
        If the target directory is still absent after the create loop.
    """
    target = strip_sftp_path(ftp_directory, cred)
    # Split into non-empty path components so we can create them one level at a
    # time. An empty ``parts`` means the target was the root — nothing to do.
    parts = [p for p in target.split("/") if p]
    if not parts:
        return

    with get_client_sftp(cred) as sftp:
        # Fast path: the whole directory already exists, skip the create loop.
        if _sftp_isdir(sftp, target):
            osh.info(f"Directory already exists: {ftp_directory}")
            return
        # Walk from the root down, creating only the levels that are missing.
        # ``current`` accumulates the path prefix as we descend.
        current = ""
        for part in parts:
            current = f"{current}/{part}"
            if not _sftp_isdir(sftp, current):
                sftp.mkdir(current)
        # Post-condition: re-stat the full target so a partial/racy failure
        # surfaces loudly with the exact level we stopped at.
        assert _sftp_isdir(sftp, target), (
            f"Remote directory creation failed:\n\t{ftp_directory}\n\t(stopped at {current})"
        )


def delete(sftp_address: str, cred: dict) -> bool:
    """
    Delete a remote file. Returns True if the file is gone afterwards
    (including the case where it never existed).

    Parameters
    ----------
    sftp_address : str
        Full ``sftp://`` address or a plain remote path.
    cred : dict
        Credentials dict passed straight to :func:`get_client_sftp`.

    Returns
    -------
    bool
        Always ``True`` on success — deleting an absent file is a no-op, which
        makes the operation idempotent.

    Raises
    ------
    Exception
        Wrapped with the address if the connection or removal fails.
    """
    remote_path = strip_sftp_path(sftp_address, cred)
    try:
        with get_client_sftp(cred) as sftp:
            # Idempotency: a missing target is treated as "already deleted"
            # rather than an error, so retries and cleanup paths stay simple.
            if not _sftp_exists(sftp, remote_path):
                osh.info(f"SFTP remote file {remote_path} does not exist, skipping deletion.")
                return True
            sftp.remove(remote_path)
            # Confirm the removal actually took effect before reporting success.
            assert not _sftp_exists(sftp, remote_path), (
                f"Failed to delete {sftp_address} on SFTP server."
            )
            osh.info(f"SFTP file {sftp_address} successfully deleted.")
            return True
    except Exception as err:
        # Re-wrap so the caller sees which file failed and the underlying cause.
        raise Exception(f"Failed to delete SFTP file:\n\t{sftp_address}.\nError:\n\t{err}") from err


def _progress_callback(bar: Any) -> Callable[[int, int], None]:
    """Adapt paramiko's cumulative transfer callback to a delta-based tqdm bar.

    paramiko's ``put`` / ``get`` invoke their ``callback`` with
    ``(bytes_transferred_so_far, bytes_total)`` — a *running total*, not a delta.
    :func:`os_helper.progress_bar` (tqdm) advances by *increments*, so this returns
    a closure that feeds it the difference since the last call (``bar.n`` is the
    bar's current position), giving a correct byte-scaled progress bar for either
    direction.

    Parameters
    ----------
    bar : tqdm.tqdm
        The progress bar to advance (from :func:`os_helper.progress_bar`).

    Returns
    -------
    Callable[[int, int], None]
        A ``callback(transferred, total)`` to hand to paramiko ``put`` / ``get``.
    """

    def _cb(transferred: int, total: int) -> None:
        """Advance the bar by the bytes moved since the previous callback."""
        # paramiko reports cumulative bytes; tqdm wants the delta since bar.n.
        bar.update(transferred - bar.n)

    return _cb


def upload(local_path: str, cred: dict, sftp_address: str = "") -> str:
    """
    Upload a local file to the SFTP server.

    If ``sftp_address`` is empty, a content-hashed name under
    ``cred['sftp_destination_path']`` is used.

    Parameters
    ----------
    local_path : str
        Path to the local file to upload.
    cred : dict
        Credentials dict passed straight to :func:`get_client_sftp`.
    sftp_address : str, optional
        Destination address. When empty, a deterministic content-hashed name
        is generated so identical files map to the same remote path.

    Returns
    -------
    str
        The full ``sftp://`` address (or plain remote path) of the file.

    Raises
    ------
    Exception
        Wrapped with both paths if the connection or transfer fails.
    """
    # No explicit destination: derive a stable, collision-resistant name from
    # the file's content hash (plus date) so re-uploading the same bytes is
    # deterministic and de-duplicated by the server-side path.
    if osh.emptystring(sftp_address):
        _, _, ext = osh.folder_name_ext(local_path)
        h = osh.hashfile(local_path, hash_content=True, date=True)
        sftp_address = f"{cred['sftp_destination_path']}/{h}.{ext}"

    remote_path = strip_sftp_path(sftp_address, cred)
    # Snapshot the local timestamps up front so we can mirror them onto the
    # remote copy after the transfer (see ``utime`` below).
    local_stat = os.stat(local_path)
    try:
        with get_client_sftp(cred) as sftp:
            # Remove any stale copy first: ``put`` would overwrite, but an
            # explicit remove keeps the semantics obvious and avoids partial
            # writes lingering under a different size.
            if _sftp_exists(sftp, remote_path):
                sftp.remove(remote_path)
            # ``confirm=True`` re-stats after the put so paramiko verifies the
            # byte count landed — cheap integrity check on the transfer. The
            # shared bar (total = local size) shows live progress on big files.
            with osh.progress_bar(
                total=local_stat.st_size, desc=os.path.basename(remote_path)
            ) as bar:
                sftp.put(
                    local_path, remote_path, callback=_progress_callback(bar), confirm=True
                )
            # Preserve the original modification time so tooling that keys off
            # mtime (rsync-like sync, caches) sees a faithful copy.
            sftp.utime(remote_path, (local_stat.st_atime, local_stat.st_mtime))
            assert _sftp_exists(sftp, remote_path), f"Upload failed for {sftp_address}"
            osh.info(f"Upload successful: {local_path} -> {sftp_address}")
            return sftp_address
    except Exception as err:
        # Re-wrap with both endpoints so failures are self-describing.
        raise Exception(
            f"Upload failed:\n\t{local_path}\n\t->{sftp_address}.\nError:\n\t{err}"
        ) from err


def download(sftp_address: str, cred: dict, local_path: str = "") -> str:
    """
    Download a remote SFTP file to ``local_path`` (defaults to the remote basename).

    Parameters
    ----------
    sftp_address : str
        Full ``sftp://`` address or a plain remote path to fetch.
    cred : dict
        Credentials dict passed straight to :func:`get_client_sftp`.
    local_path : str, optional
        Destination on the local disk. Defaults to the remote basename.

    Returns
    -------
    str
        The local path of the downloaded file.

    Raises
    ------
    Exception
        Wrapped with both paths if the connection or transfer fails.
    """
    remote_path = strip_sftp_path(sftp_address, cred)
    # No local destination given: mirror the remote file name into the CWD.
    if osh.emptystring(local_path):
        local_path = remote_path.split("/")[-1]

    try:
        with get_client_sftp(cred) as sftp:
            # Stat first: its size gives the progress bar a total (and ETA), and
            # the same result mirrors the remote mtime/atime onto the local file
            # below — so the download is timestamp-faithful, as ``upload`` is.
            remote_stat = sftp.stat(remote_path)
            with osh.progress_bar(
                total=remote_stat.st_size, desc=os.path.basename(remote_path)
            ) as bar:
                sftp.get(remote_path, local_path, callback=_progress_callback(bar))
            os.utime(local_path, (remote_stat.st_atime, remote_stat.st_mtime))
            # Assert the file actually materialized before reporting success.
            osh.checkfile(local_path, msg=f"Download failed for {sftp_address}")
            osh.info(f"Download successful: {sftp_address} -> {local_path}")
            return local_path
    except Exception as err:
        # Re-wrap with both endpoints so failures are self-describing.
        raise Exception(
            f"Download failed:\n\t{sftp_address}\n\t->{local_path}.\nError:\n\t{err}"
        ) from err


@contextmanager
def remote_tempfile(
    cred: dict,
    ext: str = "",
    subdir: str = "",
) -> Iterator[tuple[str, str]]:
    """
    Reserve a unique remote path under ``cred['sftp_destination_path']`` and
    delete it on exit.

    Parameters
    ----------
    cred : dict
        Credentials dict passed straight to :func:`get_client_sftp`.
    ext : str, optional
        File extension for the reserved name (with or without the leading dot).
    subdir : str, optional
        Subdirectory under ``sftp_destination_path``; created if missing.

    Yields
    ------
    (sftp_address, https_url)
        The reserved remote location -- the file does *not* exist yet; the
        caller is expected to upload to it (or skip entirely, in which case
        cleanup is a no-op).

    Cleanup
    -------
    The remote file is deleted in ``finally``. Cleanup failures re-raise only
    if no other exception is already propagating; otherwise they are logged
    so the original error survives.

    Example
    -------
    >>> with remote_tempfile(cred, ext="txt") as (addr, url):
    ...     upload("local.txt", cred, addr)
    ...     assert osh.is_working_url(url)
    """
    # 128 bits of randomness makes an accidental collision on the reserved
    # name effectively impossible, so two concurrent callers never clash.
    name = secrets.token_hex(16)
    if not osh.emptystring(ext):
        # Accept both "txt" and ".txt" from callers.
        name = f"{name}.{ext.lstrip('.')}"

    # Build the remote and HTTPS bases in lock-step so the returned address and
    # URL always point at the same object.
    base_remote = cred["sftp_destination_path"].rstrip("/")
    base_https = cred["sftp_https"].rstrip("/")
    if not osh.emptystring(subdir):
        # A subdir must exist server-side before we hand out a path under it,
        # otherwise the caller's upload would fail on a missing parent.
        clean_sub = subdir.strip("/")
        base_remote = f"{base_remote}/{clean_sub}"
        base_https = f"{base_https}/{clean_sub}"
        make_remote_directory(base_remote, cred)

    sftp_address = f"{base_remote}/{name}"
    url = f"{base_https}/{name}"

    try:
        # Hand the reserved coordinates to the caller. The file does not exist
        # yet — the caller is expected to upload to it inside the block.
        yield sftp_address, url
    except BaseException:
        # An error is propagating out of the with-block. Attempt cleanup, but
        # never let a cleanup failure mask the original exception: log it and
        # re-raise the user's error unchanged.
        try:
            delete(sftp_address, cred)
        except Exception as cleanup_err:
            osh.warning(
                f"remote_tempfile cleanup failed for {sftp_address} during error propagation: {cleanup_err}"
            )
        raise
    else:
        # Normal exit: remove the reserved file so it truly behaves like a
        # temporary. A no-op when the caller never uploaded anything.
        delete(sftp_address, cred)
