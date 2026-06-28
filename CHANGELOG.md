# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
