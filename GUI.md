# GUI — SFTP Helper

> A design plan, not a CLI mirror. FileZilla, Cyberduck and Transmit
> already ship pretty file explorers. If `sftp-helper` grows a GUI it
> must be something those tools cannot give: a **remote-file dashboard
> for AI pipelines** where the file system is a live artifact of running
> jobs, not a hierarchical tree to click through.

## North star

> **A single-pane view of every "AI asset" that transits your SFTP
> bucket — pinned by pipeline run, grouped by intent, and auditable
> back to the code that produced it.**

Data-engineering / AI teams do not open FileZilla to admire folders.
They open it to answer: *"is the file the training job produced still
there? did the last inference run actually upload its output? is that
staging folder still holding ten broken artefacts from last week?"*
The GUI's job is to answer those questions instantly.

## Three surfaces, one product

### 1. Pipeline Dashboard *(primary surface)*

- Left column: a **timeline of pipeline runs** (one row per calling
  script / cronjob / notebook, dedup'd by a per-run tag written into
  the SFTP metadata by `remote_tempfile`).
- Center column: the artifacts each run produced — file names, sizes,
  RMS-like activity heatmap (writes / reads over time), and the HTTPS
  URL if `sftp_https` is set.
- Right column: **diff between two runs**. Green = new file, red =
  gone since previous run, yellow = same path but different hash.
- One toggle per row: **"Detach from cleanup"** — flips the file from
  temporary (auto-deleted at run end) to persistent. Undo is a
  first-class button, not a dialog box.
- Every row has a **"Copy MCP invocation"** button — pastes the exact
  `sftp-helper-mcp` tool call that would recreate the operation.

### 2. Storage Health Panel

Not a file explorer — a set of gauges:

- **Bytes in use per subdir**, sorted descending, with a "delete
  everything older than N days" scoped action.
- **Broken uploads**: files whose remote size does not match a
  known-good hash (surfaced via a periodic `remote_file_exists +
  compare-hash` scan against a local manifest).
- **Orphan `remote_tempfile` leftovers**: files whose reserved
  address matches the `token_hex(16)` shape but that no live run is
  tracking. One-click drain.
- **Host-key drift alarm**: if the SFTP host presents an unexpected
  key on the next check, the whole panel goes red and blocks
  further writes until acked.

### 3. Live Transfer Feed

A ticker of every `upload` / `download` / `delete` performed by any
process using the same credential set. Bindings:

- Space bar: pause / resume the feed.
- Click any row → jumps to the exact log line in the pipeline that
  produced it (correlation ID from `os_helper` logging).
- Difference channel at the bottom: *"pending transfers"* — jobs that
  said they would upload but haven't started yet (queued in the
  `remote_tempfile` context but no `put` yet).

## Design principles

- **Nothing invisible.** Every file shown carries its pipeline
  provenance, its hash, its size and its `sftp_https` URL. No naked
  "unknown.bin" without a story.
- **Time is a first-class citizen.** Everything is timelined. There is
  no "current view of the filesystem" without a timestamp.
- **Files, not folders.** The tree view is optional — the primary
  entity is the pipeline artifact, not the directory it lives in.
- **Least-privilege UI.** The GUI never accepts new credentials in-app.
  It reads whatever `sftp_helper.credentials()` resolves at boot.
- **Keyboard first, mouse second.** Every panel action has a shortcut.
  `d` deletes a row, `p` toggles pinning, `/` focuses the run filter.
- **Colorblind-safe by construction.** All state uses shape + color +
  text, never color alone (see companion `front-colors` audit skill).

## What we deliberately don't do

- **No dual-pane file explorer.** FileZilla and Cyberduck already
  ship them. Scope discipline.
- **No credential entry UI.** Credentials come from env / config, not
  from a form. That eliminates a whole class of phishing failure modes.
- **No cloud lock-in.** Everything runs on the same local FastAPI
  server the container already ships. GUI is a thin JS client.
- **No FTP.** Only SFTP over SSH. The library is called `sftp-helper`.

## Stack

- Front end: TypeScript + Svelte 5 + a small D3-based
  small-multiples chart for the write-heatmaps. No React — matches
  the `front-ui` companion skill's stack.
- Back end: the FastAPI app already exists (`sftp_helper.api`) and
  covers 100 % of the operations. GUI is a client only.
- Manifest format: JSON Lines — one artifact record per line, human
  diff-friendly for CI checks.

## Milestones

| Milestone | What ships | Why first |
| --- | --- | --- |
| M0 | Pipeline Dashboard with the timeline + artifact list. Read-only. | Prove the "pipeline as first-class entity" metaphor before mutations. |
| M1 | Full CRUD via the FastAPI surface: upload / download / delete / mkdir buttons. Live transfer feed. | Feature parity with the CLI. |
| M2 | Storage Health Panel — sub-dir gauges, orphan `remote_tempfile` cleanup. | Where the GUI beats the CLI in productivity. |
| M3 | Run diff view + persistent pin/detach with audit log. | Reproducibility story for pipelines shared across a team. |
| M4 | Host-key drift alarm hooked into `~/.ssh/known_hosts` + on-server key fingerprint check on each poll. | The "we can only do this in a GUI" moment — security surface visible to non-terminal users. |

## Non-goals (recorded so we do not drift)

- Not a filemanager replacement.
- Not a hosted SaaS.
- Not a substitute for the CLI in CI (the dashboard's actions all
  emit the equivalent CLI / MCP invocation for replay).

## Success metric

> A user managing a training-data pipeline with 5000 clips across
> a dozen batches can, in one afternoon, purge stale artifacts, pin
> the golden batch, and hand off a `manifest.jsonl` to the next
> engineer — without ever opening a terminal.

If we ship that, we win.
