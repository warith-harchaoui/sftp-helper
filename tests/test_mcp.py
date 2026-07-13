"""
Smoke test for the MCP surface (``sftp_helper.mcp``).

Verifies that the MCP wrapper around the FastAPI app imports without
error, exposes the underlying FastAPI ``app`` object, and that the
``mcp`` handler is attached. Full protocol round-trips belong to a
separate integration suite once the MCP client tooling is stable in
CI.

Usage Example
-------------
>>> #   pytest tests/test_mcp.py

Author
------
Warith Harchaoui, Ph.D. — https://linkedin.com/in/warith-harchaoui/
"""

from __future__ import annotations

import pytest

# fastapi_mcp lives in the ``[mcp]`` optional extra — skip cleanly if absent.
pytest.importorskip("fastapi_mcp")


def test_mcp_module_imports_and_exposes_app():
    """The MCP module must import and re-expose the FastAPI app + mcp handler."""
    from sftp_helper import mcp as mcp_module

    assert hasattr(mcp_module, "app"), "sftp_helper.mcp must re-expose `app`."
    assert hasattr(mcp_module, "mcp"), "sftp_helper.mcp must expose the `mcp` handler."


def test_main_entrypoint_is_callable():
    """The ``sftp-helper-mcp`` console entry point should be a callable."""
    from sftp_helper.mcp import main

    assert callable(main)
