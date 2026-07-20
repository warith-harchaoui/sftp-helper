# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
