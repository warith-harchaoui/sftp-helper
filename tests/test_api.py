"""
Smoke tests for the FastAPI HTTP surface.

Only exercises endpoints that do not require a live SFTP server
(``/health``, ``/normalize-path``, plus OpenAPI schema introspection
to catch endpoint-name drift). Heavier round-trip tests belong to the
``integration`` suite where a real SFTP target is available.

Usage Example
-------------
>>> #   pytest tests/test_api.py

Author
------
Warith Harchaoui, Ph.D. — https://linkedin.com/in/warith-harchaoui/
"""

from __future__ import annotations

import pytest

# FastAPI is in the ``[api]`` optional extra — skip cleanly otherwise.
fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="module")
def client():
    """Yield a TestClient bound to the sftp-helper FastAPI app."""
    from sftp_helper.api import app

    with TestClient(app) as c:
        yield c


def test_health_returns_ok(client):
    """``/health`` should return 200 + ``{"status": "ok"}``."""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_openapi_lists_expected_endpoints(client):
    """The OpenAPI spec should list every expected route path."""
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
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


def test_docs_endpoint_is_served(client):
    """``/docs`` should serve the Swagger UI landing HTML."""
    r = client.get("/docs")
    assert r.status_code == 200
    assert "swagger" in r.text.lower() or "openapi" in r.text.lower()


def test_normalize_path_endpoint_is_pure(client):
    """``/normalize-path`` needs no credentials and no network — pure helper."""
    r = client.get("/normalize-path", params={"path": "foo/bar///"})
    assert r.status_code == 200
    assert r.json() == {"path": "/foo/bar"}


def test_upload_route_exposes_overwrite_param(client):
    """``/upload`` request-body schema exposes ``overwrite`` (default True)."""
    r = client.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    body_schema_ref = schema["paths"]["/upload"]["post"]["requestBody"]["content"][
        "multipart/form-data"
    ]["schema"]["$ref"]
    body_schema_name = body_schema_ref.rsplit("/", 1)[-1]
    props = schema["components"]["schemas"][body_schema_name]["properties"]
    assert props["overwrite"]["default"] is True


def test_remote_stat_route_listed_in_reads(client):
    """``/remote-stat`` is a GET route taking a required ``remote`` query param."""
    r = client.get("/openapi.json")
    assert r.status_code == 200
    op = r.json()["paths"]["/remote-stat"]["get"]
    params = {p["name"]: p for p in op["parameters"]}
    assert params["remote"]["required"] is True


def test_value_error_maps_to_400_not_500(client):
    """A library ValueError (e.g. an unsafe path) is a 400, not an opaque 500."""
    r = client.get("/normalize-path", params={"path": "foo\nbar"})
    assert r.status_code == 400
    assert "detail" in r.json()


def test_missing_credentials_maps_to_503_not_generic_500(client):
    """``_cred_or_503``'s HTTPException(503) isn't swallowed by the generic
    Exception handler — it must keep its own status code, not become a 502."""
    r = client.get("/show-credentials")
    # This test suite runs with no real SFTP target configured, so this is
    # always the 503 branch (see conftest / module docstring).
    assert r.status_code == 503


def test_upload_failure_cleans_up_temp_dir_synchronously(client, monkeypatch):
    """A raised exception from ``upload()`` must not leak the spooled temp dir.

    FastAPI only wires a ``background: BackgroundTasks`` parameter onto the
    outgoing Response when the endpoint returns normally. When ``upload()``
    raises, the generic Exception handler builds a brand-new JSONResponse
    that never carries this request's background tasks, so a task queued
    via ``background.add_task`` before the raise would silently never run.
    ``upload_endpoint`` must therefore clean up synchronously in an
    ``except`` block (mirroring ``download_endpoint``) rather than rely on
    the background task for the failure path.
    """
    from pathlib import Path

    import sftp_helper.api as api_mod

    # Fake server-side credentials so `_cred_or_503()` proceeds instead of
    # short-circuiting to 503 (this test suite otherwise runs with none).
    monkeypatch.setattr(
        api_mod,
        "_SERVER_CRED",
        {
            "sftp_host": "sftp.example.com",
            "sftp_login": "alice",
            "sftp_https": "https://example.com/uploads",
            "sftp_destination_path": "/",
        },
    )

    captured: dict = {}

    def failing_upload(src, _cred, _remote, *, overwrite=True):
        # Confirm the spooled file exists at call time, then record its
        # parent temp dir so the test can check it was actually removed.
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
    # The temp dir must be gone right away — not left for a background
    # task that FastAPI never actually schedules on this failure path.
    assert not captured["tmp_dir"].exists()
