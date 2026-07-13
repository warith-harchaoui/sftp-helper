# LANDSCAPE

Related and competing Python libraries in the "talk to an SFTP server"
space, benchmarked against `sftp-helper`. Ratings are `⭐️` (1) to
`⭐️⭐️⭐️⭐️⭐️` (5), scored on `sftp-helper`'s intended job — everyday SFTP
handling for AI pipelines (upload, download, exists, mkdir -p, temp
remote files with auto-cleanup, strict host-key verification). A
library optimised for a very different job (e.g. large-scale
enterprise transfer orchestration, GUI clients) is not penalised — the
score just reflects fit to *this* niche.

## At a glance

| Library / project | Strict host-key verification (safe defaults) | AI-pipeline ergonomics (`dict` return, path-based API) | Temp remote file with auto-cleanup | Multi-surface (CLI + HTTP + MCP) | Config loader (JSON / YAML / env / .env) | Maintenance status | Light install |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **sftp-helper** *(this project)* | ⭐️⭐️⭐️⭐️⭐️ (RejectPolicy by default, no opt-out flag) | ⭐️⭐️⭐️⭐️⭐️ | ⭐️⭐️⭐️⭐️⭐️ (`remote_tempfile` context manager) | ⭐️⭐️⭐️⭐️⭐️ (argparse + click + FastAPI + MCP) | ⭐️⭐️⭐️⭐️⭐️ (delegates to `os-helper`) | ⭐️⭐️⭐️⭐️⭐️ | ⭐️⭐️⭐️⭐️⭐️ (paramiko only) |
| paramiko (raw) | ⭐️⭐️ (verifies only if you wire it) | ⭐️⭐️ (SSHClient / SFTPClient, verbose) | ⭐️ (roll your own) | ⭐️ | ⭐️ | ⭐️⭐️⭐️⭐️⭐️ | ⭐️⭐️⭐️⭐️⭐️ |
| pysftp | ⭐️⭐️ (deprecated, missing recent security fixes) | ⭐️⭐️⭐️⭐️ (convenient wrapper) | ⭐️ | ⭐️ | ⭐️ | ⭐️ (unmaintained since 2016) | ⭐️⭐️⭐️⭐️ |
| Fabric | ⭐️⭐️⭐️ (paramiko-based) | ⭐️⭐️⭐️ (task-oriented, not file-oriented) | ⭐️ | ⭐️⭐️ (Invoke CLI) | ⭐️⭐️ | ⭐️⭐️⭐️⭐️ | ⭐️⭐️⭐️⭐️ |
| asyncssh | ⭐️⭐️⭐️⭐️ (verifies by default) | ⭐️⭐️⭐️ (async, tensor of futures) | ⭐️⭐️ (async temp-dir helpers) | ⭐️ | ⭐️ | ⭐️⭐️⭐️⭐️⭐️ | ⭐️⭐️⭐️⭐️ |
| smart-open (SFTP backend) | ⭐️⭐️⭐️ | ⭐️⭐️⭐️⭐️ (file-like, path-based) | ⭐️ | ⭐️ (no CLI/HTTP by design) | ⭐️ | ⭐️⭐️⭐️⭐️ | ⭐️⭐️⭐️⭐️ |
| PyFilesystem2 (SFTPFS) | ⭐️⭐️⭐️ | ⭐️⭐️⭐️⭐️ (unified FS abstraction) | ⭐️⭐️ (`fs.tempfs`) | ⭐️⭐️ (fs.mirror CLI) | ⭐️ | ⭐️⭐️⭐️ | ⭐️⭐️⭐️⭐️ |
| lftp (CLI, not Python) | ⭐️⭐️⭐️ | ⭐️ (shell) | ⭐️⭐️ | ⭐️ | ⭐️ | ⭐️⭐️⭐️⭐️ | ⭐️⭐️⭐️⭐️⭐️ |
| Rclone (SFTP backend, CLI, not Python) | ⭐️⭐️⭐️⭐️ | ⭐️⭐️ (call-out from Python) | ⭐️⭐️ (`--delete` on sync) | ⭐️⭐️⭐️ (has REST via `rclone rcd`) | ⭐️⭐️⭐️⭐️ (own config format) | ⭐️⭐️⭐️⭐️⭐️ | ⭐️⭐️⭐️ (Go binary) |

## Positioning

`sftp-helper` deliberately sits at the intersection of **`pysftp`-level
ergonomics** (one-line upload / download / exists / mkdir) and **modern
supply-chain hygiene** (strict host-key verification with no opt-out
flag, `os-helper`-based credential discovery, multi-surface exposure).
It intentionally does *not* try to compete with `Fabric` on task
orchestration or with `Rclone` on multi-backend replication, and it
keeps `paramiko` as the only mandatory dependency — you only pay for
the FastAPI / MCP / click surfaces if you install their extras. That
trade-off is the main differentiator against `pysftp` (unmaintained,
no security posture) and against raw `paramiko` (correct, but requires
40 lines of boilerplate before you can `.put()` a file).

## When to pick what

- **`sftp-helper`** — SFTP prep for AI pipelines: batch uploads,
  temporary remote scratch files, strict host-key hygiene, one-shot
  CLI + HTTP + MCP surfaces.
- **`paramiko`** — you need low-level SSH primitives (port forwarding,
  interactive sessions, custom key algorithms) and are prepared to
  wire the host-key policy yourself.
- **`asyncssh`** — you already run an `asyncio` event loop and want
  zero-copy between SFTP I/O and the rest of your async pipeline.
- **`Fabric`** — task orchestration over SSH (deployments, remote
  scripts), not just file transfer.
- **`smart-open` / `PyFilesystem2`** — you want a single file-like
  API across S3 / GCS / SFTP / local without caring about the
  underlying transport.
- **`Rclone` / `lftp`** — you need production-grade multi-backend
  sync / replication, and calling out to a binary is acceptable.
