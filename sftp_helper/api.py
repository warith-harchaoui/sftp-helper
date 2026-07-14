"""
SFTP Helper — FastAPI HTTP surface.

Exposes every public function in :mod:`sftp_helper.main` as an HTTP
endpoint so ``sftp-helper`` can be dropped behind any reverse proxy and
consumed by other services. Kept intentionally minimal:

- Multipart uploads for local-to-remote transfers (``UploadFile``),
  streamed straight to a temporary file so large payloads do not blow
  up memory.
- ``FileResponse`` for downloads.
- JSON responses for the exists / delete / mkdir / show-credentials
  queries.
- ``BackgroundTasks`` cleans temp files after the response has been
  streamed — no leftover garbage on disk after a request.

Credentials
-----------
The credentials are loaded **once at import time** from the environment
(``SFTP_HOST`` / ``SFTP_LOGIN`` / …) or from the file pointed at by
``SFTP_HELPER_CONFIG``. We never accept credentials in a request body —
the API is meant to be the trusted server-side view of a single SFTP
target, not a multitenant relay.

Install the extra to get the runtime dependencies::

    pip install 'sftp-helper[api]'

Then run the app with any ASGI server::

    uvicorn sftp_helper.api:app --host 0.0.0.0 --port 8000

Usage Example
-------------
>>> # Start the server (env-configured credentials):
>>> #   SFTP_HELPER_CONFIG=./sftp_config.json uvicorn sftp_helper.api:app --reload
>>> # Upload a file:
>>> #   curl -F 'file=@local.txt' -F 'remote=/uploads/local.txt' \\
>>> #        http://localhost:8000/upload
>>> # Check existence:
>>> #   curl "http://localhost:8000/exists?remote=/uploads/local.txt"
>>> # Full OpenAPI docs at http://localhost:8000/docs

Author
------
Warith Harchaoui, Ph.D. — https://linkedin.com/in/warith-harchaoui/
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

try:
    from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, UploadFile
    from fastapi.responses import FileResponse, JSONResponse
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "The FastAPI HTTP surface requires the [api] extra. "
        "Install with: pip install 'sftp-helper[api]'"
    ) from exc

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
# App factory + shared plumbing
# ---------------------------------------------------------------------------


app = FastAPI(
    title="SFTP Helper API",
    description=(
        "HTTP surface for the sftp-helper utilities: upload, download, delete, "
        "exists, dir-exists, mkdir, normalize-path, strip-path, tempfile, "
        "show-credentials. Strict host-key verification is always on."
    ),
    version="2.2.2",
    docs_url="/docs",
    redoc_url="/redoc",
)


def _load_server_cred() -> dict:
    """
    Load credentials once at server-side, from ``SFTP_HELPER_CONFIG`` or env.

    Returns
    -------
    dict
        The resolved credentials, or an empty ``dict`` if the loader failed
        (so unit tests / smoke tests can still import the app without a
        real config on disk). Endpoints that need credentials will raise
        HTTP 503 in that case.
    """
    cfg = os.environ.get("SFTP_HELPER_CONFIG")
    try:
        # ``credentials`` accepts ``None`` and falls back to env / .env.
        return credentials(cfg) if cfg else credentials(None)
    except Exception:
        # Import-time failure must not crash uvicorn — the smoke tests need
        # to be able to import the app even when there's no real SFTP
        # target on the host. Endpoints will surface a 503 lazily.
        return {}


# Snapshot the resolved credentials at import time. Reloading requires a
# server restart, which matches operational reality (creds live in env /
# mounted config file, both of which need a restart to change anyway).
_SERVER_CRED: dict = _load_server_cred()


def _cred_or_503() -> dict:
    """Return the server credentials or raise HTTP 503 if none were loaded.

    Returns
    -------
    dict
        The non-empty credentials snapshot resolved at import time.

    Raises
    ------
    HTTPException
        With status 503 when the server was started without credentials, so
        clients get a clean, documented failure instead of an opaque 500.
    """
    # Guard: every network-touching endpoint calls this to guarantee we
    # emit a clean 503 when the server was started without credentials.
    if not _SERVER_CRED:
        raise HTTPException(
            status_code=503,
            detail=(
                "No SFTP credentials on the server. Set SFTP_HELPER_CONFIG or "
                "the SFTP_HOST/SFTP_LOGIN/SFTP_PASSWD/SFTP_DESTINATION_PATH/"
                "SFTP_HTTPS environment variables."
            ),
        )
    return _SERVER_CRED


def _spool(uploaded: UploadFile, dest_dir: Path, suffix_hint: str | None = None) -> Path:
    """
    Persist an ``UploadFile`` to a temp path on disk.

    We copy the stream instead of holding the bytes in memory so a
    multi-hundred-MB clip does not OOM the worker. The file inherits
    the caller's suffix when available so downstream tools can pick the
    right handler.

    Parameters
    ----------
    uploaded : UploadFile
        The FastAPI upload object.
    dest_dir : Path
        Temp directory that will hold the spooled file.
    suffix_hint : str, optional
        Extension override (with or without the leading dot). Falls back
        to the client-provided filename's suffix.

    Returns
    -------
    Path
        Path to the spooled file on disk.
    """
    ext = suffix_hint or (Path(uploaded.filename or "").suffix or ".bin")
    if not ext.startswith("."):
        ext = "." + ext
    out = dest_dir / (f"upload{ext}")
    with out.open("wb") as fp:
        shutil.copyfileobj(uploaded.file, fp)
    return out


def _cleanup(*paths: object) -> None:
    """Best-effort removal of temp files/dirs — a tidy-up failure never kills a response.

    Parameters
    ----------
    *paths : object
        One or more path-like objects (``str`` or ``Path``) to remove.
        Directories are removed recursively; missing paths are ignored.
    """
    for p in paths:
        try:
            path = Path(p)
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.exists():
                path.unlink(missing_ok=True)
        except Exception:
            pass


def _new_tmpdir() -> Path:
    """Create a request-scoped temp directory under the system temp root.

    Returns
    -------
    Path
        A fresh, uniquely-named directory (prefix ``sftp-helper-``) that the
        caller is responsible for cleaning up (see :func:`_cleanup`).
    """
    return Path(tempfile.mkdtemp(prefix="sftp-helper-"))


def _mask(cred: dict) -> dict:
    """Return a copy of ``cred`` with the SFTP password redacted.

    Parameters
    ----------
    cred : dict
        Resolved credentials, potentially containing ``sftp_passwd``.

    Returns
    -------
    dict
        A shallow copy whose ``sftp_passwd`` (when set) is replaced by
        ``"***"`` so it never leaks into a response body.
    """
    masked = dict(cred)
    if masked.get("sftp_passwd"):
        masked["sftp_passwd"] = "***"
    return masked


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Simple liveness probe — no dependency check, just proves the app is up."""
    return {"status": "ok"}


@app.get("/show-credentials", tags=["meta"])
def show_credentials() -> JSONResponse:
    """Return the resolved credentials (password masked)."""
    cred = _cred_or_503()
    return JSONResponse(_mask(cred))


# ---------------------------------------------------------------------------
# Pure helpers (no SFTP round-trip needed)
# ---------------------------------------------------------------------------


@app.get("/normalize-path", tags=["reads"])
def normalize_path_endpoint(
    path: str = Query(..., description="Path to normalize."),
) -> JSONResponse:
    """Normalize a remote path (single leading '/', no trailing '/')."""
    return JSONResponse({"path": normalize_path(path)})


@app.get("/strip-path", tags=["reads"])
def strip_path_endpoint(
    address: str = Query(..., description="Full sftp:// address."),
) -> JSONResponse:
    """Strip 'sftp://<host>' prefix from an SFTP address."""
    cred = _cred_or_503()
    return JSONResponse({"path": strip_sftp_path(address, cred)})


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------


@app.get("/exists", tags=["reads"])
def exists_endpoint(
    remote: str = Query(..., description="Full sftp:// address or plain remote path."),
) -> JSONResponse:
    """Return whether a remote file exists."""
    cred = _cred_or_503()
    return JSONResponse({"exists": bool(remote_file_exists(remote, cred)), "remote": remote})


@app.get("/dir-exists", tags=["reads"])
def dir_exists_endpoint(
    remote: str = Query(..., description="Remote directory path."),
) -> JSONResponse:
    """Return whether a remote directory exists."""
    cred = _cred_or_503()
    return JSONResponse({"exists": bool(remote_dir_exist(remote, cred)), "remote": remote})


# ---------------------------------------------------------------------------
# Action endpoints
# ---------------------------------------------------------------------------


@app.post("/upload", tags=["actions"])
def upload_endpoint(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    remote: str = Form(
        "", description="Full sftp:// address or plain remote path (auto if empty)."
    ),
) -> JSONResponse:
    """Upload the multipart file to the SFTP server. Returns the remote address."""
    cred = _cred_or_503()
    tmp = _new_tmpdir()
    src = _spool(file, tmp, suffix_hint=Path(file.filename or "").suffix)
    try:
        addr = upload(str(src), cred, remote)
    finally:
        # Clean synchronously here so a slow client cannot leave the temp
        # file lying around after the response has already returned.
        background.add_task(_cleanup, tmp)
    return JSONResponse({"sftp_address": addr})


@app.get("/download", tags=["actions"])
def download_endpoint(
    background: BackgroundTasks,
    remote: str = Query(..., description="Full sftp:// address or plain remote path."),
    filename: str | None = Query(
        None, description="Suggested filename in the Content-Disposition header."
    ),
):
    """Download a remote file. The response body is the file bytes."""
    cred = _cred_or_503()
    tmp = _new_tmpdir()
    # Pick a sensible default local name — either from the query string or
    # the remote basename.
    base = filename or Path(remote.rstrip("/")).name or "download.bin"
    local = tmp / base
    try:
        download(remote, cred, str(local))
    except Exception:
        _cleanup(tmp)
        raise
    # Clean the whole temp dir after the response has been sent.
    background.add_task(_cleanup, tmp)
    return FileResponse(str(local), filename=base, media_type="application/octet-stream")


@app.delete("/delete", tags=["actions"])
def delete_endpoint(
    remote: str = Query(..., description="Full sftp:// address or plain remote path."),
) -> JSONResponse:
    """Delete a remote file. Idempotent — deleting a missing file returns True."""
    cred = _cred_or_503()
    ok = delete(remote, cred)
    return JSONResponse({"deleted": bool(ok), "remote": remote})


@app.post("/mkdir", tags=["actions"])
def mkdir_endpoint(
    remote: str = Form(..., description="Remote directory path to create."),
) -> JSONResponse:
    """Create a remote directory (mkdir -p semantics)."""
    cred = _cred_or_503()
    make_remote_directory(remote, cred)
    return JSONResponse({"created": True, "remote": remote})


@app.post("/tempfile", tags=["actions"])
def tempfile_endpoint(
    ext: str = Form("", description="Optional file extension (without leading dot)."),
    subdir: str = Form("", description="Optional subdirectory under sftp_destination_path."),
) -> JSONResponse:
    """Reserve a unique remote path (context immediately closed). Deletes on exit."""
    # NB: the library's ``remote_tempfile`` deletes the reserved address on
    # exit. For this stateless HTTP call the caller cannot hold the context
    # open across requests — so we return the coordinates *and* leave the
    # remote deleted on exit. That matches the CLI's behaviour and is the
    # honest translation of the semantics.
    cred = _cred_or_503()
    with remote_tempfile(cred, ext=ext, subdir=subdir) as (addr, url):
        payload = {"sftp_address": addr, "url": url}
    return JSONResponse(payload)
