# sftp-helper non-CLI surfaces

## 1. Library

```python
import sftp_helper as sftph
```

Public API (`sftp_helper.__all__`): `credentials`, `get_client_sftp`,
`normalize_path`, `strip_sftp_path`, `remote_file_exists`, `remote_dir_exist`,
`delete`, `upload`, `download`, `upload_many`, `download_many`,
`make_remote_directory`, `remote_tempfile`, `list_dir`, `list_dir_stat`,
`remote_stat`.

```python
cred = sftph.credentials("settings.yaml")
addr = sftph.upload("./site.html", cred, "/www/site.html")  # → the remote address written
# one connection, many files
sftph.upload_many([("./a.png", "/www/a.png"), ("./b.png", "/www/b.png")], cred)
```

`credentials()` returns the resolved config dict. Every operation drives the
system OpenSSH `sftp` client as a short batch, so there is no client object to
hand out: `get_client_sftp()` is a deprecated shim that checks the connection
and yields the same `cred` dict, kept so older `with` call sites still import.

Logging and file management route through `os_helper` — the suite convention.

## 2. CLI — click (core)

`sftp-helper`. See `cli-reference.md`.

## 3. HTTP API — FastAPI (`[api]`)

```bash
pip install 'sftp-helper[api]'
SFTP_HELPER_CONFIG=$PWD/settings.yaml uvicorn sftp_helper.api:app --host 127.0.0.1 --port 8000
# OpenAPI docs at /docs
```

| Method | Route |
|---|---|
| GET | `/health`, `/show-credentials`, `/normalize-path`, `/strip-path` |
| GET | `/exists`, `/dir-exists`, `/list`, `/remote-stat`, `/download` |
| POST | `/upload`, `/mkdir`, `/tempfile` |
| DELETE | `/delete` |

The verbs are honest: reading is `GET`, removing is `DELETE`. The server reads
credentials from its own environment and does **not** accept them per request,
so an exposed port cannot be used to transfer someone else's files. Bind it to
`127.0.0.1` and keep it there.

## 4. MCP — `fastapi-mcp` over the *same* app (`[mcp]`)

```bash
pip install 'sftp-helper[mcp]'
sftp-helper-mcp                     # same app, MCP mounted at /mcp
```

`sftp_helper.mcp` takes the FastAPI app from `sftp_helper.api` and mounts
`FastApiMCP` on it. Every MCP tool *is* an HTTP route, so the two surfaces
cannot drift and one process serves both doors.

Register it with Claude Code:

```bash
claude mcp add sftp-helper --transport http http://127.0.0.1:8000/mcp
```

**An agent holding these tools can overwrite and delete files on the user's
server.** The `delete` tool deserves an explicit confirmation every time; so
does an `upload` to a path that already exists.

## Where this sits in the suite

sftp-helper and `bucket-helper` are the suite's two transfer packages and the
only members whose job is to move data off the machine. They share the same
shape — `upload`, `download`, `exists`, `list`, `delete`, `tempfile`,
`strip-path` — so switching between a plain server and object storage is a
config change, not a rewrite.

Everything else in the suite stays local; these two exist because a pipeline
eventually has to publish its output somewhere the user chose.
