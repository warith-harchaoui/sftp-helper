# TRIGGERS — sftp-helper

This is the user-facing, exhaustive catalogue of what `sftp-helper` can do and
the natural-language phrasings, commands, functions, and context cues that should
invoke it — whether you call it yourself or drive it as a Claude / OpenCode
**skill** (see [`skills/sftp-helper/SKILL.md`](skills/sftp-helper/SKILL.md) and
its [`references/triggers.md`](skills/sftp-helper/references/triggers.md)).

`sftp-helper` moves **files** to and from a **remote SFTP server over SSH**, with
strict host-key verification always on. It is **not** local-first (its whole
purpose is a remote server), it is **not** an S3 client, **not** an SSH shell,
**not** a URL downloader, and it ships **no GUI**.

## Operations → how to invoke

| Intent | CLI | Library | API / MCP |
|--------|-----|---------|-----------|
| Upload a local file | `sftp-helper upload` | `upload` | `POST /upload` |
| Download a remote file | `sftp-helper download` | `download` | `GET /download` |
| Delete a remote file (idempotent) | `sftp-helper delete` | `delete` | `DELETE /delete` |
| Does a remote file exist | `sftp-helper exists` | `remote_file_exists` | `GET /exists` |
| Does a remote directory exist | `sftp-helper dir-exists` | `remote_dir_exist` | `GET /dir-exists` |
| Create a remote dir (`mkdir -p`) | `sftp-helper mkdir` | `make_remote_directory` | `POST /mkdir` |
| Normalize a remote path | `sftp-helper normalize-path` | `normalize_path` | `GET /normalize-path` |
| Strip `sftp://host` from an address | `sftp-helper strip-path` | `strip_sftp_path` | `GET /strip-path` |
| Reserve a self-deleting temp path | `sftp-helper tempfile` | `remote_tempfile` | `POST /tempfile` |
| Show resolved credentials (masked) | `sftp-helper show-credentials` | `credentials` | `GET /show-credentials` |

Every operation is also reachable through the click CLI (`sftp-helper-click …`,
same flags) and as MCP tools (`sftp-helper-mcp`).

## Natural-language phrasings that should fire

- **Upload**: "upload / push / send / put this file on the SFTP server", "deliver
  this to the partner inbox", "drop this on the remote box".
- **Download**: "download / fetch / pull / retrieve this from the server", "grab
  file X off the remote".
- **Delete**: "delete / remove / rm this remote file", "purge that stale upload".
- **Exists**: "does this file exist on the server", "is /path there remotely",
  "check the remote directory".
- **Mkdir**: "create the remote directory /a/b/c", "mkdir -p on the remote".
- **Paths**: "normalize this remote path", "strip the sftp:// / host prefix".
- **Temp / stage-and-share**: "reserve a temp path that deletes itself", "stage a
  file and give me a live URL for a consumer".
- **Credentials**: "load / show my SFTP credentials (masked)".
- **Surfaces**: "run the sftp API / MCP server", "install sftp-helper".

## Context cues it accepts

- an `sftp://host/path` address in the prompt;
- a host + login + remote path;
- an `sftp_config.json` / `sftp_config.yaml` file or `SFTP_*` env vars, plus a
  file to move.

## When NOT to use sftp-helper (SKIP)

- Plain **FTP / FTPS** (not SFTP-over-SSH), **SCP-only**, or the user explicitly
  wants `scp` / `rsync` shell tooling.
- **Cloud object storage** — S3 / GCS / Azure / MinIO / R2 / B2 → use
  `bucket-helper`.
- **Local-only** file copy / move with no remote server.
- **Downloading media from a URL / YouTube** → use `youtube-helper`.
- **Interactive SSH shell / remote command execution** (paramiko `exec_command`,
  Fabric) — that is not a file transfer.
- **Browsing a remote tree in a GUI** (FileZilla, Cyberduck, Transmit) —
  sftp-helper has no GUI.

## See also

- [`README.md`](README.md) — features, install, quick start.
- [`EXAMPLES.md`](EXAMPLES.md) — runnable recipes.
- [`skills/README.md`](skills/README.md) — installing this as an agent skill.
- [`LANDSCAPE.md`](LANDSCAPE.md) — how sftp-helper compares to paramiko, pysftp,
  asyncssh, Fabric, smart-open, PyFilesystem2, lftp, Rclone.
- [`GUI.md`](GUI.md) — a *design plan* for a possible future dashboard (no GUI
  ships today).
