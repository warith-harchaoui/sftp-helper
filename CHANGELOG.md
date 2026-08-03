# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.0.0] - 2026-08-03

Swaps the SSH backend from the in-process **paramiko** library to the system
**OpenSSH `sftp` client**, and relaxes the credentials contract around
key-based auth. This is a breaking release.

### Changed

- **Backend: system OpenSSH `sftp` instead of paramiko.** Every operation now
  runs as a short-lived `sftp -b` batch subprocess, with success decided by the
  process **exit code** (so a benign stderr notice — e.g. OpenSSH's
  post-quantum key-exchange warning — on a successful transfer is never
  mistaken for a failure). A 30 s `ConnectTimeout` bounds a dead host.
  Authentication matches the operator's own `ssh`/`sftp`: the SSH agent,
  `~/.ssh` default identities, hardware tokens, and `~/.ssh/config` all work.
  Requires the `sftp` binary on `PATH` (preinstalled on macOS, most Linux, and
  Windows 10 1809+ / Server 2019+); a clear error is raised if it is missing.
- **Credentials contract relaxed.** Only `sftp_host`, `sftp_login` and
  `sftp_https` are required. `sftp_passwd` is now optional (empty ⇒ key / agent
  auth) and `sftp_destination_path` is optional, defaulting to the server root
  `/`.
- **Strict host-key verification** is now enforced via OpenSSH
  `StrictHostKeyChecking=yes` (was `paramiko.RejectPolicy()`); still no opt-out.
  `sftp_known_hosts` is added to the default stores via `UserKnownHostsFile`.

### Added

- **`sftp_key` credential** — path to your SSH key for password-less auth. May
  point at the private key *or* its `.pub` companion (OpenSSH then signs via the
  agent / a hardware token). Empty ⇒ SSH agent + default identities.
- **Live progress bar on upload *and* download**, matching
  `os_helper.download_file`: on an interactive terminal the transfer runs
  through `scp` under a pseudo-terminal and its meter drives
  `os_helper.progress_bar` (byte-scaled, ETA). Auto-suppressed off a TTY (CI /
  pipes), on Windows (no pty), or under password auth — those fall back to the
  plain `sftp -b` transfer.

### Removed

- **`paramiko` dependency dropped** — the package now has no Python SSH
  dependency beyond `os-helper`; the SSH backend is the system OpenSSH client.
- **Live `paramiko.SFTPClient`** is gone. `get_client_sftp` is kept as a thin,
  deprecated compatibility shim that validates connectivity and yields the
  credentials dict (there is no longer a persistent client object to expose).

### Notes

- Password auth (`sftp_passwd`) now requires the `sshpass` helper, since OpenSSH
  never reads a password from the command line; key-based auth is recommended.
  The progress bar is unavailable under password auth (it falls back to the
  plain, non-streamed transfer).

## [2.5.0] - 2026-08-02

Adopts the hardened AI Helpers foundation and tightens the CI gate.

### Changed

- **Requires os-helper 2.x** (`os-helper>=2.0.0,<3`, was `>=1.5.3`). The shared
  transfer progress bar (`osh.progress_bar`, used by upload / download) now
  comes from the stable 2.x foundation.
- **CI trimmed to a super-light gate:** the test matrix drops to a single Python
  (the full multi-version sweep runs locally before push), and the vestigial
  `ffmpeg` system-deps step (a template leftover; sftp-helper never touches
  ffmpeg) is removed. Lint stays fully blocking (`ruff check` + `ruff format
  --check`).

### Fixed

- README / LISEZMOI / EXAMPLES install commands no longer self-pin to a git tag
  (`@v2.4.0`); they use `pip install sftp-helper` (and `"sftp-helper[cli]"` /
  `"sftp-helper[api]"`), which always resolves to the latest published release.

### Added

- `tests/test_readme_install_pin.py` guards against the stale git self-pin ever
  returning to any Markdown file.

## [2.4.0] - 2026-08-01

### Removed

- **MCP surface dropped.** `fastapi-mcp`'s latest release (0.4.0) is
  incompatible with the latest `mcp` SDK (`Server.__init__()` signature
  mismatch), breaking CI with no available version pairing to pin around.
  Removed `sftp_helper/mcp.py`, the `sftp-helper-mcp` entry point, the
  `mcp` extra, and every doc mention. The library, both CLIs, and the
  FastAPI HTTP surface are unaffected — sftp-helper now ships **three**
  surfaces instead of four.
- **Agent skill dropped from the public repo.** Without an MCP surface,
  the Claude/OpenCode skill (`skills/`) no longer earns its keep as public
  distribution — moved to the gitignored `.private/skills/` (kept locally
  as reference, never published). `TRIGGERS.md` stays public; its
  skill-specific framing and dead `skills/` links are removed.

## [2.3.0] - 2026-07-20

### Added

- **Agent skill (Claude + OpenCode).** New `skills/sftp-helper/` package with a
  trigger-rich `SKILL.md` (third-person description, exhaustive enforced TRIGGER
  clause + SKIP clause) and progressive-disclosure references
  (`cli-reference.md`, `surfaces.md`, `config.md`, `triggers.md`), plus
  `skills/README.md` with install instructions. Symlinkable into
  `~/.claude/skills/` and `~/.opencode/skills/`.
- **`TRIGGERS.md`** at the repo root — the user-facing, exhaustive catalogue of
  phrasings, commands, functions, and context cues that should invoke
  sftp-helper (and when to reach for `bucket-helper` / `youtube-helper`
  instead). Referenced from README and LISEZMOI.
- **Features section** in README and LISEZMOI (French mirror) enumerating every
  operation, the four surfaces, and the strict host-key policy.

### Changed

- The FastAPI OpenAPI `version` is now resolved dynamically from installed
  package metadata instead of a hard-coded literal, so it can never drift from
  `pyproject.toml` on a release.

### Fixed

- `ruff format` compliance in `sftp_helper/main.py` (a `sftp.put(...)` call that
  the formatter collapses onto one line), so the CI lint job stays green.

### Notes

- No public API changes — `sftp_helper.__all__` is unchanged and
  backward-compatible. No GUI and no local-first claim are added (by design:
  sftp-helper transfers data to/from a remote server).

## [2.2.5] - 2026-07-20

### Changed

- **Upload and download now show a progress bar.** `upload` (`put`) and
  `download` (`get`) thread paramiko's transfer callback into the shared
  `os_helper.progress_bar` (byte scaled, ETA, auto-quiet on a non-TTY), so moving
  a large file gives live feedback. A small adapter converts paramiko's
  cumulative `(transferred, total)` callback to the bar's delta updates; download
  stats the remote file first to seed the bar total. Requires `os-helper>=1.5.3`.

## [2.2.4] - 2026-07-15

### Documentation

- Harmonize README/LISEZMOI to the AI Helpers common structure (single
  H1, PyPI + source install paths, refreshed pins to v2.2.4); no code
  changes.

## [2.2.3] - 2026-07-14

### Maintenance

- Apply the project coding standards across the package and `tests/`:
  Numpy-style docstrings on every function/class (including private and
  nested helpers), full type annotations with `from __future__ import
  annotations`, and comment density raised above the floor in every
  module. No public API or behavior changes.
- Route library logging through the os-helper logging surface
  (`osh.info/warning/error`) and adopt os-helper path/file utilities
  more widely; pin `os-helper>=1.5.0`.
- Refresh the project logo asset.


## [2.2.2] - 2026-07-08

### Documentation

- Cross-platform Install prerequisites (macOS / Ubuntu / Windows).

## [2.2.1] - 2026-07-07

### Documentation

- Establish suite-wide Python coding-style mandate in `CONTRIBUTING.md`:
  numpy-style docstrings on every function and class, module-level
  docstring header (with usage example + author), full type annotations,
  generous explanatory comments.
- `EXAMPLES.md` cookbook present at the repo root and linked from
  README + LISEZMOI.
- `print(...)` in docs (EXAMPLES.md / README / LISEZMOI) is followed by
  a `#`-comment showing the expected output (doctest / REPL style);
  library `.py` code uses `osh.info` / `osh.warning` / `osh.error`
  instead of bare `print`.
- Every `brew install <pkg>` mention is paired with a brew.sh hint when
  not already obvious from context.
- `.gitignore` updated to drop accidental `*config.json` commits while
  keeping `*config.json.example` templates tracked.
- Ship `sftp_config.json.example` template at the repo root for first-time setup.

### Changed

- Drop `requirements.txt` and `environment.yml` (redundant with
  `pyproject.toml`).
- Add GitHub Actions CI.

## [2.1.0] - 2026-06-28

### Changed

- Bump `os-helper` pin to v1.3.0.
- Remove xfail markers (paramiko issues no longer reproducible).
- Codebase / docstring cleanup.

## [2.0.1] - 2026-06-23

### Changed

- Bump `os-helper` pin to v1.1.0.

## [2.0.0] - 2026-05-23

### Changed (breaking)

- Replace `pysftp` with `paramiko` to enable strict host-key
  verification (no more silent host-key trust).

### Added

- `remote_tempfile` context manager for stage-and-share flows.

## [1.0.0] - 2024-11-05

First tagged release (pysftp-based).
