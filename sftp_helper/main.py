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

import logging
import os
import secrets
import stat as stat_mod
from contextlib import contextmanager
from typing import Iterator, Optional, Tuple

import os_helper as osh
import paramiko


def credentials(config_path: Optional[str] = None) -> dict:
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
    ssh.load_system_host_keys()
    extra_known_hosts = cred.get("sftp_known_hosts")
    if not osh.emptystring(extra_known_hosts):
        ssh.load_host_keys(extra_known_hosts)
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())

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
        ssh.close()
        target = f"sftp://{cred['sftp_login']}@{cred['sftp_host']}"
        raise Exception(f"Failed to establish SFTP connection:\n\t{target}\nError: {err}") from err

    sftp = ssh.open_sftp()
    try:
        yield sftp
    finally:
        try:
            sftp.close()
        finally:
            ssh.close()


def normalize_path(path: str) -> str:
    """Normalize a remote path: ensure single leading '/', strip trailing slashes."""
    if not path.startswith("/"):
        path = "/" + path
    return path.rstrip("/") or "/"


def strip_sftp_path(sftp_address: str, cred: dict) -> str:
    """
    Strip ``sftp://`` and the host from an SFTP address.

    Idempotent: passing an already-stripped path returns it unchanged
    (modulo normalization).
    """
    stripped = sftp_address.replace("sftp://", "").replace(cred["sftp_host"], "")
    return normalize_path(stripped)


def _sftp_exists(sftp: paramiko.SFTPClient, remote_path: str) -> bool:
    try:
        sftp.stat(remote_path)
        return True
    except FileNotFoundError:
        return False


def _sftp_isdir(sftp: paramiko.SFTPClient, remote_path: str) -> bool:
    try:
        return stat_mod.S_ISDIR(sftp.stat(remote_path).st_mode)
    except FileNotFoundError:
        return False


def remote_file_exists(sftp_address: str, cred: dict) -> bool:
    """Return True iff the remote path exists."""
    remote_path = strip_sftp_path(sftp_address, cred)
    try:
        with get_client_sftp(cred) as sftp:
            exists = _sftp_exists(sftp, remote_path)
            logging.info(f"SFTP file {sftp_address} existence check: {exists}")
            return exists
    except Exception as err:
        raise Exception(f"Failed to check SFTP file existence for {sftp_address}.\nError: {err}") from err


def remote_dir_exist(ftp_dir: str, cred: dict) -> bool:
    """Return True iff the remote directory exists."""
    remote_path = strip_sftp_path(ftp_dir, cred)
    with get_client_sftp(cred) as sftp:
        return _sftp_isdir(sftp, remote_path)


def make_remote_directory(ftp_directory: str, cred: dict) -> None:
    """Ensure the specified remote directory exists, creating intermediate levels as needed."""
    target = strip_sftp_path(ftp_directory, cred)
    parts = [p for p in target.split("/") if p]
    if not parts:
        return

    with get_client_sftp(cred) as sftp:
        if _sftp_isdir(sftp, target):
            logging.info(f"Directory already exists: {ftp_directory}")
            return
        current = ""
        for part in parts:
            current = f"{current}/{part}"
            if not _sftp_isdir(sftp, current):
                sftp.mkdir(current)
        assert _sftp_isdir(sftp, target), (
            f"Remote directory creation failed:\n\t{ftp_directory}\n\t(stopped at {current})"
        )


def delete(sftp_address: str, cred: dict) -> bool:
    """
    Delete a remote file. Returns True if the file is gone afterwards
    (including the case where it never existed).
    """
    remote_path = strip_sftp_path(sftp_address, cred)
    try:
        with get_client_sftp(cred) as sftp:
            if not _sftp_exists(sftp, remote_path):
                logging.info(f"SFTP remote file {remote_path} does not exist, skipping deletion.")
                return True
            sftp.remove(remote_path)
            assert not _sftp_exists(sftp, remote_path), (
                f"Failed to delete {sftp_address} on SFTP server."
            )
            logging.info(f"SFTP file {sftp_address} successfully deleted.")
            return True
    except Exception as err:
        raise Exception(f"Failed to delete SFTP file:\n\t{sftp_address}.\nError:\n\t{err}") from err


def upload(local_path: str, cred: dict, sftp_address: str = "") -> str:
    """
    Upload a local file to the SFTP server.

    If ``sftp_address`` is empty, a content-hashed name under
    ``cred['sftp_destination_path']`` is used.

    Returns
    -------
    str
        The full ``sftp://`` address of the uploaded file.
    """
    if osh.emptystring(sftp_address):
        _, _, ext = osh.folder_name_ext(local_path)
        h = osh.hashfile(local_path, hash_content=True, date=True)
        sftp_address = f"{cred['sftp_destination_path']}/{h}.{ext}"

    remote_path = strip_sftp_path(sftp_address, cred)
    local_stat = os.stat(local_path)
    try:
        with get_client_sftp(cred) as sftp:
            if _sftp_exists(sftp, remote_path):
                sftp.remove(remote_path)
            sftp.put(local_path, remote_path, confirm=True)
            sftp.utime(remote_path, (local_stat.st_atime, local_stat.st_mtime))
            assert _sftp_exists(sftp, remote_path), f"Upload failed for {sftp_address}"
            logging.info(f"Upload successful: {local_path} -> {sftp_address}")
            return sftp_address
    except Exception as err:
        raise Exception(f"Upload failed:\n\t{local_path}\n\t->{sftp_address}.\nError:\n\t{err}") from err


def download(sftp_address: str, cred: dict, local_path: str = "") -> str:
    """
    Download a remote SFTP file to ``local_path`` (defaults to the remote basename).

    Returns
    -------
    str
        The local path of the downloaded file.
    """
    remote_path = strip_sftp_path(sftp_address, cred)
    if osh.emptystring(local_path):
        local_path = remote_path.split("/")[-1]

    try:
        with get_client_sftp(cred) as sftp:
            sftp.get(remote_path, local_path)
            remote_stat = sftp.stat(remote_path)
            os.utime(local_path, (remote_stat.st_atime, remote_stat.st_mtime))
            osh.checkfile(local_path, msg=f"Download failed for {sftp_address}")
            logging.info(f"Download successful: {sftp_address} -> {local_path}")
            return local_path
    except Exception as err:
        raise Exception(f"Download failed:\n\t{sftp_address}\n\t->{local_path}.\nError:\n\t{err}") from err


@contextmanager
def remote_tempfile(
    cred: dict,
    ext: str = "",
    subdir: str = "",
) -> Iterator[Tuple[str, str]]:
    """
    Reserve a unique remote path under ``cred['sftp_destination_path']`` and
    delete it on exit.

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
    name = secrets.token_hex(16)
    if not osh.emptystring(ext):
        name = f"{name}.{ext.lstrip('.')}"

    base_remote = cred["sftp_destination_path"].rstrip("/")
    base_https = cred["sftp_https"].rstrip("/")
    if not osh.emptystring(subdir):
        clean_sub = subdir.strip("/")
        base_remote = f"{base_remote}/{clean_sub}"
        base_https = f"{base_https}/{clean_sub}"
        make_remote_directory(base_remote, cred)

    sftp_address = f"{base_remote}/{name}"
    url = f"{base_https}/{name}"

    try:
        yield sftp_address, url
    except BaseException:
        try:
            delete(sftp_address, cred)
        except Exception as cleanup_err:
            logging.warning(
                f"remote_tempfile cleanup failed for {sftp_address} during error propagation: {cleanup_err}"
            )
        raise
    else:
        delete(sftp_address, cred)
