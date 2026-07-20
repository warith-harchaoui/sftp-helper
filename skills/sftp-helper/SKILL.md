---
name: sftp-helper
description: >-
  Transfer files to and from a remote SFTP server with the `sftp-helper`
  toolkit — upload a local file (optionally under an auto content-hashed name),
  download a remote file, delete a remote file (idempotent), test whether a
  remote file or directory exists, create remote directories with `mkdir -p`
  semantics, normalize / strip `sftp://host` addresses, and reserve a unique
  remote temp path that auto-deletes (`remote_tempfile`). Backed by paramiko
  with STRICT host-key verification (RejectPolicy, no opt-out). Exposed as a
  Python library (`import sftp_helper as sftph`), two CLIs (`sftp-helper`
  argparse and `sftp-helper-click`), a FastAPI HTTP surface, and an MCP tool
  set. No GUI. Not local-first: its whole purpose is talking to a REMOTE server.

  TRIGGER — any of: the user names a remote file-transfer operation over
  SFTP/SSH ("upload this file to the SFTP server", "push / send this to sftp",
  "download / fetch / pull this file from the remote server", "get file X off
  the SFTP box", "does this file exist on the server", "is this remote directory
  there", "create / make the remote directory /a/b/c", "mkdir -p on the remote",
  "delete / remove this remote file", "stage a temp file on the server and give
  me a URL", "reserve a scratch path on sftp that cleans itself up", "normalize
  this remote path", "strip the sftp:// prefix / host from this address", "show
  / load my sftp credentials"); the user types or references a command
  (`sftp-helper`, `sftp-helper-click`, `sftp-helper-mcp`, subcommands
  `upload|download|delete|exists|dir-exists|mkdir|normalize-path|strip-path|
  tempfile|show-credentials`) or a library function (`credentials`,
  `get_client_sftp`, `upload`, `download`, `delete`, `remote_file_exists`,
  `remote_dir_exist`, `make_remote_directory`, `normalize_path`,
  `strip_sftp_path`, `remote_tempfile`); the user has an `sftp://…` address, a
  host + login + remote path, or an `sftp_config.json` / `sftp_config.yaml` /
  `SFTP_*` env vars and wants to move a file; the user wants to run the sftp
  API / MCP server, or asks how to install / run sftp-helper.

  SKIP when: the transfer is plain FTP/FTPS (not SFTP-over-SSH), SCP-only, or
  rsync/scp shell tooling the user explicitly wants; the target is cloud object
  storage — S3 / GCS / Azure / MinIO (use bucket-helper); the target is a
  local-only file copy/move with no remote server; downloading media from a URL
  or YouTube (use youtube-helper); interactive SSH shell / running remote
  commands (paramiko `exec_command`, Fabric) rather than file transfer; browsing
  a full remote directory tree in a GUI (FileZilla / Cyberduck). sftp-helper
  moves *files* over SFTP; it is not an S3 client, not an SSH shell, and not a
  URL downloader.
---

# sftp-helper — remote SFTP file-transfer toolkit

`sftp-helper` is a small Python toolkit for moving files to and from a remote
SFTP server over SSH, with strict host-key verification always on. The same
operations are reachable four ways (library, two CLIs, HTTP API, MCP) so an
agent can pick whichever fits. There is **no GUI**, and it is **not local-first**
— its entire job is talking to a remote server.

## Before anything: verify it is installed

```bash
sftp-helper --version              # argparse CLI (always installed with the pkg)
python -c "import sftp_helper"     # library import check
```

If missing, install it (paramiko is the only hard dependency — no system package):

```bash
pip install sftp-helper                 # core (library + argparse CLI)
pip install 'sftp-helper[cli]'          # + click CLI twin
pip install 'sftp-helper[api]'          # + FastAPI HTTP surface
pip install 'sftp-helper[api,mcp]'      # + MCP tools over FastAPI
```

## Credentials come first

Every network operation needs credentials — resolved (in order) from an explicit
JSON/YAML file, a directory containing one, then `SFTP_*` env vars / `.env`:

```python
import sftp_helper as sftph
cred = sftph.credentials("sftp_config.json")   # or credentials() for env / .env
```

Required keys: `sftp_host`, `sftp_login`, `sftp_passwd`, `sftp_destination_path`,
`sftp_https`. Optional: `sftp_port` (default `22`), `sftp_known_hosts` (an extra
known-hosts file to trust). See `references/config.md` for the full contract.

## The operations

Same names across the library, both CLIs, the API, and the MCP tools:

| Operation | CLI subcommand | Library function |
|-----------|----------------|------------------|
| Upload a local file | `sftp-helper upload` | `upload` |
| Download a remote file | `sftp-helper download` | `download` |
| Delete a remote file (idempotent) | `sftp-helper delete` | `delete` |
| Does a remote file exist | `sftp-helper exists` | `remote_file_exists` |
| Does a remote directory exist | `sftp-helper dir-exists` | `remote_dir_exist` |
| Create a remote dir (`mkdir -p`) | `sftp-helper mkdir` | `make_remote_directory` |
| Normalize a remote path | `sftp-helper normalize-path` | `normalize_path` |
| Strip `sftp://host` from an address | `sftp-helper strip-path` | `strip_sftp_path` |
| Reserve a self-deleting temp path | `sftp-helper tempfile` | `remote_tempfile` |
| Show resolved credentials (masked) | `sftp-helper show-credentials` | `credentials` |

Quick examples:

```bash
sftp-helper upload      --config sftp_config.json --input local.txt --remote /uploads/local.txt
sftp-helper download    --config sftp_config.json --remote /uploads/local.txt --output out.txt
sftp-helper exists      --config sftp_config.json --remote /uploads/local.txt   # exit 0=yes 1=no
sftp-helper mkdir       --config sftp_config.json --remote /uploads/a/b/c
sftp-helper delete      --config sftp_config.json --remote /uploads/local.txt
```

```python
import sftp_helper as sftph
cred = sftph.credentials("sftp_config.json")
sftph.upload("local.txt", cred, "/uploads/local.txt")
assert sftph.remote_file_exists("/uploads/local.txt", cred)
sftph.download("/uploads/local.txt", cred, "roundtrip.txt")
sftph.delete("/uploads/local.txt", cred)

# Stage-and-share: reserve a random remote path that auto-deletes on exit.
with sftph.remote_tempfile(cred, ext="json") as (addr, url):
    sftph.upload("payload.json", cred, addr)   # url is now live for a consumer
# on exit the remote file is gone
```

For every flag and the scripting output contract, read `references/cli-reference.md`.
For the API / MCP surfaces (endpoints, ports, credential loading), read
`references/surfaces.md`. For the credentials contract, read `references/config.md`.
For the exhaustive, auditable trigger list, read `references/triggers.md`.

## Rules of thumb

- **Load credentials once, pass the dict around.** Every op takes `cred`; there
  is no hidden global. `show-credentials` masks the password.
- **`upload` with no `--remote` derives a content-hashed name** under
  `sftp_destination_path` — deterministic and de-duplicating for identical bytes.
- **`delete` is idempotent** — removing an absent file returns success, so
  cleanup / retry paths stay simple.
- **`exists` / `dir-exists` use `test -e` exit codes** (0 = present, 1 = missing)
  so `if sftp-helper exists …; then …` reads naturally in shell.
- **Host-key verification is never disabled.** Unknown hosts raise
  `paramiko.SSHException`. To trust a non-default key, set `sftp_known_hosts` in
  the credentials — there is no flag to turn verification off.
- **Not for S3/GCS/Azure** (use bucket-helper), not for URL downloads (use
  youtube-helper), not for an interactive SSH shell. This moves files over SFTP.
- **After running, report the path/address the tool printed** and hand it back —
  do not re-run unless something failed.
