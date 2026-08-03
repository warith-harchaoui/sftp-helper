"""
SFTP Helper

This module provides functions to interact with an SFTP server, allowing users
to perform file uploads, downloads, and deletions, as well as to check file
existence remotely.

Backed by the system OpenSSH client (the ``sftp`` binary driven in batch mode
via ``os_helper.system``) rather than an in-process SSH library. This is a
deliberate choice: OpenSSH is the reference SSH implementation, ships on macOS,
Linux and Windows 10+/Server 2019+, and — crucially — authenticates exactly the
way the operator's own ``ssh`` / ``sftp`` commands do. In particular it honours
the SSH agent and lets ``sftp_key`` point at either a private key *or* its
``.pub`` companion (delegating the signature to the agent / a hardware token),
which an in-process library cannot do.

Host key verification is on by default and cannot be disabled: every invocation
passes ``StrictHostKeyChecking=yes``, so a host whose key is not already in
``~/.ssh/known_hosts`` is rejected. A caller who wants to trust an additional
store may point ``cred["sftp_known_hosts"]`` at an extra known_hosts file.

The command is identical on every OS, so there is no per-platform branching:
the only cross-platform concern is whether the ``sftp`` binary is installed,
which is checked once, up front, with a clear error message.

Author:
- Warith HARCHAOUI (https://linkedin.com/in/warith-harchaoui)
"""

# ``from __future__ import annotations`` keeps every annotation a lazy string
# so the modern ``X | None`` / ``tuple[...]`` spellings evaluate on any of the
# supported interpreters (3.10+) without importing them at runtime.
from __future__ import annotations

import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager, suppress

import os_helper as osh

# Diagnostics go through os-helper's logging surface (``osh.info`` /
# ``osh.warning``) rather than the stdlib logger or bare ``print``. This is
# the suite-wide convention: every helper package funnels its verbosity
# through the same os-helper channel so applications tune it in one place.

# The external binaries this module drives. OpenSSH ships both on macOS, most
# Linux distributions, and Windows 10 1809+ / Server 2019+; the command lines
# are byte-for-byte identical across all three, so the only portability question
# is "is it on PATH", answered by :func:`_require_sftp_binary`. ``sftp`` (batch
# mode) runs every operation; ``scp`` is used only for the optional live
# progress bar (see :func:`_send`), because — unlike ``sftp -b`` — it emits a
# transfer meter we can translate into ``os_helper.progress_bar`` updates.
_SFTP_BIN = "sftp"
_SCP_BIN = "scp"

# Matches the ``NN%`` token in an OpenSSH transfer meter line, e.g.
# ``clip.mp4  42% 12MB  1.2MB/s  00:07``. That percentage is all we need to
# drive a byte-accurate progress bar against a known total.
_PERCENT_RE = re.compile(rb"(\d+)%")

# Substrings that mark a *connection / authentication* failure in OpenSSH's
# (English, never localized) stderr — as opposed to a per-file error such as
# "No such file". These are used to tell "the server said the file is missing"
# apart from "we never reached the server", so an existence probe never reports
# a dead connection as "file absent". The trailing "(" on the permission-denied
# markers scopes them to the auth phase: a *file* permission error reads
# "Couldn't delete file: Permission denied" (no paren) and must not be
# misclassified as an auth failure, since by then we are already connected.
_CONNECT_ERROR_MARKERS = (
    "Permission denied (",
    "Permission denied, please try again",
    "Host key verification failed",
    "Could not resolve hostname",
    "Name or service not known",
    "Connection refused",
    "Connection timed out",
    "Connection closed",
    "Connection reset",
    "No route to host",
    "Network is unreachable",
    "kex_exchange_identification",
    "Too many authentication failures",
    "no matching host key type",
    "Bad configuration option",
    "Operation timed out",
)

# Substrings that mark a benign "the path is simply not there" result. Seeing
# one of these lets an existence / directory probe answer ``False`` with
# confidence instead of raising.
_NOT_FOUND_MARKERS = (
    "No such file or directory",
    "not found",
    "Couldn't stat",
    "Can't ls",
    "Not a directory",
)


# Only these three identify a reachable, addressable target: where to connect
# (host), as whom (login), and which public URL a remote file maps to
# (https, used to hand back shareable links). Everything else — how to
# authenticate and where to write — has a sensible default, so it is resolved
# separately as optional below.
_REQUIRED_KEYS = ["sftp_host", "sftp_login", "sftp_https"]

# Optional credentials, each with a documented fallback:
#   sftp_passwd            empty  -> authenticate with a key / the SSH agent
#   sftp_key               unset  -> the SSH agent + default identities
#   sftp_destination_path  empty  -> the server root "/"
#   sftp_port              unset  -> 22
#   sftp_known_hosts       unset  -> rely on ~/.ssh/known_hosts alone
_OPTIONAL_KEYS = [
    "sftp_passwd",
    "sftp_key",
    "sftp_destination_path",
    "sftp_port",
    "sftp_known_hosts",
]


def credentials(config_path: str | None = None) -> dict:
    """
    Retrieve SFTP credentials from a configuration file, folder, or environment.

    Only ``sftp_host``, ``sftp_login`` and ``sftp_https`` are mandatory.
    Authentication (``sftp_passwd`` / ``sftp_key``) and the write location
    (``sftp_destination_path``, default ``"/"``) are optional and fall back to
    documented defaults — so a key-based login writing to the server root needs
    just the three required fields.

    Parameters
    ----------
    config_path : str
        Path to a JSON/YAML file, a directory containing one, or ``None`` to
        fall back to environment variables / ``.env``.

    Returns
    -------
    dict
        Dictionary with the three required keys always present, plus whichever
        optional keys were supplied. ``sftp_destination_path`` is always set
        (defaulting to ``"/"``).
    """
    # ``osh.get_config`` resolves the required trio from (in order) an explicit
    # file, a directory containing one, then env vars / ``.env`` — and raises
    # if none of those sources provides the full set, so callers never get a
    # half-populated credentials dict.
    cred = osh.get_config(_REQUIRED_KEYS, "SFTP", config_path)

    # Backfill optional keys. A file-sourced config already carries every key it
    # declared (``get_config`` returns the whole parsed dict), so this only ever
    # adds anything for env-var / ``.env`` setups — where ``get_config`` returns
    # just the requested keys. ``get_config`` has already merged any ``.env``
    # into ``os.environ`` by now, so reading the environment here is safe.
    for key in _OPTIONAL_KEYS:
        if key in cred:
            continue
        value = os.environ.get(key.upper(), os.environ.get(key))
        if value is not None:
            cred[key] = value

    # The destination path is optional: an empty or absent value means "write
    # under the server root". Pin it so downstream code can always read it.
    if osh.emptystring(cred.get("sftp_destination_path")):
        cred["sftp_destination_path"] = "/"

    return cred


def _require_sftp_binary() -> None:
    """Fail early, and clearly, when the OpenSSH ``sftp`` client is not installed.

    Raises
    ------
    Exception
        With an actionable message if ``sftp`` is not on ``PATH``. This is the
        only genuinely OS-dependent concern — the command itself is identical
        everywhere — so it is worth its own explicit, friendly failure.
    """
    if shutil.which(_SFTP_BIN) is None:
        raise Exception(
            "The OpenSSH 'sftp' client was not found on PATH. Install it "
            "(macOS/Linux: usually preinstalled or via your package manager's "
            "'openssh-clients'; Windows: enable the 'OpenSSH Client' optional "
            "feature) and try again."
        )


def _target(cred: dict) -> str:
    """Return the ``login@host`` token that names the SFTP endpoint."""
    return f"{cred['sftp_login']}@{cred['sftp_host']}"


def _password_prefix(cred: dict) -> tuple[list[str], dict[str, str], bool]:
    """Return the ``sshpass`` argv prefix + env for password auth (empty for key auth).

    Parameters
    ----------
    cred : dict
        Resolved credentials dict.

    Returns
    -------
    (prefix, env, use_password)
        ``prefix`` is ``["sshpass", "-e"]`` when a password is configured, else
        ``[]``. ``env`` carries ``SSHPASS`` (so the secret never appears in the
        argv / ``ps``). ``use_password`` reports which mode was chosen.

    Raises
    ------
    Exception
        If a password is configured but ``sshpass`` is not installed.
    """
    password = cred.get("sftp_passwd")
    if osh.emptystring(password):
        return [], {}, False
    # OpenSSH deliberately refuses to read a password from the CLI, so password
    # auth needs the ``sshpass`` shim. We feed the secret through the
    # environment (``sshpass -e`` reads ``$SSHPASS``) so it is never visible in
    # the argv.
    if shutil.which("sshpass") is None:
        raise Exception(
            "sftp_passwd is set but the 'sshpass' helper is not installed. "
            "Install sshpass, or (recommended) switch to SSH-key auth by "
            "setting sftp_key or loading your key into the SSH agent and "
            "leaving sftp_passwd empty."
        )
    return ["sshpass", "-e"], {"SSHPASS": str(password)}, True


def _ssh_options(cred: dict, *, batch_mode: str) -> list[str]:
    """Build the shared OpenSSH option tokens (port, identity, host-key policy).

    Parameters
    ----------
    cred : dict
        Resolved credentials dict.
    batch_mode : str
        ``"yes"`` for key/agent auth (no interactive prompt), ``"no"`` when a
        password prompt must stay open for ``sshpass`` to answer.

    Returns
    -------
    list[str]
        Option tokens shared by ``sftp`` and ``scp`` (both accept them verbatim).
    """
    # Port (uppercase -P for sftp/scp; lowercase -p means "preserve times").
    opts = ["-P", str(int(cred.get("sftp_port") or 22))]

    # Identity file. Passed verbatim so OpenSSH's native handling applies: the
    # path may be a private key or its ``.pub`` companion (in which case the
    # agent / a hardware token performs the signature). Absent -> OpenSSH falls
    # back to the agent and the default ~/.ssh identities.
    key = cred.get("sftp_key")
    if not osh.emptystring(key):
        opts += ["-i", os.path.expanduser(str(key))]

    # BatchMode avoids any interactive hang; strict host-key checking is the
    # non-negotiable security posture inherited from the paramiko era.
    opts += ["-o", f"BatchMode={batch_mode}", "-o", "StrictHostKeyChecking=yes"]

    # An extra known_hosts file is *added* to the defaults (kept explicit so we
    # do not accidentally drop the system store while trusting the extra one).
    extra = cred.get("sftp_known_hosts")
    if not osh.emptystring(extra):
        stores = f"~/.ssh/known_hosts ~/.ssh/known_hosts2 {os.path.expanduser(str(extra))}"
        opts += ["-o", f"UserKnownHostsFile={stores}"]

    return opts


def _sftp_argv(cred: dict) -> tuple[list[str], dict[str, str]]:
    """Build the ``sftp`` argv prefix (up to ``-b <batchfile>`` and the target)."""
    prefix, env, use_password = _password_prefix(cred)
    batch_mode = "no" if use_password else "yes"
    argv = [*prefix, _SFTP_BIN, *_ssh_options(cred, batch_mode=batch_mode)]
    return argv, env


def _run_sftp(cred: dict, commands: list[str], *, check: bool) -> dict:
    """Run a list of ``sftp`` batch commands against ``cred`` and capture output.

    Parameters
    ----------
    cred : dict
        Resolved credentials dict.
    commands : list[str]
        Interactive ``sftp`` commands (``put``, ``get``, ``rm``, ``mkdir``,
        ``ls``, ``cd`` ...). Prefix a command with ``-`` to ignore its own
        failure (used for idempotent ``-mkdir``).
    check : bool
        When ``True``, assert the process exited 0 (used for transfers where a
        non-zero exit is unambiguously a failure). When ``False``, return the
        captured output so the caller can classify a per-file error vs a
        connection error itself.

    Returns
    -------
    dict
        ``{"out": <stdout>, "err": <stderr>}`` as returned by ``os_helper.system``.
    """
    _require_sftp_binary()
    argv, env = _sftp_argv(cred)

    # ``sftp -b`` reads its command list from a file (not stdin), which keeps us
    # fully non-interactive and lets ``os_helper.system`` capture the result.
    # A trailing newline is required so the last command is executed.
    fd, batch_path = tempfile.mkstemp(prefix="sftp-helper-", suffix=".batch")
    try:
        with os.fdopen(fd, "w") as fout:
            fout.write("\n".join(commands) + "\n")
        argv += ["-b", batch_path, _target(cred)]

        # ``os_helper.system`` re-parses the command string with ``shlex.split``,
        # so quoting every token with ``shlex.quote`` round-trips our exact argv
        # back — spaces, ``@`` and option values survive intact.
        cmd = " ".join(shlex.quote(token) for token in argv)

        # ``os_helper.system`` inherits the current environment, so slot in the
        # password (if any) just for the duration of the call, then restore.
        saved = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        try:
            return osh.system(cmd, check_exitcode=check)
        finally:
            for k, previous in saved.items():
                if previous is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = previous
    finally:
        # The batch file may hold a remote path but never a secret; still, leave
        # nothing behind.
        os.remove(batch_path)


def _raise_if_connect_error(err: str, cred: dict, context: str) -> None:
    """Raise a descriptive error if ``err`` looks like a connection/auth failure.

    Parameters
    ----------
    err : str
        Captured stderr from an ``sftp`` invocation.
    cred : dict
        Credentials dict (only used to name the target in the message).
    context : str
        Short label for what was being attempted (e.g. ``"existence check"``).

    Raises
    ------
    Exception
        If ``err`` contains any connection/authentication marker.
    """
    if any(marker in err for marker in _CONNECT_ERROR_MARKERS):
        target = f"sftp://{_target(cred)}"
        raise Exception(f"{context} failed to reach {target}.\nError:\n\t{err.strip()}")


# ---------------------------------------------------------------------------
# Transfers (with an optional live progress bar)
# ---------------------------------------------------------------------------
#
# ``sftp -b`` is authoritative for correctness (reliable exit code + captured
# errors) but batch mode disables the transfer meter, so it can show no
# progress. To match the rest of the suite (``os_helper.download_file`` streams
# with a bar), an interactive terminal instead drives the transfer through
# ``scp`` under a pseudo-terminal and translates scp's native ``NN%`` meter into
# an ``os_helper.progress_bar``. Anywhere a bar would be noise or is impossible
# — output is not a TTY (CI, pipes), the platform has no pty (Windows), or
# password auth is in play — it falls back to the plain ``sftp -b`` transfer,
# exactly as ``download_file`` auto-suppresses its bar off a TTY.


def _scp_argv(cred: dict, src: str, dst: str) -> tuple[list[str], dict[str, str]]:
    """Build an ``scp`` argv for one transfer (``-p`` preserves times, like ``sftp``)."""
    prefix, env, use_password = _password_prefix(cred)
    batch_mode = "no" if use_password else "yes"
    argv = [*prefix, _SCP_BIN, "-p", *_ssh_options(cred, batch_mode=batch_mode), src, dst]
    return argv, env


def _can_progress(cred: dict) -> bool:
    """Return whether a live progress bar is possible for this transfer.

    True only on an interactive terminal, on a platform with pseudo-terminals
    (POSIX), with ``scp`` available and key/agent auth (a password would need to
    share the pty with ``sshpass``). Any False here means the caller uses the
    plain ``sftp -b`` path with no bar.
    """
    if not osh.emptystring(cred.get("sftp_passwd")):
        return False
    if not hasattr(os, "openpty"):
        return False
    if shutil.which(_SCP_BIN) is None:
        return False
    try:
        return bool(sys.stderr.isatty())
    except Exception:
        return False


def _remote_size(cred: dict, remote_path: str) -> int | None:
    """Best-effort remote file size (bytes) for the progress-bar total, or ``None``.

    Parses ``ls -l``; a parse miss just yields ``None`` (an open-ended bar), so
    this never fails a transfer.
    """
    try:
        res = _run_sftp(cred, [f'ls -l "{remote_path}"'], check=False)
        for line in res["out"].splitlines():
            parts = line.split()
            # A long-listing entry: mode string (starts -/d/l), links, owner,
            # group, size, ... — the size is the 5th field.
            if len(parts) >= 5 and parts[0][:1] in "-dl" and parts[4].isdigit():
                return int(parts[4])
    except Exception:
        pass
    return None


def _scp_pty(argv: list[str], env: dict[str, str], total: int | None, desc: str) -> tuple[int, str]:
    """Run ``scp`` under a pseudo-terminal, driving a progress bar from its meter.

    Parameters
    ----------
    argv : list[str]
        The full ``scp`` command.
    env : dict[str, str]
        Extra environment (unused for key auth; present for symmetry).
    total : int or None
        Total bytes when known (upload: local size; download: remote size). When
        ``None`` the bar is open-ended and simply advances to each reported
        percentage of an assumed 100.
    desc : str
        Progress-bar label (the file name).

    Returns
    -------
    (returncode, output)
        The process exit code and the combined stdout+stderr text (used to
        classify a failure).
    """
    import pty
    import select

    # A pty makes scp believe it talks to a terminal, so it emits its live
    # transfer meter (suppressed on a plain pipe). Both scp's stdout and stderr
    # are wired to the slave end; we read everything from the master.
    master, slave = pty.openpty()
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=slave,
        stderr=slave,
        close_fds=True,
        env={**os.environ, **env},
    )
    os.close(slave)

    bar_total = total if total else 100
    bar = osh.progress_bar(total=bar_total, desc=desc, unit="B" if total else "%")
    chunks: list[bytes] = []
    try:
        while True:
            try:
                ready, _, _ = select.select([master], [], [], 0.1)
            except (OSError, ValueError):
                break
            if ready:
                try:
                    data = os.read(master, 4096)
                except OSError:
                    break  # slave closed: child is done
                if not data:
                    break
                chunks.append(data)
                found = _PERCENT_RE.findall(data)
                if found:
                    pct = min(100, int(found[-1]))
                    target_n = bar_total * pct // 100
                    if target_n > bar.n:
                        bar.update(target_n - bar.n)
            elif proc.poll() is not None:
                break
    finally:
        with suppress(OSError):
            os.close(master)
        proc.wait()
        # Snap to full on success so the bar never lingers at 99%.
        if proc.returncode == 0 and bar.n < bar_total:
            bar.update(bar_total - bar.n)
        bar.close()

    return proc.returncode, b"".join(chunks).decode("utf-8", errors="replace")


def _send(cred: dict, local_path: str, remote_path: str, *, upload: bool, desc: str) -> None:
    """Transfer one file, with a live progress bar when the terminal allows it.

    Parameters
    ----------
    cred : dict
        Resolved credentials dict.
    local_path : str
        Local endpoint (source for upload, destination for download).
    remote_path : str
        Remote endpoint (destination for upload, source for download).
    upload : bool
        Direction: ``True`` sends local -> remote, ``False`` fetches remote -> local.
    desc : str
        Progress-bar label.

    Raises
    ------
    Exception
        On a connection/authentication failure or a transfer error.
    """
    _require_sftp_binary()
    context = "upload" if upload else "download"

    if _can_progress(cred):
        # scp path: a real byte bar, driven by scp's own meter.
        if upload:
            total: int | None = os.path.getsize(local_path)
            src, dst = local_path, f"{_target(cred)}:{remote_path}"
        else:
            total = _remote_size(cred, remote_path)
            src, dst = f"{_target(cred)}:{remote_path}", local_path
        argv, env = _scp_argv(cred, src, dst)
        returncode, output = _scp_pty(argv, env, total, desc=desc)
        if returncode == 0:
            return
        _raise_if_connect_error(output, cred, context)
        raise Exception(output.strip() or f"scp exited with status {returncode}")

    # Plain path: no bar, but authoritative exit code + error capture via sftp -b.
    if upload:
        command = f'put -p "{local_path}" "{remote_path}"'
    else:
        command = f'get -p "{remote_path}" "{local_path}"'
    res = _run_sftp(cred, [command], check=False)
    err = res["err"]
    if not osh.emptystring(err):
        _raise_if_connect_error(err, cred, context)
        raise Exception(err.strip())


@contextmanager
def get_client_sftp(cred: dict) -> Iterator[dict]:
    """Deprecated compatibility shim — validate the connection and yield ``cred``.

    The module used to hand back a live ``paramiko.SFTPClient``. Now every
    operation runs as its own short-lived ``sftp`` batch, so there is no
    persistent client object to expose. This context manager is kept only so
    older ``with get_client_sftp(cred) as ...:`` call sites keep importing; it
    performs a cheap connectivity check (an ``ls`` of the server root, which
    also validates auth and the host key) and yields the credentials dict.

    Yields
    ------
    dict
        The credentials dict, after a successful connection has been proven.

    Raises
    ------
    Exception
        If the server cannot be reached or authentication fails.
    """
    # A bare ``ls`` of the root exercises exactly the connect + auth + host-key
    # path without touching any user file, so a bad target fails loudly here.
    res = _run_sftp(cred, ['ls "/"'], check=False)
    _raise_if_connect_error(res["err"], cred, "connection")
    yield cred


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


def _sftp_exists(cred: dict, remote_path: str) -> bool:
    """Return whether ``remote_path`` exists on the server.

    Parameters
    ----------
    cred : dict
        Credentials dict.
    remote_path : str
        Absolute remote path to probe.

    Returns
    -------
    bool
        ``True`` if ``ls`` of the path succeeds, ``False`` if the server reports
        it missing.

    Raises
    ------
    Exception
        If the connection/auth fails, or the server returns an error we cannot
        confidently read as "missing".
    """
    # ``ls`` is the cheapest probe: on success it prints the entry (or a
    # directory's contents) with empty stderr; on a missing path it writes a
    # "No such file" error to stderr and exits non-zero.
    res = _run_sftp(cred, [f'ls "{remote_path}"'], check=False)
    err = res["err"]
    if osh.emptystring(err):
        return True
    if any(marker in err for marker in _NOT_FOUND_MARKERS):
        return False
    _raise_if_connect_error(err, cred, "existence check")
    # Some other, unexpected server error: surface it rather than guessing.
    raise Exception(f"Unexpected error probing {remote_path}:\n\t{err.strip()}")


def _sftp_isdir(cred: dict, remote_path: str) -> bool:
    """Return whether ``remote_path`` exists *and* is a directory.

    Parameters
    ----------
    cred : dict
        Credentials dict.
    remote_path : str
        Absolute remote path to probe.

    Returns
    -------
    bool
        ``True`` only when the path exists and is a directory; ``False`` when it
        is missing or is a plain file.

    Raises
    ------
    Exception
        If the connection/auth fails.
    """
    # ``cd`` is a clean directory test: it succeeds (empty stderr) only for a
    # directory, and fails for a file ("Not a directory") or a missing path.
    res = _run_sftp(cred, [f'cd "{remote_path}"'], check=False)
    err = res["err"]
    if osh.emptystring(err):
        return True
    _raise_if_connect_error(err, cred, "directory check")
    return False


def remote_file_exists(sftp_address: str, cred: dict) -> bool:
    """Return True iff the remote path exists.

    Parameters
    ----------
    sftp_address : str
        Full ``sftp://`` address or a plain remote path.
    cred : dict
        Credentials dict.

    Returns
    -------
    bool
        Whether the remote file exists.

    Raises
    ------
    Exception
        Wrapped with the address if the connection or probe fails.
    """
    remote_path = strip_sftp_path(sftp_address, cred)
    try:
        exists = _sftp_exists(cred, remote_path)
        osh.info(f"SFTP file {sftp_address} existence check: {exists}")
        return exists
    except Exception as err:
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
        Credentials dict.

    Returns
    -------
    bool
        Whether the remote path exists and is a directory.
    """
    remote_path = strip_sftp_path(ftp_dir, cred)
    return _sftp_isdir(cred, remote_path)


def make_remote_directory(ftp_directory: str, cred: dict) -> None:
    """Ensure the specified remote directory exists, creating intermediate levels as needed.

    Parameters
    ----------
    ftp_directory : str
        Full ``sftp://`` address or a plain remote directory path. Every
        missing intermediate level is created (``mkdir -p`` semantics).
    cred : dict
        Credentials dict.

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

    # Fast path: already there, skip the create round-trip entirely.
    if _sftp_isdir(cred, target):
        osh.info(f"Directory already exists: {ftp_directory}")
        return

    # Build one batch that creates every level from the root down. Each mkdir is
    # prefixed with ``-`` so an "already exists" on an intermediate level does
    # not abort the batch; a genuine connection failure still shows up in stderr.
    levels: list[str] = []
    current = ""
    for part in parts:
        current = f"{current}/{part}"
        levels.append(f'-mkdir "{current}"')
    res = _run_sftp(cred, levels, check=False)
    _raise_if_connect_error(res["err"], cred, "directory creation")

    # Post-condition: re-stat the full target so a real failure (e.g. a
    # permission problem the ``-`` prefix swallowed) surfaces loudly.
    assert _sftp_isdir(cred, target), f"Remote directory creation failed:\n\t{ftp_directory}"


def delete(sftp_address: str, cred: dict) -> bool:
    """
    Delete a remote file. Returns True if the file is gone afterwards
    (including the case where it never existed).

    Parameters
    ----------
    sftp_address : str
        Full ``sftp://`` address or a plain remote path.
    cred : dict
        Credentials dict.

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
        # ``rm`` (no ``-`` prefix) so a real removal failure is visible; we read
        # a "No such file" as success to keep the operation idempotent.
        res = _run_sftp(cred, [f'rm "{remote_path}"'], check=False)
        err = res["err"]
        if osh.emptystring(err) or any(m in err for m in _NOT_FOUND_MARKERS):
            osh.info(f"SFTP file {sftp_address} successfully deleted (or already absent).")
            return True
        _raise_if_connect_error(err, cred, "deletion")
        raise Exception(f"Failed to delete {sftp_address}:\n\t{err.strip()}")
    except Exception as err:
        raise Exception(f"Failed to delete SFTP file:\n\t{sftp_address}.\nError:\n\t{err}") from err


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
        Credentials dict.
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
    osh.checkfile(local_path, msg=f"Cannot upload missing local file: {local_path}")

    # No explicit destination: derive a stable, collision-resistant name from
    # the file's content hash (plus date) so re-uploading the same bytes is
    # deterministic and de-duplicated by the server-side path. ``rstrip`` keeps
    # the join clean when the base is the root ("/") or has a trailing slash.
    if osh.emptystring(sftp_address):
        _, _, ext = osh.folder_name_ext(local_path)
        h = osh.hashfile(local_path, hash_content=True, date=True)
        base = cred["sftp_destination_path"].rstrip("/")
        sftp_address = f"{base}/{h}.{ext}"

    remote_path = strip_sftp_path(sftp_address, cred)
    try:
        # Neither ``put`` nor ``scp`` creates missing parents, so ensure the
        # directory exists first. This makes upload robust to a fresh tree.
        parent = remote_path.rsplit("/", 1)[0]
        if parent and parent != remote_path:
            make_remote_directory(parent, cred)

        # Transfer (timestamp-preserving), with a live progress bar on a TTY.
        _send(cred, local_path, remote_path, upload=True, desc=os.path.basename(remote_path))
        osh.info(f"Upload successful: {local_path} -> {sftp_address}")
        return sftp_address
    except Exception as err:
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
        Credentials dict.
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
        # Timestamp-preserving fetch, with a live progress bar on a TTY.
        _send(cred, local_path, remote_path, upload=False, desc=os.path.basename(local_path))
        # Assert the file actually materialized before reporting success.
        osh.checkfile(local_path, msg=f"Download failed for {sftp_address}")
        osh.info(f"Download successful: {sftp_address} -> {local_path}")
        return local_path
    except Exception as err:
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
        Credentials dict.
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
