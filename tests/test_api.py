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
