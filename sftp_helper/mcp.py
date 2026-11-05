"""SFTP Helper: Model Context Protocol (MCP) surface.

A thin adapter that exposes the FastAPI app from :mod:`sftp_helper.api` as MCP
tools, so any MCP-aware host (an agent runtime, an IDE integration, a custom
shell) can call the sftp-helper operations (upload, download, delete, exists,
dir-exists, list, remote-stat, mkdir, normalize-path, strip-path, tempfile,
health) as first-class tools, against the single SFTP target the server was
started with. Strict host-key verification stays on always; credentials are
loaded once at server start and never accepted in a request body, see
:mod:`sftp_helper.api`. ``/show-credentials`` stays an HTTP-only route: it is
deliberately left out of the MCP tools, so an agent cannot read the host,
login or key path back.
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

from fastapi.routing import APIRoute

# Reuse the exact same FastAPI app: MCP is a thin wrapper on top, no new routes.
from sftp_helper.api import app

# Routes that must never become MCP tools. ``/show-credentials`` returns the
# host, login and key path (password masked): fine for the operator on the
# loopback HTTP API, not something to hand an agent. The operation id is read
# off the route rather than hard-coded, so renaming the handler cannot quietly
# re-expose it.
_HTTP_ONLY_PATHS = {"/show-credentials"}
_EXCLUDED_OPERATIONS = [
    route.operation_id or route.unique_id
    for route in app.routes
    if isinstance(route, APIRoute) and route.path in _HTTP_ONLY_PATHS
]

# Publish every other HTTP endpoint (upload / download / delete / exists /
# list / mkdir / ...) as an MCP tool.
mcp = FastApiMCP(
    app,
    name="sftp-helper",
    description=(
        "sftp-helper MCP tools: upload, download, delete, exists, dir-exists, "
        "list, remote-stat, mkdir, normalize-path, strip-path, tempfile and "
        "health against a single SFTP target reached via the system OpenSSH "
        "client, with strict host-key verification always on. Credentials are "
        "fixed server-side at start time — no MCP tool call accepts or "
        "exposes them."
    ),
    exclude_operations=_EXCLUDED_OPERATIONS,
)
# Newer fastapi-mcp splits mount() into transport-specific mount_http(); fall back to
# the legacy mount() so a range of fastapi-mcp versions keeps working.
if hasattr(mcp, "mount_http"):
    mcp.mount_http()
else:  # pragma: no cover - legacy fastapi-mcp
    mcp.mount()


def main(argv: list[str] | None = None) -> None:
    """Console entry point (``sftp-helper-mcp``): serve the API + MCP endpoint.

    Boots the FastAPI app (now serving both the plain HTTP routes and the
    ``/mcp`` MCP endpoint) with uvicorn in a single worker.
    Local-first: binds to loopback by default (override with ``--host`` /
    ``--port`` or ``SFTP_HELPER_HOST`` / ``SFTP_HELPER_PORT``). A click command,
    so ``--help`` answers instead of starting the server.
    """
    import click

    @click.command(context_settings={"help_option_names": ["-h", "--help"]})
    @click.option("--host", envvar="SFTP_HELPER_HOST", default="127.0.0.1", show_default=True)
    @click.option("--port", envvar="SFTP_HELPER_PORT", default=8000, type=int, show_default=True)
    def serve(host: str, port: int) -> None:
        """Serve the SFTP Helper HTTP API and its MCP endpoint (/mcp)."""
        import uvicorn

        print(f"SFTP Helper API + MCP -> http://{host}:{port}  (MCP at /mcp)")
        uvicorn.run(app, host=host, port=port, workers=1)

    serve.main(args=argv, prog_name="sftp-helper-mcp")


if __name__ == "__main__":  # pragma: no cover
    main()
