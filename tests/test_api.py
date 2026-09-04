"""
Tests for the FastAPI HTTP surface.

The read/action endpoints below are tested functionally: the server-side
credential snapshot is patched via the ``authed`` fixture (so
``_cred_or_503()`` proceeds instead of always 503'ing, which is this
suite's default with no real SFTP target configured), and the single
``sftp_helper.main`` function each endpoint calls is monkeypatched — the
same boundary ``test_sftp_helper.py`` and ``test_cli.py`` mock at. No live
SFTP server is ever contacted.

Usage Example
-------------
>>> #   pytest tests/test_api.py

Author
------
Warith Harchaoui, Ph.D. — https://linkedin.com/in/warith-harchaoui/
"""

from __future__ import annotations

import contextlib
from datetime import datetime, timezone
from pathlib import Path

import pytest

# FastAPI is in the ``[api]`` optional extra — skip cleanly otherwise.
fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

FAKE_CRED = {
    "sftp_host": "sftp.example.com",
    "sftp_login": "alice",
    "sftp_https": "https://example.com/uploads",
    "sftp_destination_path": "/var/www/uploads",
    "sftp_passwd": "hunter2",
}


@pytest.fixture(scope="module")
def client():
    """Yield a TestClient bound to the sftp-helper FastAPI app."""
    from sftp_helper.api import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def authed(monkeypatch):
    """Patch the server-side credential snapshot so ``_cred_or_503()``
    proceeds instead of the always-503 branch this suite otherwise runs
    under (no real SFTP target configured). Returns the fake cred dict so
    tests can assert against its fields (e.g. the masked password)."""
    import sftp_helper.api as api_mod

    monkeypatch.setattr(api_mod, "_SERVER_CRED", dict(FAKE_CRED))
    return FAKE_CRED


# ---------------------------------------------------------------------------
# Meta / wiring
# ---------------------------------------------------------------------------


def test_health_returns_ok(client):
    """``/health`` should return 200 + ``{"status": "ok"}``."""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_openapi_lists_expected_endpoints_with_expected_shapes(client):
    """The OpenAPI spec lists every route, and spot-checks two request/
    response contracts that matter to callers: ``/upload``'s ``overwrite``
    default and ``/remote-stat``'s required ``remote`` query param."""
    r = client.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    paths = schema["paths"]
    expected = {
        "/health",
        "/show-credentials",
        "/normalize-path",
        "/strip-path",
        "/exists",
        "/dir-exists",
        "/list",
        "/remote-stat",
        "/upload",
        "/download",
        "/delete",
        "/mkdir",
        "/tempfile",
    }
    assert expected.issubset(set(paths.keys()))

    body_schema_ref = paths["/upload"]["post"]["requestBody"]["content"]["multipart/form-data"][
        "schema"
    ]["$ref"]
    body_schema_name = body_schema_ref.rsplit("/", 1)[-1]
    props = schema["components"]["schemas"][body_schema_name]["properties"]
    assert props["overwrite"]["default"] is True

    stat_params = {p["name"]: p for p in paths["/remote-stat"]["get"]["parameters"]}
    assert stat_params["remote"]["required"] is True


def test_docs_endpoint_is_served(client):
    """``/docs`` should serve the Swagger UI landing HTML."""
    r = client.get("/docs")
    assert r.status_code == 200
    assert "swagger" in r.text.lower() or "openapi" in r.text.lower()


# ---------------------------------------------------------------------------
# Exception mapping
# ---------------------------------------------------------------------------


def test_value_error_maps_to_400_not_500(client):
    """A library ValueError (e.g. an unsafe path) is a 400, not an opaque 500."""
    r = client.get("/normalize-path", params={"path": "foo\nbar"})
    assert r.status_code == 400
    assert "detail" in r.json()


def test_missing_credentials_maps_to_503_not_generic_500(client):
    """``_cred_or_503``'s HTTPException(503) isn't swallowed by the generic
    Exception handler — it must keep its own status code, not become a 502.
    This suite runs with no ``authed`` fixture applied here, so the server
    genuinely has no credentials loaded."""
    r = client.get("/show-credentials")
    assert r.status_code == 503


def test_sftp_error_handler_reraises_http_exception_unchanged():
    """``_sftp_error_handler``'s ``isinstance`` guard must pass an
    ``HTTPException`` through unchanged rather than flatten it to a 502.
    Under FastAPI's normal routing, a more specific default handler already
    catches ``HTTPException`` before this generic one ever sees it, so the
    guard can only be exercised by calling the handler directly — this is
    what keeps ``_cred_or_503``'s 503 correct if that routing precedence
    ever changes."""
    import sftp_helper.api as api_mod

    exc = HTTPException(status_code=503, detail="no creds")
    with pytest.raises(HTTPException) as excinfo:
        api_mod._sftp_error_handler(None, exc)
    assert excinfo.value is exc


# ---------------------------------------------------------------------------
# Pure / read endpoints
# ---------------------------------------------------------------------------


def test_normalize_path_endpoint_is_pure(client):
    """``/normalize-path`` needs no credentials and no network — pure helper."""
    r = client.get("/normalize-path", params={"path": "foo/bar///"})
    assert r.status_code == 200
    assert r.json() == {"path": "/foo/bar"}


def test_show_credentials_endpoint_masks_password(client, authed):
    r = client.get("/show-credentials")
    assert r.status_code == 200
    body = r.json()
    assert body["sftp_passwd"] == "***"
    assert body["sftp_host"] == authed["sftp_host"]


def test_strip_path_endpoint(client, authed, monkeypatch):
    import sftp_helper.api as api_mod

    monkeypatch.setattr(api_mod, "strip_sftp_path", lambda *_a, **_k: "/foo/bar")
    r = client.get("/strip-path", params={"address": "sftp://host/foo/bar"})
    assert r.status_code == 200
    assert r.json() == {"path": "/foo/bar"}


def test_exists_and_dir_exists_endpoints(client, authed, monkeypatch):
    """Both probes return ``{"exists": bool, "remote": ...}`` with a 200
    either way — unlike the CLI, the HTTP surface has no reason to encode
    "missing" as a non-2xx status."""
    import sftp_helper.api as api_mod

    monkeypatch.setattr(api_mod, "remote_file_exists", lambda *_a, **_k: True)
    r = client.get("/exists", params={"remote": "/var/www/uploads/a.txt"})
    assert r.status_code == 200
    assert r.json() == {"exists": True, "remote": "/var/www/uploads/a.txt"}

    monkeypatch.setattr(api_mod, "remote_file_exists", lambda *_a, **_k: False)
    r = client.get("/exists", params={"remote": "/var/www/uploads/a.txt"})
    assert r.json()["exists"] is False

    monkeypatch.setattr(api_mod, "remote_dir_exist", lambda *_a, **_k: True)
    r = client.get("/dir-exists", params={"remote": "/var/www/uploads"})
    assert r.status_code == 200
    assert r.json() == {"exists": True, "remote": "/var/www/uploads"}


def test_list_endpoint_forwards_recursive_flag(client, authed, monkeypatch):
    import sftp_helper.api as api_mod

    calls = []

    def fake_list_dir(remote, cred, *, recursive):
        calls.append((remote, recursive))
        return ["a.txt", "sub/b.txt"] if recursive else ["a.txt"]

    monkeypatch.setattr(api_mod, "list_dir", fake_list_dir)

    r = client.get("/list", params={"remote": "/var/www/uploads"})
    assert r.status_code == 200
    assert r.json()["entries"] == ["a.txt"]
    assert calls[-1] == ("/var/www/uploads", False)

    r = client.get("/list", params={"remote": "/var/www/uploads", "recursive": "true"})
    assert r.json()["entries"] == ["a.txt", "sub/b.txt"]
    assert calls[-1] == ("/var/www/uploads", True)


def test_remote_stat_endpoint_found_and_missing(client, authed, monkeypatch):
    import sftp_helper.api as api_mod

    mtime = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    monkeypatch.setattr(api_mod, "remote_stat", lambda *_a, **_k: {"size": 42, "mtime": mtime})
    r = client.get("/remote-stat", params={"remote": "/var/www/uploads/a.txt"})
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "exists": True,
        "remote": "/var/www/uploads/a.txt",
        "size": 42,
        "mtime": mtime.isoformat(),
    }

    monkeypatch.setattr(api_mod, "remote_stat", lambda *_a, **_k: None)
    r = client.get("/remote-stat", params={"remote": "/var/www/uploads/missing.txt"})
    assert r.status_code == 200
    assert r.json() == {"exists": False, "remote": "/var/www/uploads/missing.txt"}


# ---------------------------------------------------------------------------
# Action endpoints
# ---------------------------------------------------------------------------


def test_upload_endpoint_success_returns_address_and_cleans_up_temp_dir(
    client, authed, monkeypatch
):
    import sftp_helper.api as api_mod

    captured = {}

    def fake_upload(src, _cred, remote, *, overwrite):
        assert Path(src).exists()
        captured["tmp_dir"] = Path(src).parent
        captured["remote"] = remote
        captured["overwrite"] = overwrite
        return "/var/www/uploads/a.txt"

    monkeypatch.setattr(api_mod, "upload", fake_upload)
    r = client.post(
        "/upload", files={"file": ("a.txt", b"hello")}, data={"remote": "/var/www/uploads/a.txt"}
    )
    assert r.status_code == 200
    assert r.json() == {"sftp_address": "/var/www/uploads/a.txt"}
    assert captured["remote"] == "/var/www/uploads/a.txt"
    assert captured["overwrite"] is True
    # The background cleanup task runs before TestClient returns.
    assert not captured["tmp_dir"].exists()


def test_upload_endpoint_failure_cleans_up_temp_dir_synchronously(client, authed, monkeypatch):
    """FastAPI only wires a ``background: BackgroundTasks`` parameter onto
    the outgoing Response when the endpoint returns normally. When
    ``upload()`` raises, the generic Exception handler builds a brand-new
    JSONResponse that never carries this request's background tasks, so a
    task queued via ``background.add_task`` before the raise would silently
    never run. ``upload_endpoint`` must therefore clean up synchronously in
    an ``except`` block (mirroring ``download_endpoint``)."""
    import sftp_helper.api as api_mod

    captured: dict = {}

    def failing_upload(src, _cred, _remote, *, overwrite=True):
        assert Path(src).exists()
        captured["tmp_dir"] = Path(src).parent
        raise Exception("simulated SFTP failure")

    monkeypatch.setattr(api_mod, "upload", failing_upload)

    # Starlette's TestClient re-raises the original exception by default
    # (``raise_server_exceptions=True``) even though `_sftp_error_handler`
    # would turn it into a clean 502 for a real deployed server — see
    # `ServerErrorMiddleware`, which always re-raises after sending its
    # response so tooling like this can observe the underlying error. What
    # matters here is that `upload_endpoint`'s own `except` block (which
    # runs well before that middleware) has already fired by this point.
    with pytest.raises(Exception, match="simulated SFTP failure"):
        client.post("/upload", files={"file": ("a.txt", b"hello")})
    assert not captured["tmp_dir"].exists()


def test_download_endpoint_success_streams_file_and_cleans_up_temp_dir(
    client, authed, monkeypatch
):
    import sftp_helper.api as api_mod

    captured = {}

    def fake_download(remote, _cred, local):
        captured["remote"] = remote
        captured["tmp_dir"] = Path(local).parent
        Path(local).write_bytes(b"file contents")
        return local

    monkeypatch.setattr(api_mod, "download", fake_download)
    r = client.get("/download", params={"remote": "/var/www/uploads/a.txt"})
    assert r.status_code == 200
    assert r.content == b"file contents"
    assert "a.txt" in r.headers["content-disposition"]
    assert not captured["tmp_dir"].exists()


def test_download_endpoint_failure_cleans_up_temp_dir_synchronously(client, authed, monkeypatch):
    """Mirrors the upload-side failure test: the ``except`` block must clean
    up synchronously since a raised exception never reaches the background
    task registered on the (never-sent) success response."""
    import sftp_helper.api as api_mod

    captured: dict = {}

    def failing_download(_remote, _cred, local):
        captured["tmp_dir"] = Path(local).parent
        raise Exception("simulated SFTP failure")

    monkeypatch.setattr(api_mod, "download", failing_download)
    with pytest.raises(Exception, match="simulated SFTP failure"):
        client.get("/download", params={"remote": "/var/www/uploads/a.txt"})
    assert not captured["tmp_dir"].exists()


def test_delete_endpoint_returns_deleted_flag(client, authed, monkeypatch):
    import sftp_helper.api as api_mod

    monkeypatch.setattr(api_mod, "delete", lambda *_a, **_k: True)
    r = client.delete("/delete", params={"remote": "/var/www/uploads/a.txt"})
    assert r.status_code == 200
    assert r.json() == {"deleted": True, "remote": "/var/www/uploads/a.txt"}

    monkeypatch.setattr(api_mod, "delete", lambda *_a, **_k: False)
    r = client.delete("/delete", params={"remote": "/var/www/uploads/a.txt"})
    assert r.json()["deleted"] is False


def test_mkdir_endpoint_creates_and_confirms(client, authed, monkeypatch):
    import sftp_helper.api as api_mod

    calls = []
    monkeypatch.setattr(
        api_mod, "make_remote_directory", lambda remote, cred: calls.append(remote)
    )
    r = client.post("/mkdir", data={"remote": "/var/www/uploads/a/b/c"})
    assert r.status_code == 200
    assert r.json() == {"created": True, "remote": "/var/www/uploads/a/b/c"}
    assert calls == ["/var/www/uploads/a/b/c"]


def test_tempfile_endpoint_reserves_and_returns_payload(client, authed, monkeypatch):
    import sftp_helper.api as api_mod

    @contextlib.contextmanager
    def fake_remote_tempfile(cred, ext="", subdir=""):
        assert ext == "txt"
        assert subdir == "batch-42"
        yield ("/var/www/uploads/abc123.txt", "https://example.com/uploads/abc123.txt")

    monkeypatch.setattr(api_mod, "remote_tempfile", fake_remote_tempfile)
    r = client.post("/tempfile", data={"ext": "txt", "subdir": "batch-42"})
    assert r.status_code == 200
    assert r.json() == {
        "sftp_address": "/var/www/uploads/abc123.txt",
        "url": "https://example.com/uploads/abc123.txt",
    }
