# sftp-helper non-CLI surfaces

`sftp-helper` exposes the same operations through four surfaces. The Python
library and argparse CLI are always available; the others live behind optional
extras. **There is no GUI** (by design — see the note at the end).

## 1. Python library (default)

```python
import sftp_helper as sftph

sftph.credentials(config_path=None)                 # -> dict (file / dir / env / .env)
sftph.get_client_sftp(cred)                          # context manager -> paramiko.SFTPClient
sftph.upload(local_path, cred, sftp_address="")      # -> remote address (auto-hashed if empty)
sftph.download(sftp_address, cred, local_path="")    # -> local path (remote basename default)
sftph.delete(sftp_address, cred)                     # -> True (idempotent)
sftph.remote_file_exists(sftp_address, cred)         # -> bool
sftph.remote_dir_exist(ftp_dir, cred)                # -> bool
sftph.make_remote_directory(ftp_directory, cred)     # mkdir -p, returns None
sftph.normalize_path(path)                            # -> str (pure, no network)
sftph.strip_sftp_path(sftp_address, cred)            # -> str (drop sftp://host)
with sftph.remote_tempfile(cred, ext="", subdir="") as (addr, url): ...  # auto-delete on exit
```

The public API is fixed via `sftp_helper.__all__` — sibling repos in the
AI Helpers suite depend on these names, so treat them as stable.

## 2. CLI — argparse (default) and click

- **argparse** `sftp-helper <sub> …` — ships with the base package, zero extra
  deps. Primary surface. See `cli-reference.md`.
- **click** `sftp-helper-click <sub> …` — install `sftp-helper[cli]`. Same
  subcommands and flag names; nicer `--help`, shell completion.

## 3. HTTP API — FastAPI (`sftp-helper[api]`)

```bash
pip install 'sftp-helper[api]'
SFTP_HELPER_CONFIG=./sftp_config.json uvicorn sftp_helper.api:app --host 0.0.0.0 --port 8000
# OpenAPI docs: http://localhost:8000/docs
```

Credentials are loaded **once at import time** from `SFTP_HELPER_CONFIG` or the
`SFTP_*` env vars — the API is the trusted server-side view of a *single* SFTP
target and never accepts credentials in a request body. Endpoints that need
credentials return HTTP 503 if the server booted without any.

Endpoints:
- `GET  /health` — liveness probe → `{"status":"ok"}`.
- `GET  /show-credentials` — resolved creds, password masked.
- `GET  /normalize-path?path=…` — pure path canonicalization.
- `GET  /strip-path?address=…` — strip `sftp://host`.
- `GET  /exists?remote=…` — `{"exists": bool, "remote": …}`.
- `GET  /dir-exists?remote=…` — directory existence.
- `POST /upload` — multipart `file` + `remote` form field → `{"sftp_address": …}`.
- `GET  /download?remote=…&filename=…` — streams the file bytes (`FileResponse`).
- `DELETE /delete?remote=…` — `{"deleted": bool, "remote": …}`.
- `POST /mkdir` — form `remote` → `{"created": true, …}`.
- `POST /tempfile` — form `ext`, `subdir` → `{"sftp_address": …, "url": …}`
  (the reserved file is deleted on context exit, matching the CLI).

Uploads stream to a temp file; temp dirs are cleaned via `BackgroundTasks`.

## 4. MCP server — FastAPI-MCP (`sftp-helper[api,mcp]`)

```bash
pip install 'sftp-helper[api,mcp]'
sftp-helper-mcp                  # serves FastAPI + MCP on :8000
# or: python -m sftp_helper.mcp
```

Wraps the exact FastAPI app with `fastapi_mcp` — the same endpoints become MCP
tools (`upload`, `download`, `delete`, `exists`, …) for any MCP-aware host
(Claude Desktop, custom agents, IDE integrations). Host/port via
`SFTP_HELPER_HOST` / `SFTP_HELPER_PORT`.

## No GUI (by design)

Unlike some sibling helpers, `sftp-helper` ships **no** `/gui` bench and no
graphical surface. Its purpose is moving data to/from a remote server, and
FileZilla / Cyberduck / Transmit already ship polished SFTP file explorers. A
forward-looking dashboard concept (pipeline-artifact view, storage-health panel)
is written up in the repo-root `GUI.md` as a *design plan only* — no such code
ships today. Do not advertise a GUI surface.
