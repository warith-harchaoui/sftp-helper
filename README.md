# SFTP Helper

[🇫🇷](https://github.com/warith-harchaoui/sftp-helper/blob/main/LISEZMOI.md) · [🇬🇧](https://github.com/warith-harchaoui/sftp-helper/blob/main/README.md)

[![CI](https://github.com/warith-harchaoui/sftp-helper/actions/workflows/ci.yml/badge.svg)](https://github.com/warith-harchaoui/sftp-helper/actions/workflows/ci.yml) [![License: BSD-3-Clause](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](https://github.com/warith-harchaoui/sftp-helper/blob/main/LICENSE) [![Python](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue.svg)](#)

`SFTP Helper` belongs to a collection of libraries called `AI Helpers` developped for building Artificial Intelligence

This toolbox requires:
  - a `config.json` for the sftp parameters (or YAML or environment variables or .env)
  - that you previously added you SSH key of your local machine in the SFTP server

[🌍 AI Helpers](https://harchaoui.org/warith/ai-helpers)

[![logo](https://raw.githubusercontent.com/warith-harchaoui/sftp-helper/main/assets/logo.png)](https://harchaoui.org/warith/ai-helpers)

SFTP Helper is a Python library that provides utility functions for working with SFTP servers via the system OpenSSH `sftp` client. Host key verification is on by default — `~/.ssh/known_hosts` is consulted and unknown hosts are rejected.

> **Remote by design.** `sftp-helper` exists to move data to and from a *remote*
> server, so it is deliberately **not** local-first and ships **no GUI**. For
> cloud object storage (S3 / GCS / Azure / MinIO) use `bucket-helper`; for
> downloading media from a URL use `youtube-helper`.

## Features

- **Upload** a local file to the server — pass an explicit `sftp://host/path`, or
  omit it to get a deterministic **content-hashed** name under
  `sftp_destination_path` (identical bytes de-duplicate to the same path). Shows
  a byte-scaled progress bar on large transfers and preserves the source mtime.
- **Download** a remote file to disk (defaults to the remote basename), with a
  progress bar and remote-mtime preservation.
- **Delete** a remote file — **idempotent**: removing an absent file succeeds.
- **Existence checks** for a remote **file** (`remote_file_exists`) and a remote
  **directory** (`remote_dir_exist`).
- **Create remote directories** with `mkdir -p` semantics
  (`make_remote_directory`) — every missing intermediate level is created.
- **Path helpers**: `normalize_path` (single leading `/`, no trailing `/`) and
  `strip_sftp_path` (drop the `sftp://` scheme + host).
- **`remote_tempfile`** context manager — reserve a unique random remote path
  (optionally under a subdir, optionally with an extension) that is
  **auto-deleted on block exit**, even if an exception propagates; hands back
  both the `sftp://` address and its public HTTPS URL.
- **Credentials loader** (`credentials`) resolving JSON / YAML / directory /
  `SFTP_*` env vars / `.env`, with a masked `show-credentials` view.
- **Strict host-key verification, always on** — OpenSSH
  `StrictHostKeyChecking=yes`, no opt-out; trust an extra key via the optional
  `sftp_known_hosts` credential.
- **Three surfaces, one behavior** — Python library, argparse CLI (`sftp-helper`),
  click CLI twin (`sftp-helper-click`), and FastAPI HTTP surface. See the
  [multi-surface section](#multi-surface-exposure).
- Trigger catalogue in
  [`TRIGGERS.md`](https://github.com/warith-harchaoui/sftp-helper/blob/main/TRIGGERS.md).

## Documentation

[💻 Documentation](https://harchaoui.org/warith/ai-helpers/docs/sftp-helper-doc/)

[🗺️ Landscape](https://github.com/warith-harchaoui/sftp-helper/blob/main/LANDSCAPE.md)

[📋 Examples](https://github.com/warith-harchaoui/sftp-helper/blob/main/EXAMPLES.md)

## Installation

**Prerequisites** — **Python 3.10–3.13** and **git**, cross-platform:

- 🍎 **macOS** ([Homebrew](https://brew.sh)): `brew install python git`
- 🐧 **Ubuntu/Debian**: `sudo apt update && sudo apt install -y python3 python3-pip git`
- 🪟 **Windows** (PowerShell): `winget install Python.Python.3.12 Git.Git`

We recommend using Python environments. Check this link if you're unfamiliar with setting one up: [🥸 Tech tips](https://harchaoui.org/warith/4ml/#install).

### From PyPI (recommended)

```bash
# Core SFTP utilities (library + argparse CLI)
pip install sftp-helper

# Optional surfaces
pip install "sftp-helper[cli]"       # click-based CLI twin
pip install "sftp-helper[api]"       # FastAPI HTTP surface
```

### From source (no PyPI)

```bash
# Core SFTP utilities (library + argparse CLI)
pip install sftp-helper

# Optional surfaces
pip install "sftp-helper[cli]"
pip install "sftp-helper[api]"
```

## Write your own configuration file

A ready-to-fill template is committed at [`sftp_config.json.example`](https://github.com/warith-harchaoui/sftp-helper/blob/main/sftp_config.json.example). A heavily-commented YAML variant is also provided at [`sftp_config.yaml.example`](https://github.com/warith-harchaoui/sftp-helper/blob/main/sftp_config.yaml.example) — YAML supports inline comments explaining every key and how to obtain its value. Copy either one and edit in place — real `*config.json` / `*config.yaml` files are gitignored so you cannot accidentally commit secrets:

```bash
cp sftp_config.json.example sftp_config.json
# then edit sftp_config.json with your credentials
```

You may also provide a YAML version (`sftp_config.yaml`), environment variables, or an `.env` file — `sftp-helper` falls back in that order via `os_helper.get_config`:

Only **three** fields are required — `sftp_host`, `sftp_login`, `sftp_https`.
Authenticate with an SSH key (recommended: no password) by setting `sftp_key`
or loading your key into the SSH agent. `sftp_destination_path` is optional and
defaults to the server root `/`.

_JSON_
```json
{
    "sftp_host": "<sftp_host>",
    "sftp_login": "<sftp_login>",
    "sftp_https": "<sftp_https>",
    "sftp_key": "~/.ssh/id_ed25519"
}
```
or

_YAML_
```yaml
sftp_host: "<sftp_host>"
sftp_login: "<sftp_login>"
sftp_https: "<sftp_https>"
sftp_key: "~/.ssh/id_ed25519"    # optional; empty -> SSH agent + default keys
# sftp_passwd: "<sftp_passwd>"   # optional fallback (needs `sshpass`)
# sftp_destination_path: "/base" # optional; empty -> server root "/"
# sftp_port: "2022"              # optional; default 22
```
or

_ENVIRONMENT VARIABLES_
```bash
SFTP_HOST="<sftp_host>" \
SFTP_LOGIN="<sftp_login>" \
SFTP_HTTPS="<sftp_https>" \
SFTP_KEY="~/.ssh/id_ed25519" \
python <your_python_script>
```
or

_.env_
```
SFTP_HOST                = <sftp_host>
SFTP_LOGIN               = <sftp_login>
SFTP_HTTPS               = <sftp_https>
SFTP_KEY                 = ~/.ssh/id_ed25519
```

Where to find these (in your favorite FTP tool — mine is FileZilla):
  + `<sftp_host>` is the server host, e.g. `sftp.example.com`
  + `<sftp_login>` is your username
  + `<sftp_https>` corresponds to the web URL of `sftp_destination_path`
  + `sftp_key` is the SSH key you already use to `ssh`/`sftp` into the server
    (its public half must be installed in the server's `authorized_keys`); or
    leave it empty and rely on your SSH agent
  + <your_python_script> is your python script :)

## Usage

For the full catalog of recipes (uploads, downloads, existence checks, recursive directory creation, temporary remote files with auto-cleanup, strict host-key verification), see [📋 EXAMPLES.md](https://github.com/warith-harchaoui/sftp-helper/blob/main/EXAMPLES.md).

Here's an example of how to use SFTP helper (**won't work without a valid `path/to/sftp_config.json`**):

```python
import sftp_helper as sftph
import os_helper as osh

# Write a small text file
local_file = "example.txt"
with open(local_file, "wt") as f:
    f.write("A small example of text")

# Load creds from JSON / YAML file, or fall back to .env / environment vars.
cred = sftph.credentials("path/to/sftp_config.json")

remote_file = cred["sftp_destination_path"] + "/" + local_file
url = cred["sftp_https"] + "/" + local_file

# upload() raises on failure and returns the destination URL on success.
sftph.upload(local_file, cred, remote_file)
print(f"Uploaded {local_file} to {remote_file}")
# Uploaded example.txt to /remote/base/path/example.txt

assert osh.is_working_url(url), f"URL not reachable: {url}"
print(f"URL is live: {url}")
# URL is live: https://files.example.com/example.txt
```

## Temporary remote files

If you need a unique remote path that gets cleaned up automatically, use the
`remote_tempfile` context manager:

```python
import sftp_helper as sftph
import os_helper as osh

credentials = sftph.credentials("path/to/sftp_config.json")

with sftph.remote_tempfile(credentials, ext="txt") as (sftp_address, url):
    sftph.upload("local.txt", credentials, sftp_address)
    assert osh.is_working_url(url)
# On exit, the remote file is deleted.
```

## Host key verification

`sftp_helper` never disables host key verification. Every `sftp` invocation
passes `StrictHostKeyChecking=yes` and `~/.ssh/known_hosts` is consulted
automatically, so a host whose key you have not already accepted is rejected.
To trust a server whose key lives elsewhere, point at an extra known_hosts file
via the optional `sftp_known_hosts` credential.

## Multi-surface exposure

`sftp-helper` is not just a library — the same functions are exposed
as a CLI and a FastAPI HTTP surface:

```bash
# Python library (default)
import sftp_helper as sftph

# argparse-based CLI (installed automatically)
sftp-helper upload   --config sftp_config.json --input local.txt --remote /uploads/local.txt
sftp-helper download --config sftp_config.json --remote /uploads/local.txt --output out.txt
sftp-helper exists   --config sftp_config.json --remote /uploads/local.txt
sftp-helper mkdir    --config sftp_config.json --remote /uploads/a/b/c

# click-based CLI twin (needs the [cli] extra)
pip install "sftp-helper[cli]"
sftp-helper-click upload --config sftp_config.json --input local.txt --remote /uploads/local.txt

# FastAPI HTTP surface (needs the [api] extra)
pip install "sftp-helper[api]"
SFTP_HELPER_CONFIG=./sftp_config.json uvicorn sftp_helper.api:app --port 8000
# → OpenAPI docs at http://localhost:8000/docs
```

Docker image (HTTP on port 8000):

```bash
docker build -t sftp-helper .
docker run --rm -p 8000:8000 \
  -v $PWD/sftp_config.json:/app/sftp_config.json:ro \
  -e SFTP_HELPER_CONFIG=/app/sftp_config.json \
  sftp-helper
```

See [`TRIGGERS.md`](https://github.com/warith-harchaoui/sftp-helper/blob/main/TRIGGERS.md)
for the exhaustive catalogue of phrasings, commands, and functions that invoke it
(and when to reach for `bucket-helper` / `youtube-helper` instead).

There is **no GUI** — a forward-looking dashboard *design plan* (pipeline
dashboard, storage-health panel, live transfer feed) lives in
[GUI.md](https://github.com/warith-harchaoui/sftp-helper/blob/main/GUI.md), but no
such code ships today.

## Author

 - [Warith HARCHAOUI](https://linkedin.com/in/warith-harchaoui)

## Acknowledgements

Special thanks to [Mohamed Chelali](https://mchelali.github.io) and [Bachir Zerroug](https://www.linkedin.com/in/bachirzerroug) for fruitful discussions.

## License

This project is licensed under the BSD-3-Clause License — see the [LICENSE](https://github.com/warith-harchaoui/sftp-helper/blob/main/LICENSE) file for details.
