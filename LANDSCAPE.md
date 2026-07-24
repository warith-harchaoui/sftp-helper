# Landscape

[🇫🇷 PAYSAGE.md](https://github.com/warith-harchaoui/sftp-helper/blob/main/PAYSAGE.md) · 🇬🇧 English

Related and competing Python libraries in the "talk to an SFTP server"
space, benchmarked against `sftp-helper`. Ratings are ⭐ (1) to
⭐⭐⭐⭐⭐ (5), scored on `sftp-helper`'s intended job — everyday SFTP
handling for AI pipelines (upload, download, exists, mkdir -p, temp
remote files with auto-cleanup, strict host-key verification). A
library optimised for a very different job (e.g. large-scale
enterprise transfer orchestration, GUI clients) is not penalised — the
score just reflects fit to *this* niche. `sftp-helper` is deliberately
a **remote** tool: it talks to a live SSH/SFTP server, so there is no
local-first mode to score here.

## At a glance

<!-- TABLE:START -->
| SFTP Transfer | Strict host-key verification | AI-pipeline ergonomics | Temp remote file with auto-cleanup | Multi-surface | Config loader | Maintenance status | Light install |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **sftp-helper** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| paramiko | ⭐⭐ | ⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| pysftp | ⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ |
| Fabric | ⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| asyncssh | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| smart-open | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| PyFilesystem2 | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| lftp | ⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Rclone | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
<!-- TABLE:END -->

## Positioning map

<!-- FIGURE:START -->
2D representation of the table above.

![Positioning map](https://raw.githubusercontent.com/warith-harchaoui/sftp-helper/main/assets/landscape.png)

The map is a 2-D summary of the seven criteria, so read it as a shape, not a scoreboard. `sftp-helper` is at the top-right corner. The axes read **Horizontal — Streamlined ↔ Secure** and **Vertical — Lightweight ↔ Versatile**.
<!-- FIGURE:END -->

## Positioning

`sftp-helper` deliberately sits at the intersection of **`pysftp`-level
ergonomics** (one-line upload / download / exists / mkdir) and **modern
supply-chain hygiene** (strict host-key verification with no opt-out
flag, `os-helper`-based credential discovery, multi-surface exposure).
It intentionally does *not* try to compete with `Fabric` on task
orchestration or with `Rclone` on multi-backend replication, and it
keeps `paramiko` as the only mandatory dependency — you only pay for
the FastAPI / MCP / click surfaces if you install their extras. That
trade-off is the main differentiator against `pysftp` (unmaintained
since 2016, missing recent security fixes) and against raw `paramiko`
(correct, but requires 40 lines of boilerplate before you can `.put()`
a file).

A few notes behind the ratings. On **host-key verification**,
`sftp-helper` scores top because it defaults to `RejectPolicy` with no
opt-out flag; `paramiko` and `pysftp` only verify if you wire it
yourself, while `asyncssh` and `Rclone` verify by default. On
**temp remote file**, `sftp-helper`'s `remote_tempfile` context manager
is the only first-class, auto-cleaning implementation in the field. Its
**multi-surface** score reflects argparse + click + FastAPI + MCP behind
the same function signatures, and its **config loader** delegates to
`os-helper` (JSON / YAML / env / .env). `Rclone` earns a strong config
score for its own config format and a REST surface via `rclone rcd`,
but as a Go binary it is heavier to install and awkward to drive from
Python.

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
