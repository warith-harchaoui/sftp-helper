# Landscape

[🇫🇷 PAYSAGE.md](https://github.com/warith-harchaoui/sftp-helper/blob/main/PAYSAGE.md) · 🇬🇧 English

Related and competing Python libraries in the "talk to an SFTP server"
space, benchmarked against `sftp-helper`. Ratings are ⭐ (1) to
⭐⭐⭐⭐⭐ (5), scored on `sftp-helper`'s intended job: everyday SFTP
handling for AI pipelines (upload, download, exists, mkdir -p, temp
remote files with auto-cleanup, strict host-key verification). A
library optimised for a very different job (e.g. large-scale
enterprise transfer orchestration, GUI clients) is not penalised; the
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
| Fabric | ⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| asyncssh | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| smart-open | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| PyFilesystem2 | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| lftp | ⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Rclone | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
<!-- TABLE:END -->

## Positioning map

<!-- FIGURE:START -->
2D representation of the table above.

![Positioning map](https://raw.githubusercontent.com/warith-harchaoui/sftp-helper/main/assets/landscape.png)

The map is a 2-D summary of the seven criteria, so read it as a shape, not a scoreboard. `sftp-helper` is at the top-right corner. The axes read **Horizontal — Ingenuity ↔ Robustness** and **Vertical — Simplicity ↔ Versatility**.
<!-- FIGURE:END -->

## Positioning

`sftp-helper` deliberately sits at the intersection of **`pysftp`-level
ergonomics** (one-line upload / download / exists / mkdir) and **modern
supply-chain hygiene** (strict host-key verification with no opt-out
flag, `os-helper`-based credential discovery, multi-surface exposure).
It intentionally does *not* try to compete with `Fabric` on task
orchestration or with `Rclone` on multi-backend replication, and it
drives the **system OpenSSH `sftp` client**, so it has no Python SSH
dependency at all (only `os-helper`), and authenticates exactly like
your own `ssh`/`sftp` (agent, `~/.ssh/config`, hardware tokens). You
only pay for the FastAPI / MCP surfaces if you install their extras.
That trade-off is the main differentiator against `pysftp` (whose last
release, 0.2.9, is dated 6 July 2016) and against raw `paramiko`
(correct, but you assemble the transport, choose a missing-host-key
policy and open an `SFTPClient` yourself before the first `.put()`).

A few notes behind the ratings. On **host-key verification**,
`sftp-helper` scores top because every invocation passes
`StrictHostKeyChecking=yes` and there is no flag that turns it off.
`asyncssh` also validates by default: its `known_hosts` argument falls
back to `~/.ssh/known_hosts`, and only an explicit `known_hosts=None`
disables the check. `paramiko` rejects an unknown host by default
(`RejectPolicy`) but a fresh `SSHClient` holds **zero** host keys until
you call `load_system_host_keys()`, so the store is yours to wire.
`Rclone`'s SFTP backend defaults the other way: it performs no host-key
validation until `known_hosts_file` is set (or a key is pinned with
`--sftp-pin-host-key`), and it warns "No host key validation is being
performed" every time it starts in that mode. Its four stars are for
having the machinery and documenting it, not for arriving switched on.

On **temp remote file**, `sftp-helper`'s `remote_tempfile` context manager
is the only first-class, auto-cleaning implementation among the Python
libraries here; only `Rclone`'s binary comes close. Its **multi-surface**
score reflects one click CLI, a FastAPI HTTP surface
and the MCP tools published from that same app, all behind the same
function signatures; its **config loader** delegates to
`os-helper` (JSON / YAML / env / .env). `Rclone` earns a strong config
score for its own config format and a REST surface via `rclone rcd`,
but as a Go binary it is heavier to install and awkward to drive from
Python.

## When to pick what

- **`sftp-helper`**: SFTP prep for AI pipelines: batch uploads,
  temporary remote scratch files, strict host-key hygiene, one-shot
  CLI + HTTP surfaces.
- **`paramiko`**: you need low-level SSH primitives (port forwarding,
  interactive sessions, custom key algorithms) and are prepared to
  wire the host-key policy yourself.
- **`asyncssh`**: you already run an `asyncio` event loop and want
  zero-copy between SFTP I/O and the rest of your async pipeline.
- **`Fabric`**: task orchestration over SSH (deployments, remote
  scripts), not just file transfer.
- **`smart-open` / `PyFilesystem2`**: you want a single file-like
  API across S3 / GCS / SFTP / local without caring about the
  underlying transport.
- **`Rclone` / `lftp`**: you need production-grade multi-backend
  sync / replication, and calling out to a binary is acceptable.

## Sources and as-of date

**As of 27 October 2026.** Nothing here was benchmarked: this is a
fit-to-one-job comparison, and the stars are judgements. What *can* rot
is the factual half — release dates and documented defaults for other
people's software — so that is what this section pins down.

Release data, read from each project's PyPI JSON API
(`https://pypi.org/pypi/<name>/json`) on the date above:

| Project | Latest release | Published |
| --- | --- | --- |
| paramiko | 5.1.0 | 2026-10-18 |
| smart-open | 8.0.4 | 2026-10-17 |
| asyncssh | 2.24.1 | 2026-10-04 |
| Fabric | 3.2.3 | 2026-04-06 |
| PyFilesystem2 (`fs`) | 2.4.16 | 2022-05-02 |
| pysftp | 0.2.9 | 2016-07-06 |

`Rclone` is not a Python package: v1.75.2, published 2026-10-09, from the
GitHub releases API. `lftp` ships through distribution packages only and
no release date was checked for it, which makes its **maintenance
status** cell the weakest-sourced one in the table — read that one as an
impression rather than a measurement.

Documented behaviour, from each project's own reference:

- [asyncssh `connect()`](https://asyncssh.readthedocs.io/en/latest/api.html) —
  "If this is not specified, the keys will be looked up in the file
  .ssh/known_hosts. If this is explicitly set to `None`, server host key
  validation will be disabled."
- [paramiko `SSHClient`](https://docs.paramiko.org/en/latest/api/client.html) —
  `RejectPolicy` is the default missing-host-key policy, and a host key
  counts as known only once `load_system_host_keys()` or
  `load_host_keys()` has loaded it. The "zero keys at construction"
  detail was checked against the installed paramiko 3.5.1, not just read.
- [rclone's SFTP backend](https://rclone.org/sftp/) — "Optional path to
  known_hosts file. Set this value to enable server host key validation",
  and the warning "No host key validation is being performed" it emits
  each time the backend starts without one.

`sftp-helper`'s own claims are checkable in this repository rather than
cited: `_ssh_options` in `sftp_helper/main.py` for the
`StrictHostKeyChecking=yes` that has no opt-out, `sftp_helper/cli.py` and
`sftp_helper/api.py` for the surfaces, `CHANGELOG.md` for the history.

The stars themselves are generated from `assets/landscape.csv`, which is
the source of truth for both the table above and the positioning figure.
A library built for a different job (enterprise transfer orchestration, a
GUI client, multi-backend replication) scores low here without that being
a defect — see the preamble.

## Ideas worth stealing

Researched rather than guessed: what each neighbour does better, and what this library would have to change to match it. Nothing here is a commitment — it is the reading list the next version starts from.

- **`pysftp` is dead, and the table should say so** — Last released in 2016, unmaintained, and it still cannot use Ed25519 or ECDSA keys even though the paramiko it wraps can. It is the first result people find and the worst choice they can make; naming that plainly is more useful than a star rating.

- **`asyncssh` — fast, and licence-blocked for many callers** — It is the strongest async option, but it ships under the EPL, which does not combine with GPL or BSD distribution. For a BSD-3 suite that is a hard stop, and it belongs in the comparison as a licence fact rather than a performance one.

- **`sshfs` — fsspec over asyncssh, and notably quicker than paramiko** — Where the licence allows it, the throughput difference is large enough to matter for bulk transfer. Worth measuring here before assuming paramiko's speed is the ceiling.

- **`Rclone` — resume, verify, and limit the bandwidth** — Checksummed verification after transfer, resumable partial uploads and a bandwidth cap are the three things an operator asks for the first time a transfer fails at 90% on a shared link.
