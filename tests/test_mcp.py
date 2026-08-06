"""
Smoke test for the MCP surface (`sftp_helper.mcp`).

Gated on the ``mcp`` extra (FastAPI + fastapi-mcp). Importing `sftp_helper.mcp`
mounts an MCP endpoint onto the FastAPI app; we check the endpoint is wired
and that the HTTP API keeps serving alongside it, using only ``/health``
(no live SFTP server needed — same constraint as ``test_api.py``). Skips
cleanly when the extra isn't installed, so the default suite is unaffected.

Usage Example
-------------
>>> #   pytest tests/test_mcp.py

Author
------
Warith Harchaoui, Ph.D. — https://linkedin.com/in/warith-harchaoui/
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("fastapi_mcp")
httpx = pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from sftp_helper import mcp as mcp_module  # noqa: E402  (import mounts MCP on the app)


def test_mcp_endpoint_is_mounted() -> None:
    """Importing the module publishes an `/mcp` endpoint named 'sftp-helper'."""
    paths = {r.path for r in mcp_module.app.routes}
    assert any("/mcp" in p for p in paths), paths
    assert mcp_module.mcp.name == "sftp-helper"


def test_api_still_served_next_to_mcp() -> None:
    """The FastAPI routes still work once the MCP endpoint is mounted."""
    with TestClient(mcp_module.app) as client:
        res = client.get("/health")
        assert res.status_code == 200 and res.json()["status"] == "ok"
