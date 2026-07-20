# sftp-helper skill — exhaustive trigger catalogue

Auditable superset of the `description:` TRIGGER clause in `SKILL.md` (the
description is what a host model sees before loading; this file is the
human-reviewable full list). Keep the two in sync, and mirror the repo-root
`TRIGGERS.md`.

## Fire (positive triggers)

**Upload (local → remote)**
- "upload this file to the SFTP server", "push / send / put this on sftp"
- "deliver this to the partner's SFTP inbox", "drop this on the remote server"
- "upload it and give me the auto-hashed name / the URL"

**Download (remote → local)**
- "download / fetch / pull / retrieve this file from the SFTP server"
- "grab file X off the remote box", "get the remote copy to my disk"

**Delete (remote)**
- "delete / remove / rm this remote file", "clean up that file on the server"
- "purge the stale upload" (idempotent — absent file is fine)

**Existence checks**
- "does this file exist on the server", "is /path there remotely"
- "check whether the remote directory /a/b exists"

**Directory creation**
- "create / make the remote directory /a/b/c", "mkdir -p on the remote"
- "ensure the remote folder exists before I upload"

**Path helpers**
- "normalize this remote path" (single leading `/`, no trailing `/`)
- "strip the `sftp://` scheme / the host from this address"

**Temp / stage-and-share**
- "reserve a unique temp path on the server that deletes itself"
- "stage a file on sftp and hand me a live URL for a downstream consumer"
- "give me a scratch remote path scoped under a subdir"

**Credentials**
- "load / resolve my SFTP credentials", "show my sftp config (masked)"
- "where are my SFTP creds coming from — file, env, or .env?"

**Explicit command / function mentions**
- `sftp-helper`, `sftp-helper-click`, `sftp-helper-mcp`
- subcommands `upload download delete exists dir-exists mkdir normalize-path
  strip-path tempfile show-credentials`
- functions `credentials get_client_sftp upload download delete
  remote_file_exists remote_dir_exist make_remote_directory normalize_path
  strip_sftp_path remote_tempfile`

**Surfaces**
- "run the sftp API / sftp-helper server", "expose these as HTTP / MCP tools"
- "how do I install / run sftp-helper"

**Context cues** (with a transfer intent)
- an `sftp://host/path` address in the prompt
- a host + login + remote path, or an `sftp_config.json` / `sftp_config.yaml`
  / `SFTP_*` env vars, plus a file to move

## Do NOT fire (SKIP)

- **Plain FTP / FTPS** (not SFTP-over-SSH), **SCP-only**, or the user explicitly
  wants `scp` / `rsync` shell tooling → not this skill.
- **Cloud object storage** — S3 / GCS / Azure Blob / MinIO → use `bucket-helper`.
- **Local-only** file copy / move with no remote server → plain `os-helper` /
  shell.
- **Downloading media from a URL / YouTube** → `youtube-helper`.
- **Interactive SSH shell / running remote commands** (paramiko `exec_command`,
  Fabric task runner) → not a file transfer, not this skill.
- **Browsing a full remote directory tree in a GUI** (FileZilla, Cyberduck,
  Transmit) → sftp-helper has no GUI and is not a file explorer.

## Enforcement checklist

A trigger is "enforced" when (1) it is represented in `SKILL.md`'s `description`
TRIGGER clause so the host sees it pre-load; (2) the SKIP clause is present so the
skill does not over-fire; (3) this catalogue lists the positive and negative
buckets so a human can audit coverage against the description.
