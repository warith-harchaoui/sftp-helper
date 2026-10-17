---
name: sftp-helper
description: >-
  Move files to and from an SFTP server. Upload one file or many, download one
  or many, check whether a remote file or directory exists, list a directory
  (with or without stat), stat a remote path, create remote directories, mint
  a remote temporary path, delete a remote file, normalize a remote path, and
  strip an `sftp://` URL down to its path. Credentials come from a YAML / JSON
  / .env config or the environment, never from the skill. Use when the user
  says "upload this over SFTP / to my server", "scp this up", "download this
  from the server", "does this remote file exist", "list the remote
  directory", "mkdir on the server", "delete this remote file", "publish this
  to my web host", "FTP this", or names `sftp-helper`, `sftp-helper-click`,
  `sftp-helper-mcp`, `import sftp_helper as sh`, `paramiko`, `sftp://`. Do NOT
  use for S3-compatible object storage (bucket-helper), local file management
  (os-helper), or git / rsync workflows.
license: BSD-3-Clause
metadata:
  author: Warith Harchaoui
  package: sftp-helper
  suite: ai-helpers
  homepage: https://deraison.ai/ai-helpers
---

# sftp-helper — files to and from an SFTP server

`sftp-helper` moves files between the machine and an SFTP host. It is **the
suite's honest exception to local-first**, together with `bucket-helper`: its
whole job is to put data somewhere else. That somewhere is the host *the user*
configured — no vendor default, no telemetry, no relay.

## ⚠️ Credentials and destructive calls

- **Credentials never live in this skill.** `credentials()` reads them, in
  precedence order, from a JSON / YAML config, a `.env`, then environment
  variables (via `os_helper.get_config`). Only `sftp_host`, `sftp_login` and
  `sftp_https` are mandatory; `sftp_passwd` / `sftp_key` and
  `sftp_destination_path` (default `/`) fall back to documented defaults, so a
  key-based login writing to the server root needs just the three.
- **`show-credentials` masks the password** — it prints `***`, and the schema
  stays stable for scripting. Even so, never paste a secret into a command
  line, never write one into a file the user did not name, and never echo one
  back.
- **`delete` removes a remote file, and an upload overwrites one.** Confirm
  the exact remote path with the user first; check `exists` when a key might
  already be in use. A web host's document root is not a scratch directory.

## Before anything: verify it is installed and configured

```bash
sftp-helper --help                               # argparse CLI (ships with the package)
python -c "import sftp_helper"                   # library import check
sftp-helper show-credentials --config settings.yaml   # resolves config, masks the secret
```

Install:

```bash
pip install sftp-helper                    # core: library + argparse CLI
pip install 'sftp-helper[cli]'             # + the click twin
pip install 'sftp-helper[api]'             # + FastAPI HTTP surface
pip install 'sftp-helper[mcp]'             # + MCP tools over the same app
```

Configuration starts from the repo's `settings.yaml.example` — copy it, fill
it in, and keep it out of version control.

## What it does, and how to invoke it

| Intent | CLI | Library |
|---|---|---|
| Send a file up | `sftp-helper upload` | `upload`, `upload_many` |
| Bring a file down | `sftp-helper download` | `download`, `download_many` |
| Does this remote file exist | `sftp-helper exists` | `remote_file_exists` |
| Does this remote directory exist | `sftp-helper dir-exists` | `remote_dir_exist` |
| List a remote directory | `sftp-helper list` | `list_dir`, `list_dir_stat` |
| Size / mtime of a remote path | `sftp-helper remote-stat` | `remote_stat` |
| Create remote directories | `sftp-helper mkdir` | `make_remote_directory` |
| A scratch path on the remote | `sftp-helper tempfile` | `remote_tempfile` |
| Remove a remote file | `sftp-helper delete` | `delete` |
| Tidy a remote path | `sftp-helper normalize-path` | `normalize_path` |
| Split an `sftp://` address | `sftp-helper strip-path` | `strip_sftp_path` |
| Show the resolved config | `sftp-helper show-credentials` | `credentials` |

Quick examples:

```bash
sftp-helper upload --config settings.yaml --input ./site.html --remote /www/site.html
sftp-helper exists --config settings.yaml --remote /www/site.html
sftp-helper list   --config settings.yaml --remote /www
```

```python
import sftp_helper as sh

url = sh.upload("./site.html", "/www/site.html")  # public URL, from sftp_https
sh.upload_many([("./a.png", "/www/a.png"), ("./b.png", "/www/b.png")])
```

`upload` returns the public URL built from the configured `sftp_https` base —
that URL, not the local path, is what you report back.

For the full flag matrix, the config keys and the output contract, read
`references/cli-reference.md`. For the HTTP API and MCP tools, read
`references/surfaces.md`. For the exhaustive trigger list, read
`references/triggers.md`.

## Rules of thumb

- **Check before you overwrite.** `exists` is one cheap call; an overwritten
  file on someone's server is not recoverable.
- **Confirm before `delete`.** Name the exact remote path back to the user
  and wait for a yes.
- **Batch with `upload_many` / `download_many`**, not a shell loop: they reuse
  one connection instead of re-authenticating per file.
- **`mkdir` creates parents.** Create the directory before a deep upload
  rather than discovering the failure mid-transfer.
- **`normalize_path` and `strip_sftp_path` exist so you stop doing string
  surgery** on remote paths — double slashes, trailing slashes and
  `sftp://host/...` addresses are all handled.
- **Report the published URL and the byte count after a transfer** — do not
  re-upload to confirm.
