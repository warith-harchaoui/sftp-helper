"""SFTP Helper: Model Context Protocol (MCP) surface.

A thin adapter that exposes the FastAPI app from :mod:`sftp_helper.api` as MCP
tools, so any MCP-aware host (an agent runtime, an IDE integration, a custom
shell) can call the sftp-helper operations — upload, download, delete, exists,
dir-exists, mkdir, normalize-path, strip-path, tempfile, show-credentials —
as first-class tools, against the single SFTP target the server was started
with (strict host-key verification always on; credentials are loaded once at
server start, never accepted in a request body — see :mod:`sftp_helper.api`).
Uses `fastapi-mcp` (https://github.com/tadata-org/fastapi_mcp): one wrapper
publishes the whole existing HTTP surface, so the routes are never duplicated.

Install the extra to pull in ``fastapi-mcp``::

    pip install "sftp-helper[mcp]"

Then run the server (HTTP API + MCP endpoint at ``/mcp``)::

    sftp-helper-mcp                 # console entry point
    python -m sftp_helper.mcp       # equivalent

Author
------
Warith HARCHAOUI, Ph.D. — https://linkedin.com/in/warith-harchaoui/
"""

from __future__ import annotations

try:
    from fastapi_mcp import FastApiMCP
except ImportError as exc:  # pragma: no cover - exercised only without the extra
    raise ImportError(
        'The MCP surface needs the [mcp] extra: pip install "sftp-helper[mcp]"'
    ) from exc

# Reuse the exact same FastAPI app: MCP is a thin wrapper on top, no new routes.
from sftp_helper.api import app

# Publish the HTTP endpoints (upload / download / delete / exists / mkdir / ...)
# as MCP tools.
mcp = FastApiMCP(
    app,
    name="sftp-helper",
    description=(
        "sftp-helper MCP tools: upload, download, delete, exists, dir-exists, "
        "mkdir, normalize-path, strip-path, and tempfile against a single SFTP "
        "target reached via the system OpenSSH client, with strict host-key "
        "verification always on. Credentials are fixed server-side at start "
        "time — no MCP tool call accepts or exposes them."
    ),
)
# Newer fastapi-mcp splits mount() into transport-specific mount_http(); fall back to
# the legacy mount() so a range of fastapi-mcp versions keeps working.
if hasattr(mcp, "mount_http"):
    mcp.mount_http()
else:  # pragma: no cover - legacy fastapi-mcp
    mcp.mount()


def main() -> None:
    """Console entry point (``sftp-helper-mcp``): serve the API + MCP endpoint.

    Boots the FastAPI app (now serving both the plain HTTP routes and the
    ``/mcp`` MCP endpoint) with uvicorn in a single worker. Local-first: binds
    to loopback by default (override with ``SFTP_HELPER_HOST`` /
    ``SFTP_HELPER_PORT``).
    """
    import os

    import uvicorn

    host = os.environ.get("SFTP_HELPER_HOST", "127.0.0.1")
    port = int(os.environ.get("SFTP_HELPER_PORT", "8000"))
    print(f"SFTP Helper API + MCP -> http://{host}:{port}  (MCP at /mcp)")
    uvicorn.run(app, host=host, port=port, workers=1)


if __name__ == "__main__":  # pragma: no cover
    main()
