"""
SFTP Helper

This module provides functions to interact with an SFTP server, allowing users
to perform file uploads, downloads, and deletions, as well as to check file
existence remotely.

Backed by the system OpenSSH client (the ``sftp`` binary driven in batch mode
via ``os_helper.system``) rather than an in-process SSH library. This is a
deliberate choice: OpenSSH is the reference SSH implementation, it ships on
macOS, Linux and Windows 10+/Server 2019+, and it authenticates exactly the
way the operator's own ``ssh`` / ``sftp`` commands do, which matters most of
all. In particular it honours the SSH agent and lets ``sftp_key`` point at
your *public* key (the recommended value: ``~/.ssh/id_ed25519.pub``, letting
the agent or a hardware token perform the signature, so no private-key
material is ever named in the config) as readily as at a private key, which
an in-process library cannot do.

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

import hashlib
import os
import platform
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import os_helper as osh

# Diagnostics go through os-helper's logging surface (``osh.info`` /
# ``osh.warning``) rather than the stdlib logger or bare ``print``. This is
# the suite-wide convention: every helper package funnels its verbosity
# through the same os-helper channel so applications tune it in one place.

# The external binary this module drives. OpenSSH ships on macOS, most Linux
# distributions, and Windows 10 1809+ / Server 2019+; the command line is
# byte-for-byte identical across all three, so the only portability question
# is "is it on PATH", answered by :func:`_require_sftp_binary`. Every transfer
# runs through ``sftp -b`` (batch mode) using ``reput``/``reget`` — OpenSSH's
# own resume-upload / resume-download commands — so retries continue instead
# of restarting (see :func:`_upload_resumable` / :func:`_download_resumable`).
_SFTP_BIN = "sftp"

# Deterministic suffix for the temp remote path an upload transfers into
# before being atomically published (renamed) onto the real destination — see
# :func:`_upload_resumable`.
_UPLOAD_TMP_SUFFIX = ".sftp-helper-upload"

# How long an SSH ControlMaster connection (see :func:`_control_path`) stays
# alive after its last client detaches, before OpenSSH closes it on its own.
# Long enough to cover a bulk operation's realistic total duration even
# across several separate sftp-helper calls; short enough that an idle
# socket does not linger indefinitely.
_CONTROL_PERSIST = "10m"

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

# Characters that must never reach an ``sftp -b`` batch command or a remote
# ``ssh ... command`` string, because both are built by interpolating a path
# into an ``f'... "{path}" ...'`` template rather than through a proper
# argv-style API. A bare ``"`` breaks out of that quoting; ``\n``/``\r`` break
# out of the batch file's one-command-per-line format entirely, letting a
# crafted path smuggle in an extra sftp command (including ``!command``,
# OpenSSH sftp's local-shell escape) on the next line; ``\x00`` cannot appear
# in a real path at all and only ever signals a truncation attack.
_UNSAFE_PATH_CHARS = ("\n", "\r", "\x00", '"')


def _assert_safe_path(path: str, *, what: str) -> str:
    """Reject a path that could break out of an ``sftp``/``ssh`` command string.

    Parameters
    ----------
    path : str
        A remote or local path about to be interpolated into a quoted
        ``sftp -b`` batch command or a remote ``ssh`` exec string.
    what : str
        Short label for the error message (e.g. ``"remote path"``).

    Returns
    -------
    str
        ``path``, unchanged, once proven safe.

    Raises
    ------
    ValueError
        If `path` contains a newline, carriage return, NUL byte, or double
        quote — see :data:`_UNSAFE_PATH_CHARS`.
    """
    if any(ch in path for ch in _UNSAFE_PATH_CHARS):
        raise ValueError(
            f"Unsafe {what} (contains a newline, NUL byte, or double quote, any "
            f"of which could break out of an sftp/ssh command string): {path!r}"
        )
    return path


# Only these three identify a reachable, addressable target: where to connect
# (host), as whom (login), and which public URL a remote file maps to
# (https, used to hand back shareable links). Everything else — how to
# authenticate and where to write — has a sensible default, so it is resolved
# separately as optional below.
_REQUIRED_KEYS = ["sftp_host", "sftp_login", "sftp_https"]

# Optional credentials, each with a documented fallback:
#   sftp_passwd            empty  -> authenticate with a key / the SSH agent
#   sftp_key               unset  -> the SSH agent + default identities
#                                     (recommended value: your *public* key,
#                                     e.g. ~/.ssh/id_ed25519.pub — the agent /
#                                     token signs, so no private key is named)
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


def _install_hint(tool: str, *, apt: str, dnf: str, pacman: str, brew: str, windows: str) -> str:
    """Render a copy-pasteable install command for `tool`, picked by host OS.

    Parameters
    ----------
    tool : str
        Name of the missing binary, used only in the fallback line.
    apt, dnf, pacman : str
        Package-manager commands offered together on Linux (distro package
        managers cannot be told apart from ``platform.system()`` alone, so
        all three common ones are listed rather than guessed).
    brew : str
        Command offered on macOS (Homebrew).
    windows : str
        Command(s) offered on Windows (typically winget and/or a note about
        WSL, since some tools have no native Windows build).

    Returns
    -------
    str
        A single-line-per-option hint block, tailored to
        ``platform.system()`` (``"Darwin"``, ``"Linux"``, ``"Windows"``);
        a generic fallback line if the platform is none of those.
    """
    system = platform.system()
    if system == "Darwin":
        return f"macOS: {brew}"
    if system == "Linux":
        return f"Linux: {apt} (Debian/Ubuntu) | {dnf} (Fedora/RHEL) | {pacman} (Arch)"
    if system == "Windows":
        return f"Windows: {windows}"
    return f"Install '{tool}' via your platform's package manager."


def _require_sftp_binary() -> None:
    """Fail early, and clearly, when the OpenSSH ``sftp`` client is not installed.

    Raises
    ------
    Exception
        With an actionable, per-OS message if ``sftp`` is not on ``PATH``.
        The command itself is identical everywhere once installed; only
        *how you install it* differs, hence :func:`_install_hint`.
    """
    if shutil.which(_SFTP_BIN) is None:
        hint = _install_hint(
            "sftp",
            apt="sudo apt install openssh-client",
            dnf="sudo dnf install openssh-clients",
            pacman="sudo pacman -S openssh",
            brew="preinstalled on modern macOS; if missing, 'brew install openssh'",
            windows="Settings > Apps > Optional features > Add > 'OpenSSH Client' "
            "(or: Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0 in PowerShell as Administrator)",
        )
        raise Exception(f"The OpenSSH 'sftp' client was not found on PATH. {hint}")


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
        hint = _install_hint(
            "sshpass",
            apt="sudo apt install sshpass",
            dnf="sudo dnf install sshpass",
            pacman="sudo pacman -S sshpass",
            brew="'brew install hudochenkov/sshpass/sshpass' (sshpass is not in "
            "Homebrew core; that third-party tap builds it from source)",
            windows="no native sshpass build exists — use WSL (same as the Linux "
            "commands above) or switch to SSH-key auth (see below)",
        )
        raise Exception(
            "sftp_passwd is set but the 'sshpass' helper is not installed.\n"
            f"  {hint}\n"
            "  (recommended, works on every OS with no extra install): switch to "
            "SSH-key auth by setting sftp_key or loading your key into the SSH "
            "agent, and leaving sftp_passwd empty."
        )
    return ["sshpass", "-e"], {"SSHPASS": str(password)}, True


def _control_path(cred: dict) -> str:
    """Deterministic ControlMaster socket path for `cred`'s target.

    Parameters
    ----------
    cred : dict
        Resolved credentials dict.

    Returns
    -------
    str
        A path under the system temp directory (never ``~/.ssh/``: AF_UNIX
        socket paths are capped at ~104 bytes on macOS/BSD, and a temp-dir
        path stays comfortably short regardless of how long ``$HOME`` is).
        Keyed on host + login + port so distinct targets never collide on
        one socket, and stable across calls so repeated invocations against
        the same target in one run (or a short window after) attach to the
        same master connection instead of starting a new one.
    """
    key = f"{cred['sftp_login']}@{cred['sftp_host']}:{cred.get('sftp_port') or 22}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return str(Path(tempfile.gettempdir()) / f"sftp-helper-cm-{digest}.sock")


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

    # Identity file. Passed verbatim so OpenSSH's native handling applies. The
    # recommended value is the *public* key (``~/.ssh/id_ed25519.pub``): OpenSSH
    # then delegates the signature to the agent / a hardware token, so no
    # private-key material is ever named in the config. A private-key path is
    # equally accepted (read directly, for setups with no agent). Absent ->
    # OpenSSH falls back to the agent and the default ~/.ssh identities.
    key = cred.get("sftp_key")
    if not osh.emptystring(key):
        opts += ["-i", os.path.expanduser(str(key))]

    # BatchMode avoids any interactive hang; strict host-key checking is the
    # non-negotiable security posture inherited from the paramiko era;
    # ConnectTimeout bounds a dead host so a call never hangs indefinitely.
    opts += [
        "-o",
        f"BatchMode={batch_mode}",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=30",
    ]

    # An extra known_hosts file is *added* to the defaults (kept explicit so we
    # do not accidentally drop the system store while trusting the extra one).
    extra = cred.get("sftp_known_hosts")
    if not osh.emptystring(extra):
        stores = f"~/.ssh/known_hosts ~/.ssh/known_hosts2 {os.path.expanduser(str(extra))}"
        opts += ["-o", f"UserKnownHostsFile={stores}"]

    # Connection multiplexing: every _run_sftp call otherwise pays a full new
    # SSH handshake (TCP + key exchange + auth), which dominates the cost of
    # bulk operations — a directory walk or a many-file upload issues one
    # `sftp -b` invocation *per command*, not per file, so with N directories
    # or N files that is N handshakes. `ControlMaster=auto` makes the first
    # invocation in a run become a background master connection; every
    # subsequent invocation (any function, any call) attaches to it over the
    # local control socket instead of re-handshaking — transparent, and safe
    # to enable unconditionally since it is a pure client-side optimization
    # with no server-side requirement (works against any SSH server,
    # including SFTP-only/chrooted accounts). `ControlPersist` keeps the
    # master alive for a while after the last client detaches, so a script
    # issuing many calls in quick succession (a bulk upload, a recursive
    # stat walk) reuses one connection throughout; it then closes itself
    # (no daemon left running indefinitely).
    opts += [
        "-o",
        "ControlMaster=auto",
        "-o",
        f"ControlPath={_control_path(cred)}",
        "-o",
        f"ControlPersist={_CONTROL_PERSIST}",
    ]

    return opts


def _sftp_argv(cred: dict) -> tuple[list[str], dict[str, str]]:
    """Build the ``sftp`` argv prefix (up to ``-b <batchfile>`` and the target)."""
    prefix, env, use_password = _password_prefix(cred)
    batch_mode = "no" if use_password else "yes"
    argv = [*prefix, _SFTP_BIN, *_ssh_options(cred, batch_mode=batch_mode)]
    return argv, env


def _ssh_exec_argv(cred: dict, remote_command: str) -> tuple[list[str], dict[str, str]]:
    """Build a plain ``ssh host remote_command`` argv (not the ``sftp`` subsystem).

    Shares identity, host-key policy, known_hosts and ControlMaster options
    with :func:`_ssh_options`, but cannot reuse it verbatim: ``sftp``/``scp``
    take the port as ``-P`` (uppercase), while ``ssh`` itself takes ``-p``
    (lowercase) — the one flag that differs between the two tools.

    Parameters
    ----------
    cred : dict
        Resolved credentials dict.
    remote_command : str
        The command to run on the remote host's default shell.

    Returns
    -------
    (argv, env)
        Ready for :func:`_system`. ``env`` carries ``SSHPASS`` when password
        auth is configured, same as :func:`_sftp_argv`.
    """
    prefix, env, use_password = _password_prefix(cred)
    batch_mode = "no" if use_password else "yes"
    # _ssh_options()'s first two tokens are always ["-P", port] (the
    # sftp/scp spelling) — swap that one token's flag, keep everything after
    # it (identity, host-key policy, known_hosts, ControlMaster) untouched.
    shared = _ssh_options(cred, batch_mode=batch_mode)
    shared[0] = "-p"
    argv = [*prefix, "ssh", *shared, _target(cred), remote_command]
    return argv, env


#: Sentinel echoed by :func:`_probe_exec` — long and specific enough that a
#: forced-command / restricted-shell server's own error banner could never
#: coincidentally match it.
_EXEC_PROBE_MARKER = "sftp-helper-exec-probe-ok"


def _probe_exec(cred: dict) -> bool:
    """Return whether the server accepts an arbitrary shell command over SSH.

    Many SFTP-only hosting accounts (``ForceCommand internal-sftp`` or a
    restricted shell) accept SFTP connections but reject/ignore any other
    command — silently, without a clean error: the connection itself still
    succeeds, only the requested command never actually runs. Checking the
    *literal echoed output*, not just the exit code, is what makes this
    detection reliable — a rejected command commonly still exits 0.

    Parameters
    ----------
    cred : dict
        Resolved credentials dict.

    Returns
    -------
    bool
        ``True`` only if the server ran the probe command and returned
        exactly the expected marker.
    """
    argv, env = _ssh_exec_argv(cred, f"echo {_EXEC_PROBE_MARKER}")
    try:
        code, out, _err = _system(argv, env)
    except Exception:  # noqa: BLE001 — any failure to even ask means "assume no exec"
        return False
    return code == 0 and _EXEC_PROBE_MARKER in out


def _run_ssh_exec(cred: dict, command: str) -> dict:
    """Run one command over plain SSH exec and capture the result.

    The exec-channel counterpart to :func:`_run_sftp`: same return shape,
    but drives ``ssh host command`` instead of the ``sftp`` subsystem. Only
    meaningful when :func:`_probe_exec` has confirmed the server accepts
    exec at all.

    Returns
    -------
    dict
        ``{"code": <exit status>, "out": <stdout>, "err": <stderr>}``.
    """
    argv, env = _ssh_exec_argv(cred, command)
    code, out, err = _system(argv, env)
    return {"code": code, "out": out, "err": err}


def _system(argv: list[str], env: dict[str, str]) -> tuple[int, str, str]:
    """Run ``argv`` (no shell) and return ``(returncode, stdout, stderr)``.

    We drive the process directly rather than through ``os_helper.system``
    because the **exit code** is the authoritative success signal, and that
    helper does not expose it — it only asserts on non-zero. That distinction
    matters: a modern OpenSSH client prints benign notices to stderr (e.g. the
    post-quantum key-exchange warning) on a fully successful transfer, so
    "stderr is non-empty" cannot mean "it failed". ``env`` is merged onto the
    current environment (used only to pass ``SSHPASS`` for password auth,
    keeping the secret out of the argv).
    """
    osh.info("Executing: " + " ".join(shlex.quote(token) for token in argv))
    proc = subprocess.run(  # noqa: S603 — argv list, shell=False, no injection surface
        argv,
        capture_output=True,
        text=True,
        env={**os.environ, **env},
    )
    return proc.returncode, proc.stdout, proc.stderr


def _run_sftp(cred: dict, commands: list[str], *, extra_env: dict[str, str] | None = None) -> dict:
    """Run a list of ``sftp`` batch commands against ``cred`` and capture the result.

    Parameters
    ----------
    cred : dict
        Resolved credentials dict.
    commands : list[str]
        Interactive ``sftp`` commands (``put``, ``get``, ``rm``, ``mkdir``,
        ``ls``, ``cd`` ...). Prefix a command with ``-`` to ignore its own
        failure (used for idempotent ``-mkdir``).
    extra_env : dict of str to str, optional
        Extra environment variables merged onto the subprocess env (on top
        of whatever :func:`_sftp_argv` already set, e.g. ``SSHPASS``).
        Used by the ``ls -l`` parsers to force ``LC_ALL=C`` so month names
        in the output are deterministic English abbreviations regardless of
        the caller's locale.

    Returns
    -------
    dict
        ``{"code": <exit status>, "out": <stdout>, "err": <stderr>}``. Callers
        decide success from ``code`` (0 = success, warnings on ``err`` and all),
        and only consult ``err`` to *classify* a non-zero exit.
    """
    _require_sftp_binary()
    argv, env = _sftp_argv(cred)
    if extra_env:
        env = {**env, **extra_env}

    # ``sftp -b`` reads its command list from a file (not stdin), which keeps us
    # fully non-interactive. A trailing newline ensures the last command runs.
    fd, batch_path = tempfile.mkstemp(prefix="sftp-helper-", suffix=".batch")
    try:
        with os.fdopen(fd, "w") as fout:
            fout.write("\n".join(commands) + "\n")
        argv += ["-b", batch_path, _target(cred)]
        code, out, err = _system(argv, env)
        return {"code": code, "out": out, "err": err}
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
# Transfers — resumable, retried, atomic, verified (with an optional live
# progress bar), mirroring os_helper.download_file's design.
# ---------------------------------------------------------------------------
#
# Every transfer goes through ``reput``/``reget`` — OpenSSH's own resume
# commands (equivalent to ``put -a`` / ``get -a``): they continue from
# whatever bytes already exist at the destination instead of restarting, so a
# retry (within one call, or across separate calls days apart) picks up where
# the last attempt left off. Uploads land in a deterministic temp remote path
# and are only published (renamed) onto the real destination once verified —
# a caller only ever sees ``remote_path`` absent or complete, never truncated.
# Downloads use the exact same ``<file>.part`` sidecar + ``os.replace`` pattern
# ``download_file`` already uses locally.
#
# ``sftp -b`` batch mode is authoritative for correctness (reliable exit code
# + captured errors) but shows no live meter. On an interactive terminal, the
# blocking batch call runs on a worker thread while the main thread polls a
# cheap progress probe (local ``.part`` size for downloads; a remote ``ls -l``
# for uploads) and drives an ``os_helper.progress_bar`` — real byte counts,
# not scraped text. Off a TTY (CI, pipes) it runs with no thread and no bar,
# exactly like ``download_file`` auto-suppresses its own.


def _sha256_file(path: str, *, chunk_size: int = 1 << 20) -> str:
    """Stream ``path`` through SHA-256 in fixed-size chunks (flat memory)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk_size), b""):
            h.update(block)
    return h.hexdigest()


def _stderr_is_tty() -> bool:
    """Whether stderr is an interactive terminal — a seam kept for testability."""
    try:
        return bool(sys.stderr.isatty())
    except Exception:  # noqa: BLE001
        return False


def _run_sftp_with_progress(
    cred: dict,
    commands: list[str],
    *,
    total: int | None,
    probe,
    desc: str,
    progress: bool = True,
) -> dict:
    """Run :func:`_run_sftp` on a worker thread, driving a bar from ``probe()`` polls.

    Parameters
    ----------
    cred : dict
        Resolved credentials dict.
    commands : list[str]
        Passed straight through to :func:`_run_sftp`.
    total : int or None
        Known total bytes for the bar (``None`` leaves it open-ended).
    probe : Callable[[], int | None]
        Zero-arg callable returning the current known byte count. Must be
        cheap and safe to call repeatedly (roughly once a second); an
        exception or a ``None`` return just skips that update — a missed tick
        is harmless, the caller's own exit-code/size check is what actually
        decides success.
    desc : str
        Progress-bar label (the file name).
    progress : bool, optional
        Show a bar on an interactive terminal (default ``True``, matching
        ``os_helper.download_file``'s own ``progress`` flag). ``False``
        forces the inline no-thread path unconditionally — useful for a
        caller driving many transfers in a loop (e.g. :func:`upload_many`'s
        per-file fallback) that wants one bar's worth of noise, not N.

    Returns
    -------
    dict
        Exactly :func:`_run_sftp`'s ``{"code", "out", "err"}``.
    """
    if not progress or not _stderr_is_tty():
        # No bar off a TTY (or when explicitly disabled): run inline, no
        # thread, no polling overhead — matches ``os_helper.progress_bar``'s
        # own auto-suppress convention.
        return _run_sftp(cred, commands)

    result: dict = {}

    def worker() -> None:
        result.update(_run_sftp(cred, commands))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    bar = osh.progress_bar(total=total, desc=desc)
    last = 0
    while thread.is_alive():
        thread.join(timeout=1.0)
        try:
            cur = probe()
        except Exception:  # noqa: BLE001 — a missed progress tick is harmless
            cur = None
        if cur is not None and cur > last:
            bar.update(cur - last)
            last = cur
    try:
        cur = probe()
    except Exception:  # noqa: BLE001
        cur = None
    if cur is not None and cur > last:
        bar.update(cur - last)
    bar.close()
    return result


def _upload_resumable(
    cred: dict,
    local_path: str,
    remote_path: str,
    *,
    desc: str,
    retries: int,
    resume: bool = True,
    progress: bool = True,
) -> None:
    """Upload ``local_path`` -> ``remote_path``: resumable, retried, atomic, size-verified.

    Transfers into a deterministic temp remote path (``remote_path +
    _UPLOAD_TMP_SUFFIX``) so a retry — within this call, or a later call to
    :func:`upload` for the same destination — continues instead of
    restarting. Each attempt is verified by comparing the temp file's remote
    size to the local file's size; only a size-verified transfer is
    published, atomically, onto ``remote_path`` (any existing file there is
    removed, then the temp file renamed onto it, in one batch). A file only
    ever appears at ``remote_path`` complete — never truncated.

    OpenSSH's ``reput`` (``put -a``) only actually *resumes*: empirically (not
    just per ``man sftp``) it errors both when the remote temp file is wholly
    absent ("stat remote: No such file or directory") and when it is already
    the same size or larger ("destination file same size or larger") — it is
    not the drop-in "upload or continue" primitive its description suggests.
    Each attempt therefore stats the temp file first and picks the right
    command: plain ``put`` when absent (or when a stale, oversized leftover
    is removed first), ``reput`` only when a genuine smaller partial exists,
    and no transfer at all when it is already complete.

    Note: like ``os_helper.download_file`` without a ``sha256`` pin, this
    verifies *completeness* (size) but not byte-for-byte content — a
    corruption that preserves length would slip through. Content hashing
    would need a remote exec channel, which many SFTP-only accounts
    (chrooted, ``ForceCommand internal-sftp``) do not expose.

    Parameters
    ----------
    resume : bool, optional
        Continue a partial temp remote file (default ``True``, mirroring
        ``os_helper.download_file``'s own ``resume`` flag). ``False``
        discards any existing temp remote file up front and uploads from
        scratch — for a caller that knows a prior partial is unusable
        (e.g. the local source changed) rather than merely interrupted.
    progress : bool, optional
        Show a bar on an interactive terminal (default ``True``). Forwarded
        to :func:`_run_sftp_with_progress`.

    Raises
    ------
    Exception
        If every attempt fails, or the atomic publish fails. On total
        failure the temp remote file is left in place so a later call
        resumes rather than starts over.
    """
    # ``remote_path`` arrives already validated (every caller resolves it via
    # strip_sftp_path -> normalize_path first); ``local_path`` does not go
    # through that funnel, and is what gets embedded in the ``put``/``reput``
    # batch command below, so it needs the same guard here.
    _assert_safe_path(local_path, what="local path")
    temp_remote = f"{remote_path}{_UPLOAD_TMP_SUFFIX}"
    local_size = os.path.getsize(local_path)

    if not resume:
        # Best-effort: a stale/absent temp file either way just means the
        # next attempt starts with a plain ``put`` (see ``before is None``
        # below) — no need to check the result.
        _run_sftp(cred, [f'-rm "{temp_remote}"'])

    def probe() -> int | None:
        st = remote_stat(temp_remote, cred)
        return st["size"] if st else 0

    last_err = ""
    for attempt in range(retries + 1):
        try:
            before = remote_stat(temp_remote, cred)
        except Exception:  # noqa: BLE001 — an inconclusive stat just means "assume absent"
            before = None
        if before is None:
            command = f'put -p "{local_path}" "{temp_remote}"'
        elif before["size"] == local_size:
            break  # a prior attempt already finished this transfer
        elif before["size"] > local_size:
            # Stale/corrupt leftover larger than the current source: reput
            # would refuse it too ("same size or larger") — start clean.
            _run_sftp(cred, [f'-rm "{temp_remote}"'])
            command = f'put -p "{local_path}" "{temp_remote}"'
        else:
            command = f'reput -p "{local_path}" "{temp_remote}"'

        res = _run_sftp_with_progress(
            cred, [command], total=local_size, probe=probe, desc=desc, progress=progress
        )
        if res["code"] == 0:
            st = remote_stat(temp_remote, cred)
            if st and st["size"] == local_size:
                break
            osh.warning(
                f"sftp upload: size mismatch after attempt {attempt + 1} "
                f"(local {local_size}, remote {st['size'] if st else 0}) — retrying"
            )
        else:
            last_err = res["err"]
            osh.warning(f"sftp upload attempt {attempt + 1} failed: {last_err.strip()}")
        if attempt < retries:
            time.sleep(2**attempt)
    else:
        if last_err:
            _raise_if_connect_error(last_err, cred, "upload")
        raise Exception(
            f"Upload failed after {retries + 1} attempt(s): {local_path} -> {remote_path}. "
            f"Partial data kept at {temp_remote} for a future resumed retry."
        )

    # Atomic publish: drop whatever (if anything) is already at remote_path, then
    # rename the verified temp file onto it — one batch, minimal exposure window.
    pub = _run_sftp(cred, [f'-rm "{remote_path}"', f'rename "{temp_remote}" "{remote_path}"'])
    if pub["code"] != 0:
        _raise_if_connect_error(pub["err"], cred, "upload publish")
        raise Exception(f"Failed to publish {remote_path}: {pub['err'].strip()}")
    final = remote_stat(remote_path, cred)
    if not final or final["size"] != local_size:
        raise Exception(f"Publish verification failed for {remote_path}")


def _download_resumable(
    cred: dict,
    remote_path: str,
    local_path: str,
    *,
    desc: str,
    retries: int,
    sha256: str | None,
    resume: bool = True,
    progress: bool = True,
) -> dict:
    """Download ``remote_path`` -> ``local_path``: resumable, retried, atomic, verified.

    Mirrors ``os_helper.download_file`` on the SFTP side: bytes land in a
    ``<local_path>.part`` sidecar via ``reget``, which resumes from the
    sidecar's current size; retried with exponential backoff; only
    ``os.replace``-d onto ``local_path`` once size-verified (and, if
    ``sha256`` is given, content-verified too — always possible here since
    the hash runs locally, unlike the upload side's remote-exec limitation).

    Parameters
    ----------
    resume : bool, optional
        Continue a partial ``.part`` sidecar (default ``True``, mirroring
        ``os_helper.download_file``'s own ``resume`` flag). ``False``
        discards any existing sidecar up front and downloads from scratch.
    progress : bool, optional
        Show a bar on an interactive terminal (default ``True``). Forwarded
        to :func:`_run_sftp_with_progress`.

    Returns
    -------
    dict
        ``{"bytes": <size on disk>, "sha256": <hex or "">}``.

    Raises
    ------
    ValueError
        If ``sha256`` is given and the finished file's digest does not match
        (the bad sidecar is discarded).
    Exception
        If every attempt fails. On total failure the ``.part`` sidecar is
        left in place so a later call resumes rather than starts over.
    """
    # local_path gets embedded (as the ".part" sidecar) in the ``reget``
    # batch command below — same guard as _upload_resumable's local_path,
    # same reasoning.
    _assert_safe_path(local_path, what="local path")
    part_path = local_path + ".part"
    if not resume and os.path.exists(part_path):
        os.remove(part_path)

    def probe() -> int | None:
        return os.path.getsize(part_path) if os.path.exists(part_path) else 0

    try:
        remote_info = remote_stat(remote_path, cred)
    except Exception:  # noqa: BLE001 — an inconclusive stat just means "no known size yet"
        remote_info = None
    remote_size = remote_info["size"] if remote_info else None

    last_err = ""
    for attempt in range(retries + 1):
        res = _run_sftp_with_progress(
            cred,
            [f'reget -p "{remote_path}" "{part_path}"'],
            total=remote_size,
            probe=probe,
            desc=desc,
            progress=progress,
        )
        if res["code"] == 0:
            have = os.path.getsize(part_path) if os.path.exists(part_path) else 0
            if remote_size is None or have == remote_size:
                break
            osh.warning(
                f"sftp download: size mismatch after attempt {attempt + 1} "
                f"(local {have}, remote {remote_size}) — retrying"
            )
        else:
            last_err = res["err"]
            osh.warning(f"sftp download attempt {attempt + 1} failed: {last_err.strip()}")
        if attempt < retries:
            time.sleep(2**attempt)
    else:
        if last_err:
            _raise_if_connect_error(last_err, cred, "download")
        raise Exception(
            f"Download failed after {retries + 1} attempt(s): {remote_path} -> {local_path}. "
            f"Partial data kept at {part_path} for a future resumed retry."
        )

    digest = ""
    if sha256 is not None:
        digest = _sha256_file(part_path)
        if digest != sha256.lower():
            os.remove(part_path)
            raise ValueError(
                f"sha256 mismatch for {remote_path}: expected {sha256.lower()}, got {digest}"
            )

    os.replace(part_path, local_path)
    return {"bytes": os.path.getsize(local_path), "sha256": digest}


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
    res = _run_sftp(cred, ['ls "/"'])
    if res["code"] != 0:
        _raise_if_connect_error(res["err"], cred, "connection")
        raise Exception(f"Connection check failed:\n\t{res['err'].strip()}")
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

    Raises
    ------
    ValueError
        If `path` contains a newline, carriage return, NUL byte, or double
        quote — see :func:`_assert_safe_path`. Every remote-path-accepting
        function in this module funnels through here (directly or via
        :func:`strip_sftp_path`), so this is the one choke point that keeps
        such a path from ever reaching an ``sftp -b`` batch command or a
        remote ``ssh`` exec string, where it could break out of the quoting.
    """
    _assert_safe_path(path, what="remote path")
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
    # ``ls`` is the cheapest probe: exit 0 means the path is there (a benign
    # stderr notice is irrelevant), a non-zero exit with "No such file" means
    # absent, and anything else is a real fault we surface.
    res = _run_sftp(cred, [f'ls "{remote_path}"'])
    if res["code"] == 0:
        return True
    err = res["err"]
    if any(marker in err for marker in _NOT_FOUND_MARKERS):
        return False
    _raise_if_connect_error(err, cred, "existence check")
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
    # ``cd`` is a clean directory test: it exits 0 only for a directory, and
    # fails for a file ("Not a directory") or a missing path.
    res = _run_sftp(cred, [f'cd "{remote_path}"'])
    if res["code"] == 0:
        return True
    _raise_if_connect_error(res["err"], cred, "directory check")
    return False


#: Parses one ``ls -l`` output line. The name is captured greedily to the end
#: of the line (not the naive "last whitespace-split token") because remote
#: filenames may contain spaces. The date is either "Mon DD HH:MM" (recent —
#: year omitted, inferred) or "Mon DD  YYYY" (older — time omitted, midnight
#: assumed), exactly like GNU/BSD ``ls -l`` itself.
_LS_LONG_RE = re.compile(
    r"^(?P<type>[-dlbcps])\S*\s+\S+\s+\S+\s+\S+\s+(?P<size>\d+)\s+"
    r"(?P<mon>[A-Za-z]{3})\s+(?P<day>\d{1,2})\s+(?P<tv>\d{1,2}:\d{2}|\d{4})\s+(?P<name>.+)$"
)

_MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    )
}


def _parse_ls_long_line(line: str, *, now: datetime | None = None) -> dict | None:
    """Parse one ``ls -l`` line into ``{"name", "is_dir", "size", "mtime"}``.

    Parameters
    ----------
    line : str
        One line of ``ls -l`` output (English month names — the caller must
        run the command with ``LC_ALL=C``, see :func:`_sftp_ls_long`).
    now : datetime, optional
        Reference "current time" for the omitted-year heuristic. Defaults to
        ``datetime.now(timezone.utc)``; overridable for deterministic tests.

    Returns
    -------
    dict or None
        ``{"name": str, "is_dir": bool, "size": int, "mtime": datetime}``
        (``mtime`` is UTC-naive — the server's ``ls -l`` has no timezone
        info to give us, so this is a best-effort local-clock reading, good
        enough for "is the source newer" comparisons at day/minute
        granularity). ``None`` when the line does not match a long-listing
        entry (blank lines, a leading "total N" line, etc.).
    """
    m = _LS_LONG_RE.match(line.rstrip())
    if not m or m.group("mon") not in _MONTHS:
        return None
    now = now or datetime.now(timezone.utc)
    month = _MONTHS[m.group("mon")]
    day = int(m.group("day"))
    tv = m.group("tv")
    if ":" in tv:
        hour, minute = (int(p) for p in tv.split(":"))
        year = now.year
        try:
            candidate = datetime(year, month, day, hour, minute)
        except ValueError:
            return None
        # Standard ls heuristic: a "recent" (time-shown) date more than a day
        # in the future must actually be from last year (clock skew aside).
        if candidate > now.replace(tzinfo=None) + timedelta(days=1):
            candidate = candidate.replace(year=year - 1)
    else:
        try:
            candidate = datetime(int(tv), month, day)
        except ValueError:
            return None
    # Some servers echo the full path (not a bare filename) in `ls -l` output
    # for a directory target — observed in the wild, not just a theoretical
    # case. "/" can never be part of a real POSIX filename itself, so taking
    # the last path component is always safe and always correct, whichever
    # style the server used.
    name = m.group("name").rsplit("/", 1)[-1]
    return {
        "name": name,
        "is_dir": m.group("type") == "d",
        "size": int(m.group("size")),
        "mtime": candidate,
    }


def _sftp_ls_long(cred: dict, remote_path: str) -> list[dict]:
    """Immediate children of ``remote_path`` with type/size/mtime, via ``ls -l``.

    Parameters
    ----------
    cred : dict
        Credentials dict.
    remote_path : str
        Absolute remote directory to list.

    Returns
    -------
    list of dict
        One ``{"name", "is_dir", "size", "mtime"}`` per entry (see
        :func:`_parse_ls_long_line`); unparsable lines (e.g. a leading
        "total N" line some servers emit) are silently skipped. Empty when
        the directory has no entries.

    Raises
    ------
    Exception
        If the connection/auth fails, or the path is not a directory.
    """
    # LC_ALL=C: forces English month abbreviations regardless of the
    # server's or the operator's own locale, so _LS_LONG_RE's month table
    # is reliable. This overrides only this subprocess's environment, not
    # the caller's.
    res = _run_sftp(cred, [f'ls -l "{remote_path}"'], extra_env={"LC_ALL": "C", "LANG": "C"})
    if res["code"] != 0:
        err = res["err"]
        if any(marker in err for marker in _NOT_FOUND_MARKERS):
            raise Exception(f"No such remote directory: {remote_path}")
        _raise_if_connect_error(err, cred, "directory listing")
        raise Exception(f"Unexpected error listing {remote_path}:\n\t{err.strip()}")
    entries = []
    for line in res["out"].splitlines():
        parsed = _parse_ls_long_line(line)
        if parsed is not None:
            entries.append(parsed)
    return entries


def _sftp_ls_flat(cred: dict, remote_path: str) -> list[str]:
    """Immediate children of ``remote_path`` via a batch-mode ``ls -1``.

    Parameters
    ----------
    cred : dict
        Credentials dict.
    remote_path : str
        Absolute remote directory to list.

    Returns
    -------
    list of str
        Entry names (files and sub-directory names, not their contents), in
        the order the server returned them. Empty when the directory has no
        entries.

    Raises
    ------
    Exception
        If the connection/auth fails, or the path is not a directory.
    """
    res = _run_sftp(cred, [f'ls -1 "{remote_path}"'])
    if res["code"] != 0:
        err = res["err"]
        if any(marker in err for marker in _NOT_FOUND_MARKERS):
            raise Exception(f"No such remote directory: {remote_path}")
        _raise_if_connect_error(err, cred, "directory listing")
        raise Exception(f"Unexpected error listing {remote_path}:\n\t{err.strip()}")
    return [ln.strip() for ln in res["out"].splitlines() if ln.strip()]


def _sftp_list(cred: dict, remote_path: str, *, recursive: bool = False) -> list[str]:
    """List entries under ``remote_path``.

    Parameters
    ----------
    cred : dict
        Credentials dict.
    remote_path : str
        Absolute remote directory to list.
    recursive : bool, optional
        When ``True``, walks sub-directories too. OpenSSH's interactive
        ``sftp`` client has **no recursive `ls` flag** (its `ls` only
        supports ``-1afhlnrSt`` — the ``-r`` there means reverse-sort, not
        recurse, unlike GNU ``ls -R``), so recursion is emulated: `ls -1`
        the directory, then :func:`_sftp_isdir` each entry to tell files
        from sub-directories, recursing (depth-first) into the latter. This
        costs one round trip per entry found, on top of one `ls` per
        directory level — fine for a typical site tree, but a large/deep
        remote directory will be slow to walk this way. When ``False``
        (default), lists only the immediate children.

    Returns
    -------
    list of str
        Entry names (non-recursive) or paths relative to `remote_path`
        using ``/`` separators (recursive, files only — directories
        themselves are walked into, not listed). Empty when the directory
        has no entries.

    Raises
    ------
    Exception
        If the connection/auth fails, or the path is not a directory.
    """
    top = _sftp_ls_flat(cred, remote_path)
    if not recursive:
        return top

    entries: list[str] = []
    for name in top:
        child = f"{remote_path.rstrip('/')}/{name}"
        if _sftp_isdir(cred, child):
            entries.extend(f"{name}/{sub}" for sub in _sftp_list(cred, child, recursive=True))
        else:
            entries.append(name)
    return entries


def _sftp_walk_long(cred: dict, remote_path: str) -> dict[str, dict]:
    """Recursively stat every **file** under ``remote_path`` in one pass.

    Unlike :func:`_sftp_list`'s recursive mode (one ``cd`` probe per entry,
    kept as-is for that already-tested code path), this walks using
    :func:`_sftp_ls_long`, which gets the file/directory distinction *and*
    size/mtime from the same ``ls -l`` call that lists a directory's
    entries — one round trip per directory level instead of one per entry,
    and it fills in the stat data :func:`list_dir_stat` needs for free.

    Parameters
    ----------
    cred : dict
        Credentials dict.
    remote_path : str
        Absolute remote directory to walk.

    Returns
    -------
    dict of str to dict
        ``{relative_posix_path: {"size": int, "mtime": datetime}}``, one
        entry per **file** (directories are walked into, not listed).
    """
    out: dict[str, dict] = {}
    for entry in _sftp_ls_long(cred, remote_path):
        child = f"{remote_path.rstrip('/')}/{entry['name']}"
        if entry["is_dir"]:
            for rel, stat in _sftp_walk_long(cred, child).items():
                out[f"{entry['name']}/{rel}"] = stat
        else:
            out[entry["name"]] = {"size": entry["size"], "mtime": entry["mtime"]}
    return out


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


def list_dir(ftp_dir: str, cred: dict, *, recursive: bool = False) -> list[str]:
    """List a remote directory's contents.

    The missing counterpart to :func:`upload` for tooling that needs to know
    what is already on the server before deciding what to transfer (e.g. a
    mirror-style sync that skips or removes files, rather than
    :func:`upload`'s unconditional overwrite).

    Parameters
    ----------
    ftp_dir : str
        Full ``sftp://`` address or a plain remote directory path.
    cred : dict
        Credentials dict.
    recursive : bool, optional
        When ``True``, walks sub-directories too and returns paths relative
        to `ftp_dir` (e.g. ``"css/app.css"``). When ``False`` (default),
        returns only the immediate entries (one path component each).

    Returns
    -------
    list of str
        Entry names/relative paths, in the order the server returned them.

    Raises
    ------
    Exception
        Wrapped with the address if the connection fails or `ftp_dir` does
        not exist.

    Examples
    --------
    >>> import sftp_helper as sftph
    >>> cred = sftph.credentials("settings.yaml")
    >>> sftph.list_dir("/uploads", cred)  # doctest: +SKIP
    ['2026-06', 'readme.txt']
    >>> sftph.list_dir("/uploads", cred, recursive=True)  # doctest: +SKIP
    ['readme.txt', '2026-06/report.pdf']
    """
    remote_path = strip_sftp_path(ftp_dir, cred)
    try:
        entries = _sftp_list(cred, remote_path, recursive=recursive)
        osh.info(f"SFTP list {ftp_dir}: {len(entries)} entrie(s)")
        return entries
    except Exception as err:
        raise Exception(f"Failed to list SFTP directory {ftp_dir}.\nError: {err}") from err


def remote_stat(sftp_address: str, cred: dict) -> dict | None:
    """Return ``{"size": int, "mtime": datetime}`` for a remote file, or ``None``.

    Parses the server's ``ls -l`` output (see :func:`_parse_ls_long_line`);
    ``mtime`` has minute resolution and no timezone (the server sends none
    over this interface), so treat it as an approximate local-clock reading
    good enough for "is the source newer" comparisons, not for anything
    requiring second-level or timezone-aware precision.

    Parameters
    ----------
    sftp_address : str
        Full ``sftp://`` address or a plain remote path to a **file** (not a
        directory).
    cred : dict
        Credentials dict.

    Returns
    -------
    dict or None
        ``{"size": int, "mtime": datetime}``, or ``None`` if the path does
        not exist (or is a directory — this is a file stat, not `list_dir`).

    Raises
    ------
    Exception
        Wrapped with the address if the connection fails.

    Examples
    --------
    >>> import sftp_helper as sftph
    >>> cred = sftph.credentials("settings.yaml")
    >>> sftph.remote_stat("/uploads/readme.txt", cred)  # doctest: +SKIP
    {'size': 1234, 'mtime': datetime.datetime(2026, 6, 19, 10, 30)}
    """
    remote_path = strip_sftp_path(sftp_address, cred)
    parent = remote_path.rsplit("/", 1)[0] or "/"
    name = remote_path.rsplit("/", 1)[-1]
    try:
        for entry in _sftp_ls_long(cred, parent):
            if entry["name"] == name and not entry["is_dir"]:
                return {"size": entry["size"], "mtime": entry["mtime"]}
        return None
    except Exception as err:
        raise Exception(f"Failed to stat SFTP file {sftp_address}.\nError: {err}") from err


def list_dir_stat(ftp_dir: str, cred: dict) -> dict[str, dict]:
    """Recursively stat every file under a remote directory, in one walk.

    The bulk counterpart to :func:`stat`: builds a full ``{relative_path:
    {"size", "mtime"}}`` map for an entire remote tree in one pass (one
    round trip per directory level, not per file), so a sync tool can decide
    what to upload by comparing against local files entirely in memory —
    no per-file remote round trip needed.

    Parameters
    ----------
    ftp_dir : str
        Full ``sftp://`` address or a plain remote directory path.
    cred : dict
        Credentials dict.

    Returns
    -------
    dict of str to dict
        ``{relative_posix_path: {"size": int, "mtime": datetime}}``, one
        entry per file found anywhere under `ftp_dir` (directories are
        walked into, not listed). Empty if `ftp_dir` has no files.

    Raises
    ------
    Exception
        Wrapped with the address if the connection fails or `ftp_dir` does
        not exist.

    Examples
    --------
    >>> import sftp_helper as sftph
    >>> cred = sftph.credentials("settings.yaml")
    >>> sftph.list_dir_stat("/uploads", cred)  # doctest: +SKIP
    {'readme.txt': {'size': 1234, 'mtime': ...}, '2026-06/report.pdf': {'size': 98765, 'mtime': ...}}
    """
    remote_path = strip_sftp_path(ftp_dir, cred)
    try:
        tree = _sftp_walk_long(cred, remote_path)
        osh.info(f"SFTP stat {ftp_dir}: {len(tree)} file(s)")
        return tree
    except Exception as err:
        raise Exception(f"Failed to stat SFTP directory {ftp_dir}.\nError: {err}") from err


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
    res = _run_sftp(cred, levels)
    if res["code"] != 0:
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
        # ``rm`` (no ``-`` prefix) so a real removal failure is visible; a
        # "No such file" is read as success to keep the operation idempotent.
        res = _run_sftp(cred, [f'rm "{remote_path}"'])
        err = res["err"]
        if res["code"] == 0 or any(m in err for m in _NOT_FOUND_MARKERS):
            osh.info(f"SFTP file {sftp_address} successfully deleted (or already absent).")
            return True
        _raise_if_connect_error(err, cred, "deletion")
        raise Exception(f"Failed to delete {sftp_address}:\n\t{err.strip()}")
    except Exception as err:
        raise Exception(f"Failed to delete SFTP file:\n\t{sftp_address}.\nError:\n\t{err}") from err


def _local_walk_files(folder: str) -> list[tuple[str, str]]:
    """Every non-hidden file under ``folder``, paired with its ``folder``-relative POSIX path.

    Mirrors ``os_helper.zip_folder``'s own convention: any file or directory
    whose name starts with ``"."`` is skipped.

    Parameters
    ----------
    folder : str
        Local directory to walk (recursively).

    Returns
    -------
    list of (str, str)
        ``(absolute_local_path, relative_posix_path)`` pairs, in walk order.
    """
    out: list[tuple[str, str]] = []
    for root, dirs, filenames in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in filenames:
            if name.startswith("."):
                continue
            abs_path = os.path.join(root, name)
            rel = os.path.relpath(abs_path, folder).replace(os.sep, "/")
            out.append((abs_path, rel))
    return out


def upload(
    local_path: str,
    cred: dict,
    sftp_address: str = "",
    *,
    retries: int = 3,
    overwrite: bool = True,
    resume: bool = True,
    progress: bool = True,
) -> str:
    """
    Upload a local file (or directory) to the SFTP server: resumable, retried, atomic, size-verified.

    If ``local_path`` is a directory, every non-hidden file under it is
    uploaded (recursively) via :func:`upload_many` instead — see
    :func:`_upload_folder`. ``sftp_address`` is then required (there is no
    single file to derive a content-hashed default from) and names the
    destination directory; the return value is `sftp_address` itself rather
    than a single file's address.

    If ``sftp_address`` is empty (single-file case), a content-hashed name
    under ``cred['sftp_destination_path']`` is used.

    Mirrors ``os_helper.download_file``'s smart-transfer design: the file is
    sent into a temp remote path via ``reput`` (OpenSSH's resume-upload
    command), retried with exponential backoff on failure — each retry
    continuing rather than restarting — and only published (renamed) onto
    ``sftp_address`` once its remote size matches the local file exactly. A
    caller only ever observes ``sftp_address`` absent or complete, never
    truncated. See :func:`_upload_resumable` for the full design (including
    its one honest gap versus ``download_file``: size is verified, not a
    full content hash — that would need a remote exec channel many SFTP-only
    accounts don't expose).

    Parameters
    ----------
    local_path : str
        Path to the local file or directory to upload.
    cred : dict
        Credentials dict.
    sftp_address : str, optional
        Destination address (or destination directory, for a folder upload).
        When empty for a single file, a deterministic content-hashed name is
        generated so identical files map to the same remote path.
    retries : int, optional
        Extra attempts on a failed or size-mismatched transfer, with
        exponential backoff (default ``3``, so up to four tries total). Each
        retry resumes rather than restarts.
    overwrite : bool, optional
        Re-upload even if `sftp_address` already exists (default ``True``,
        matching :func:`download`'s own default). Set ``False`` to reuse an
        already-present destination without re-transferring: when
        `sftp_address` was auto-derived from the file's content hash, mere
        presence already proves the right bytes are there (no further check
        needed — see the derivation above); when it was given explicitly,
        the skip only applies if the remote size already matches (upload has
        no cheap way to content-verify a remote file — see
        :func:`_upload_resumable`).
    resume : bool, optional
        Continue a partial temp remote file (default ``True``). Set
        ``False`` to discard any existing partial and upload from scratch.
    progress : bool, optional
        Show a bar on an interactive terminal (default ``True``). Set
        ``False`` to suppress it even on a TTY (e.g. to keep a bulk loop's
        output to one summary line instead of N bars).

    Returns
    -------
    str
        The full ``sftp://`` address (or plain remote path) of the file, or
        `sftp_address` itself for a folder upload.

    Raises
    ------
    ValueError
        If `local_path` is a directory and `sftp_address` is empty.
    Exception
        If every attempt fails, or the atomic publish fails. On total
        failure the file is left in place at its temp remote path — see
        :data:`_UPLOAD_TMP_SUFFIX` — so a later call to :func:`upload` for
        the same destination resumes instead of starting over.
    """
    if os.path.isdir(local_path):
        return _upload_folder(
            local_path,
            cred,
            sftp_address,
            retries=retries,
            overwrite=overwrite,
            resume=resume,
            progress=progress,
        )

    osh.checkfile(local_path, msg=f"Cannot upload missing local file: {local_path}")

    # No explicit destination: derive a stable, collision-resistant name from
    # the file's content hash (plus date) so re-uploading the same bytes is
    # deterministic and de-duplicated by the server-side path. ``rstrip`` keeps
    # the join clean when the base is the root ("/") or has a trailing slash.
    auto_named = osh.emptystring(sftp_address)
    if auto_named:
        _, _, ext = osh.folder_name_ext(local_path)
        h = osh.hashfile(local_path, hash_content=True, date=True)
        base = cred["sftp_destination_path"].rstrip("/")
        sftp_address = f"{base}/{h}.{ext}"

    if not overwrite:
        existing = remote_stat(sftp_address, cred)
        if existing is not None and (auto_named or existing["size"] == os.path.getsize(local_path)):
            osh.info(f"'{sftp_address}' already present; skipping (pass overwrite=True to force)")
            return sftp_address
        if existing is not None:
            osh.warning(f"'{sftp_address}' exists but size differs from local; re-uploading")

    remote_path = strip_sftp_path(sftp_address, cred)
    try:
        # sftp does not create missing parents, so ensure the directory exists
        # first. This makes upload robust to a fresh tree.
        parent = remote_path.rsplit("/", 1)[0]
        if parent and parent != remote_path:
            make_remote_directory(parent, cred)

        _upload_resumable(
            cred,
            local_path,
            remote_path,
            desc=os.path.basename(remote_path),
            retries=retries,
            resume=resume,
            progress=progress,
        )
        osh.info(f"Upload successful: {local_path} -> {sftp_address}")
        return sftp_address
    except Exception as err:
        raise Exception(
            f"Upload failed:\n\t{local_path}\n\t->{sftp_address}.\nError:\n\t{err}"
        ) from err


def _upload_folder(
    local_dir: str,
    cred: dict,
    sftp_address: str,
    *,
    retries: int = 3,
    overwrite: bool = True,
    resume: bool = True,
    progress: bool = True,
) -> str:
    """Upload every file under ``local_dir`` (recursively) via :func:`upload_many`.

    The directory counterpart to :func:`upload`'s single-file path: walks
    `local_dir` (skipping hidden entries, see :func:`_local_walk_files`) and
    hands the whole batch to :func:`upload_many` in one call, so a server
    that accepts exec gets the archive-accelerated path for free.

    Parameters
    ----------
    local_dir : str
        Local directory to upload (recursively).
    cred : dict
        Credentials dict.
    sftp_address : str
        Destination directory. Required — unlike the single-file path,
        there is no single content hash to derive a default from.
    retries, overwrite, resume, progress
        Forwarded to :func:`upload_many` (see its docstring — `overwrite`,
        in particular, turns a repeat call into an incremental sync that
        skips files already present with a matching size).

    Returns
    -------
    str
        `sftp_address`, unchanged, once every file has landed under it.

    Raises
    ------
    ValueError
        If `sftp_address` is empty.
    Exception
        If any file fails to upload — see :func:`upload_many`.
    """
    if osh.emptystring(sftp_address):
        raise ValueError(
            "sftp_address is required when uploading a folder "
            "(there is no single file to derive a content-hashed default from)."
        )
    remote_root = strip_sftp_path(sftp_address, cred)
    files = [(abs_path, f"{remote_root}/{rel}") for abs_path, rel in _local_walk_files(local_dir)]
    if not files:
        osh.warning(f"Upload skipped: '{local_dir}' has no files to upload.")
        return sftp_address

    upload_many(files, cred, retries=retries, overwrite=overwrite, resume=resume, progress=progress)
    osh.info(f"Upload successful (folder): {local_dir} -> {sftp_address} ({len(files)} file(s))")
    return sftp_address


def _upload_many_archive(files: list[tuple[str, str]], cred: dict) -> dict[str, str]:
    """Bulk-upload via one local zip -> one ``put`` -> one remote ``unzip``.

    Only called by :func:`upload_many` after :func:`_probe_exec` has
    confirmed the server accepts arbitrary exec — a plain SFTP subsystem
    cannot run ``unzip``, and many hosting accounts restrict exec entirely
    (see :func:`_probe_exec`'s docstring), which is why this is an
    accelerator, never the only path.

    Every file must resolve under ``cred["sftp_destination_path"]`` (one
    zip can only explode under one root); a caller mixing destinations
    should split into separate :func:`upload_many` calls instead.

    Staging, zipping and cleanup are all done through ``os_helper`` /
    ``sftp_helper``'s own house utilities rather than raw ``tempfile`` /
    ``zipfile`` calls: :func:`os_helper.temporary_folder` (local staging
    tree), :func:`os_helper.zip_folder` (the archive itself),
    :func:`os_helper.temporary_filename` (the local zip's path), and
    :func:`remote_tempfile` (the remote zip's path) — each already handles
    its own guaranteed cleanup, so this function does not track any temp
    path by hand.

    Parameters
    ----------
    files : list of (str, str)
        ``(local_path, sftp_address)`` pairs.
    cred : dict
        Credentials dict.

    Returns
    -------
    dict of str to str
        ``{local_path: sftp_address}`` for every file, on success.

    Raises
    ------
    ValueError
        If any `sftp_address` falls outside the shared destination root.
    Exception
        If the upload or the remote unzip fails.
    """
    dest_root = cred["sftp_destination_path"].rstrip("/")  # "" for the server root

    entries: list[tuple[str, str, str]] = []  # (local_path, sftp_address, arcname)
    for local_path, sftp_address in files:
        remote_path = strip_sftp_path(sftp_address, cred)
        if dest_root and not (remote_path == dest_root or remote_path.startswith(dest_root + "/")):
            raise ValueError(
                f"{sftp_address!r} is outside the destination root "
                f"{cred['sftp_destination_path']!r}; bulk archive upload requires "
                "every target under one root."
            )
        arcname = remote_path[len(dest_root) :].lstrip("/")
        entries.append((local_path, sftp_address, arcname))

    # Stage a mirror tree (arcname-relative) so os_helper.zip_folder — which
    # zips a *folder*, paths relative to it, not an arbitrary scattered file
    # list — can build the archive without us touching the zip format directly.
    with osh.temporary_folder(prefix="sftp-helper-bulk") as staging:
        for local_path, _addr, arcname in entries:
            staged_path = os.path.join(staging, arcname)
            osh.make_directory(os.path.dirname(staged_path) or staging)
            osh.copyfile(local_path, staged_path)

        with osh.temporary_filename(suffix=".zip", prefix="sftp-helper-bulk") as zip_path:
            osh.zip_folder(staging, zip_path)

            with remote_tempfile(cred, ext="zip") as (remote_zip, _url):
                upload(zip_path, cred, remote_zip)

                # unzip creates missing subdirectories itself — no separate
                # mkdir -p pass needed, unlike the per-file path. -o
                # overwrites in place, -q keeps the (unused) stdout small.
                # The remote zip itself is cleaned up by remote_tempfile's
                # own context-manager exit, success or failure alike — no
                # explicit rm here.
                target_dir = dest_root or "/"
                # shlex.quote (POSIX shell quoting), not a hand-rolled f'"..."':
                # this remote command runs through the target's actual shell,
                # where a bare double-quoted "{...}" still lets $(...) / `...`
                # command-substitution through — quoting must defeat that too.
                cmd = (
                    f"cd {shlex.quote(target_dir)} && "
                    f"unzip -o -q {shlex.quote(os.path.basename(remote_zip))}"
                )
                res = _run_ssh_exec(cred, cmd)
                if res["code"] != 0:
                    raise Exception(
                        f"Remote unzip failed (exit {res['code']}): "
                        f"{res['err'].strip() or res['out'].strip()}"
                    )
                osh.info(
                    f"Bulk archive upload: {len(entries)} file(s) via {os.path.basename(remote_zip)}"
                )

    return {local_path: sftp_address for local_path, sftp_address, _arc in entries}


def upload_many(
    files: list[tuple[str, str]],
    cred: dict,
    *,
    retries: int = 3,
    archive: bool | None = None,
    overwrite: bool = True,
    resume: bool = True,
    progress: bool = True,
) -> dict[str, str]:
    """Upload several files in one bulk operation, archive-accelerated when possible.

    Every SFTP command in this package pays a fresh SSH handshake unless
    ControlMaster reuse kicks in (see :func:`_control_path`); on a server
    that also accepts exec, this collapses N file transfers into one zip
    upload plus one remote unzip — the biggest possible win, since it avoids
    even the reduced per-file overhead ControlMaster leaves behind (one
    `put` conversation, one directory-creation round trip, one publish-rename
    per file). :func:`_probe_exec` detects that capability up front; a
    server that does not have it (most SFTP-only hosting accounts) falls
    back to the ordinary per-file :func:`upload` loop, unaffected, since
    ControlMaster reuse still applies there.

    Parameters
    ----------
    files : list of (str, str)
        ``(local_path, sftp_address)`` pairs to upload.
    cred : dict
        Credentials dict.
    retries : int, optional
        Forwarded to :func:`upload` for the per-file fallback path (the
        archive path has its own upload+unzip retry-free flow — a failure
        there falls all the way back to per-file, which does retry).
    archive : bool or None, optional
        Force the archive path (``True``), force the per-file path
        (``False``), or auto-detect via :func:`_probe_exec` (``None``,
        default). Ignored (treated as ``False``) when `overwrite` is
        ``False`` — see below.
    overwrite : bool, optional
        Re-upload every file unconditionally (default ``True``). Set
        ``False`` to skip files already present with a matching size —
        turning a repeat call into an incremental sync. This *forces the
        per-file path* regardless of `archive`: the archive path zips and
        unzips the whole batch in one shot with no per-entry stat, so it has
        no way to honour a per-file skip.
    resume, progress
        Forwarded to :func:`upload` for the per-file fallback path.

    Returns
    -------
    dict of str to str
        ``{local_path: sftp_address}`` for every file.
    """
    if not files:
        return {}

    use_archive = False if not overwrite else (_probe_exec(cred) if archive is None else archive)
    if use_archive:
        try:
            return _upload_many_archive(files, cred)
        except Exception as exc:  # noqa: BLE001 — degrade to the always-available path
            osh.warning(f"Bulk archive upload failed ({exc}); falling back to per-file upload.")

    results: dict[str, str] = {}
    for local_path, sftp_address in files:
        results[local_path] = upload(
            local_path,
            cred,
            sftp_address,
            retries=retries,
            overwrite=overwrite,
            resume=resume,
            progress=progress,
        )
    return results


def download(
    sftp_address: str,
    cred: dict,
    local_path: str = "",
    *,
    retries: int = 3,
    sha256: str | None = None,
    overwrite: bool = True,
    resume: bool = True,
    progress: bool = True,
) -> str:
    """
    Download a remote SFTP file (or directory) to ``local_path``: resumable, retried, atomic, verified.

    If `sftp_address` is a remote directory, every file under it is
    downloaded (recursively) via :func:`download_many` instead — see
    :func:`_download_folder`. `sha256` is meaningless there (there is no
    single file to verify) and must be left ``None``; the return value is
    `local_path` itself rather than a single file's local path.

    Mirrors ``os_helper.download_file``'s design exactly, on the SFTP side
    (single-file case): bytes land in a ``<local_path>.part`` sidecar via
    ``reget`` (OpenSSH's resume-download command), retried with exponential
    backoff — each retry continuing rather than restarting — and only
    ``os.replace``-d onto ``local_path`` once size-verified (and, if
    ``sha256`` is given, content-verified too). See :func:`_download_resumable`
    for the full design.

    Parameters
    ----------
    sftp_address : str
        Full ``sftp://`` address or a plain remote path (file or directory)
        to fetch.
    cred : dict
        Credentials dict.
    local_path : str, optional
        Destination on the local disk. Defaults to the remote basename.
    retries : int, optional
        Extra attempts on a failed or size-mismatched transfer, with
        exponential backoff (default ``3``, so up to four tries total). Each
        retry resumes rather than restarts.
    sha256 : str or None, optional
        Expected lowercase hex SHA-256. When given, the finished file is
        verified and a mismatch raises :class:`ValueError` (the bad sidecar
        is discarded). Only valid for a single-file download.
    overwrite : bool, optional
        Re-download even if ``local_path`` already exists (default ``True``,
        matching this function's historical behaviour). Set ``False`` to
        reuse a complete destination without re-downloading — its digest is
        re-checked when ``sha256`` is given. Ignored for a folder download.
    resume : bool, optional
        Continue a partial ``.part`` sidecar (default ``True``). Set
        ``False`` to discard any existing partial and download from
        scratch.
    progress : bool, optional
        Show a bar on an interactive terminal (default ``True``). Set
        ``False`` to suppress it even on a TTY (e.g. to keep a bulk loop's
        output to one summary line instead of N bars).

    Returns
    -------
    str
        The local path of the downloaded file, or `local_path` itself for a
        folder download.

    Raises
    ------
    ValueError
        If ``sha256`` is given and the finished file's digest does not
        match, or if ``sha256`` is given for a directory `sftp_address`.
    Exception
        If every attempt fails. On total failure the ``.part`` sidecar is
        left in place so a later call to :func:`download` for the same
        destination resumes instead of starting over.
    """
    remote_path = strip_sftp_path(sftp_address, cred)
    # No local destination given: mirror the remote file name into the CWD.
    if osh.emptystring(local_path):
        local_path = remote_path.split("/")[-1]

    # Purely local, zero-round-trip fast path: an already-complete destination
    # needs no server contact at all — checked before the directory probe
    # below (also a round trip) so this optimization still holds even when
    # `sftp_address` happens to be a directory.
    if not overwrite and osh.file_exists(local_path):
        if sha256 is None or _sha256_file(local_path) == sha256.lower():
            osh.info(f"'{local_path}' already present; skipping (pass overwrite=True to force)")
            return local_path
        osh.warning(f"'{local_path}' exists but sha256 mismatch; re-downloading")

    if remote_dir_exist(sftp_address, cred):
        if sha256 is not None:
            raise ValueError(
                "sha256 is only meaningful for a single-file download, not a directory."
            )
        return _download_folder(
            sftp_address,
            cred,
            local_path,
            retries=retries,
            overwrite=overwrite,
            resume=resume,
            progress=progress,
        )

    try:
        _download_resumable(
            cred,
            remote_path,
            local_path,
            desc=os.path.basename(local_path),
            retries=retries,
            sha256=sha256,
            resume=resume,
            progress=progress,
        )
        # Assert the file actually materialized before reporting success.
        osh.checkfile(local_path, msg=f"Download failed for {sftp_address}")
        osh.info(f"Download successful: {sftp_address} -> {local_path}")
        return local_path
    except ValueError:
        # A sha256 mismatch is a distinct, actionable failure (matches
        # os_helper.download_file's contract) — let it propagate as-is
        # rather than blurring it into the generic wrapped Exception below.
        raise
    except Exception as err:
        raise Exception(
            f"Download failed:\n\t{sftp_address}\n\t->{local_path}.\nError:\n\t{err}"
        ) from err


def _download_folder(
    sftp_address: str,
    cred: dict,
    local_path: str,
    *,
    retries: int = 3,
    overwrite: bool = True,
    resume: bool = True,
    progress: bool = True,
) -> str:
    """Download every file under a remote directory (recursively) via :func:`download_many`.

    The directory counterpart to :func:`download`'s single-file path: lists
    `sftp_address` recursively via :func:`list_dir` and hands the whole
    batch to :func:`download_many` in one call, so a server that accepts
    exec gets the archive-accelerated path for free.

    Parameters
    ----------
    sftp_address : str
        Remote directory to download (recursively). Full ``sftp://``
        address or a plain remote path.
    cred : dict
        Credentials dict.
    local_path : str
        Local destination directory. When empty, defaults to the remote
        directory's basename in the current working directory.
    retries, overwrite, resume, progress
        Forwarded to :func:`download_many` (see its docstring — `overwrite`,
        in particular, turns a repeat call into an incremental sync that
        skips files already present locally with a matching size).

    Returns
    -------
    str
        The resolved `local_path`, once every file has landed under it.

    Raises
    ------
    Exception
        If any file fails to download — see :func:`download_many`.
    """
    remote_root = strip_sftp_path(sftp_address, cred)
    if osh.emptystring(local_path):
        local_path = remote_root.rsplit("/", 1)[-1] or remote_root

    rel_paths = list_dir(sftp_address, cred, recursive=True)
    osh.make_directory(local_path)
    if not rel_paths:
        osh.warning(f"Download skipped: '{sftp_address}' has no files to download.")
        return local_path

    files = [
        (f"{remote_root}/{rel}", os.path.join(local_path, *rel.split("/"))) for rel in rel_paths
    ]
    download_many(
        files, cred, retries=retries, overwrite=overwrite, resume=resume, progress=progress
    )
    osh.info(f"Download successful (folder): {sftp_address} -> {local_path} ({len(files)} file(s))")
    return local_path


def _download_many_archive(files: list[tuple[str, str]], cred: dict) -> dict[str, str]:
    """Bulk-download via a remote-staged zip -> one ``get`` -> one local unzip.

    Only called by :func:`download_many` after :func:`_probe_exec` has
    confirmed the server accepts arbitrary exec — a plain SFTP subsystem
    cannot run ``zip``, and many hosting accounts restrict exec entirely
    (see :func:`_probe_exec`'s docstring), which is why this is an
    accelerator, never the only path.

    The mirror image of :func:`_upload_many_archive`, run in reverse: there,
    the *local* side stages a mirror tree and zips it before one ``put``;
    here, the *remote* side stages a mirror tree (via ``cp``, in a
    :func:`_remote_scratch_dir`) and zips it before one ``get``, then the
    archive is exploded into a local staging tree (``os_helper``'s own
    :func:`os_helper.temporary_folder` / :func:`os_helper.temporary_filename`
    — kept temporary the same way the upload side keeps its staging tree
    temporary) and each entry copied to its own requested `local_path` —
    which, unlike `upload`'s single shared destination root, may be
    scattered anywhere on the local disk, so no shared-root check applies
    here.

    Parameters
    ----------
    files : list of (str, str)
        ``(sftp_address, local_path)`` pairs — mirrors :func:`download`'s
        own argument order.
    cred : dict
        Credentials dict.

    Returns
    -------
    dict of str to str
        ``{sftp_address: local_path}`` for every file, on success.

    Raises
    ------
    Exception
        If the remote staging/zip, the download, or local extraction fails.
    """
    entries: list[tuple[str, str, str]] = []  # (sftp_address, local_path, arcname)
    for sftp_address, local_path in files:
        arcname = strip_sftp_path(sftp_address, cred).lstrip("/")
        entries.append((sftp_address, local_path, arcname))

    with _remote_scratch_dir(cred) as stage_dir:
        # One mkdir per distinct parent directory, then one cp per file —
        # both sorted for a deterministic, readable command; cheap even for
        # a large batch since each is a plain shell built-in / coreutil, no
        # extra round trip per entry the way per-file mkdir/put would cost.
        parent_dirs = sorted(
            {arc.rsplit("/", 1)[0] for _addr, _local, arc in entries if "/" in arc}
        )
        # shlex.quote, not a hand-rolled f'"..."': see the matching comment in
        # _upload_many_archive — a bare double-quoted "{...}" still lets
        # $(...) / `...` command-substitution through in the remote shell.
        parts = [f"mkdir -p {shlex.quote(f'{stage_dir}/{d}')}" for d in parent_dirs]
        parts += [
            f"cp -p {shlex.quote('/' + arc)} {shlex.quote(f'{stage_dir}/{arc}')}"
            for _addr, _local, arc in entries
        ]

        with remote_tempfile(cred, ext="zip") as (remote_zip, _url):
            parts.append(f"cd {shlex.quote(stage_dir)} && zip -rq {shlex.quote(remote_zip)} .")
            res = _run_ssh_exec(cred, " && ".join(parts))
            if res["code"] != 0:
                raise Exception(
                    f"Remote archive staging/zip failed (exit {res['code']}): "
                    f"{res['err'].strip() or res['out'].strip()}"
                )

            with osh.temporary_filename(suffix=".zip", prefix="sftp-helper-bulk") as zip_path:
                download(remote_zip, cred, zip_path)

                with osh.temporary_folder(prefix="sftp-helper-bulk") as extracted:
                    with zipfile.ZipFile(zip_path) as zf:
                        zf.extractall(extracted)
                    for _addr, local_path, arc in entries:
                        parent = os.path.dirname(local_path)
                        if parent:
                            osh.make_directory(parent)
                        osh.copyfile(os.path.join(extracted, arc), local_path)

            osh.info(
                f"Bulk archive download: {len(entries)} file(s) via {os.path.basename(remote_zip)}"
            )

    return {sftp_address: local_path for sftp_address, local_path, _arc in entries}


def download_many(
    files: list[tuple[str, str]],
    cred: dict,
    *,
    retries: int = 3,
    archive: bool | None = None,
    overwrite: bool = True,
    resume: bool = True,
    progress: bool = True,
) -> dict[str, str]:
    """Download several files in one bulk operation, archive-accelerated when possible.

    The download-side mirror of :func:`upload_many`: on a server that also
    accepts exec, this collapses N downloads into one remote stage+zip, one
    ``get``, and one local unzip — avoiding even the reduced per-file
    overhead ControlMaster reuse leaves behind (one `get` conversation per
    file otherwise). :func:`_probe_exec` detects that capability up front; a
    server without it (most SFTP-only hosting accounts) falls back to the
    ordinary per-file :func:`download` loop, unaffected, since ControlMaster
    reuse still applies there.

    Parameters
    ----------
    files : list of (str, str)
        ``(sftp_address, local_path)`` pairs to download — mirrors
        :func:`download`'s own argument order.
    cred : dict
        Credentials dict.
    retries : int, optional
        Forwarded to :func:`download` for the per-file fallback path (the
        archive path has its own stage+zip+get+unzip flow — a failure there
        falls all the way back to per-file, which does retry).
    archive : bool or None, optional
        Force the archive path (``True``), force the per-file path
        (``False``), or auto-detect via :func:`_probe_exec` (``None``,
        default). Ignored (treated as ``False``) when `overwrite` is
        ``False`` — see below.
    overwrite : bool, optional
        Re-download every file unconditionally (default ``True``). Set
        ``False`` to skip files already present locally — turning a repeat
        call into an incremental sync. This *forces the per-file path*
        regardless of `archive`: the archive path downloads and extracts the
        whole batch in one shot with no per-entry check, so it has no way to
        honour a per-file skip.
    resume, progress
        Forwarded to :func:`download` for the per-file fallback path.

    Returns
    -------
    dict of str to str
        ``{sftp_address: local_path}`` for every file.
    """
    if not files:
        return {}

    use_archive = False if not overwrite else (_probe_exec(cred) if archive is None else archive)
    if use_archive:
        try:
            return _download_many_archive(files, cred)
        except Exception as exc:  # noqa: BLE001 — degrade to the always-available path
            osh.warning(f"Bulk archive download failed ({exc}); falling back to per-file download.")

    results: dict[str, str] = {}
    for sftp_address, local_path in files:
        results[sftp_address] = download(
            sftp_address,
            cred,
            local_path,
            retries=retries,
            overwrite=overwrite,
            resume=resume,
            progress=progress,
        )
    return results


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


@contextmanager
def _remote_scratch_dir(cred: dict) -> Iterator[str]:
    """Reserve a unique remote directory (via exec) and ``rm -rf`` it on exit.

    The directory-shaped counterpart to :func:`remote_tempfile`, which only
    reserves a single file path. Used exclusively by
    :func:`_download_many_archive` for a server-side mirror tree that
    ``zip`` can archive in one pass — only meaningful once
    :func:`_probe_exec` has already confirmed the server accepts exec (a
    plain SFTP subsystem has no recursive-delete primitive of its own).

    Parameters
    ----------
    cred : dict
        Credentials dict.

    Yields
    ------
    str
        The reserved, already-created remote directory's absolute path.

    Raises
    ------
    Exception
        If the directory cannot be created.
    """
    # Same 128-bit-random naming scheme as remote_tempfile, under the same
    # root, so two concurrent callers never collide.
    path = f"{cred['sftp_destination_path'].rstrip('/')}/{secrets.token_hex(16)}.tmp"
    res = _run_ssh_exec(cred, f"mkdir -p {shlex.quote(path)}")
    if res["code"] != 0:
        raise Exception(f"Failed to create remote scratch directory {path}: {res['err'].strip()}")
    try:
        yield path
    finally:
        # Best-effort: a cleanup failure here must never mask whatever
        # exception (if any) is already propagating out of the with-block.
        cleanup = _run_ssh_exec(cred, f"rm -rf {shlex.quote(path)}")
        if cleanup["code"] != 0:
            osh.warning(
                f"Failed to remove remote scratch directory {path}: {cleanup['err'].strip()}"
            )
