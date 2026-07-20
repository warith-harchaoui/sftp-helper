# SFTP Helper

[🇫🇷](https://github.com/warith-harchaoui/sftp-helper/blob/main/LISEZMOI.md) · [🇬🇧](https://github.com/warith-harchaoui/sftp-helper/blob/main/README.md)

[![CI](https://github.com/warith-harchaoui/sftp-helper/actions/workflows/ci.yml/badge.svg)](https://github.com/warith-harchaoui/sftp-helper/actions/workflows/ci.yml) [![License: BSD-3-Clause](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](LICENSE) [![Python](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue.svg)](#)

`SFTP Helper` belongs to a collection of libraries called `AI Helpers` developped for building Artificial Intelligence

This toolbox requires:
  - a `config.json` for the sftp parameters (or YAML or environment variables or .env)
  - that you previously added you SSH key of your local machine in the SFTP server

[🌍 AI Helpers](https://harchaoui.org/warith/ai-helpers)

[![logo](https://raw.githubusercontent.com/warith-harchaoui/sftp-helper/main/assets/logo.png)](https://harchaoui.org/warith/ai-helpers)

SFTP Helper is a Python library that provides utility functions for working with SFTP servers via [paramiko](https://www.paramiko.org/). Host key verification is on by default — `~/.ssh/known_hosts` is loaded and unknown hosts are rejected.

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
- **Strict host-key verification, always on** — `paramiko.RejectPolicy()`, no
  opt-out; trust an extra key via the optional `sftp_known_hosts` credential.
- **Four surfaces, one behavior** — Python library, argparse CLI (`sftp-helper`),
  click CLI twin (`sftp-helper-click`), FastAPI HTTP surface, and MCP tools
  (`sftp-helper-mcp`). See the [multi-surface section](#multi-surface-exposure).
- **Agent skill** for Claude Code / Claude Desktop / OpenCode — see
  [`skills/README.md`](https://github.com/warith-harchaoui/sftp-helper/blob/main/skills/README.md)
  and the trigger catalogue in
  [`TRIGGERS.md`](https://github.com/warith-harchaoui/sftp-helper/blob/main/TRIGGERS.md).

## Documentation

[💻 Documentation](https://harchaoui.org/warith/ai-helpers/docs/sftp-helper-doc/)

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
pip install "sftp-helper[api,mcp]"   # MCP tools over FastAPI
```

### From source (no PyPI)

```bash
# Core SFTP utilities (library + argparse CLI)
pip install "git+https://github.com/warith-harchaoui/sftp-helper.git@v2.3.0"

# Optional surfaces
pip install "sftp-helper[cli] @ git+https://github.com/warith-harchaoui/sftp-helper.git@v2.3.0"
pip install "sftp-helper[api] @ git+https://github.com/warith-harchaoui/sftp-helper.git@v2.3.0"
pip install "sftp-helper[api,mcp] @ git+https://github.com/warith-harchaoui/sftp-helper.git@v2.3.0"
```

## Write your own configuration file

A ready-to-fill template is committed at [`sftp_config.json.example`](https://github.com/warith-harchaoui/sftp-helper/blob/main/sftp_config.json.example). A heavily-commented YAML variant is also provided at [`sftp_config.yaml.example`](https://github.com/warith-harchaoui/sftp-helper/blob/main/sftp_config.yaml.example) — YAML supports inline comments explaining every key and how to obtain its value. Copy either one and edit in place — real `*config.json` / `*config.yaml` files are gitignored so you cannot accidentally commit secrets:

```bash
cp sftp_config.json.example sftp_config.json
# then edit sftp_config.json with your credentials
```

You may also provide a YAML version (`sftp_config.yaml`), environment variables, or an `.env` file — `sftp-helper` falls back in that order via `os_helper.get_config`:

_JSON_
```json
{
    "sftp_host": "<sftp_host>",
    "sftp_login": "<sftp_login>",
    "sftp_passwd": "<sftp_passwd>",
    "sftp_https": "<sftp_https>",
    "sftp_destination_path": "<sftp_destination_path>",
}
```
or

_YAML_
```yaml
sftp_host: "<sftp_host>"
sftp_login: "<sftp_login>"
sftp_passwd: "<sftp_passwd>"
sftp_https: "<sftp_https>"
sftp_destination_path: "<sftp_destination_path>"
```
or

_ENVIRONMENT VARIABLES_
```bash
SFTP_HOST="<sftp_host>" \
SFTP_LOGIN="<sftp_login>" \
SFTP_PASSWD="<sftp_passwd>" \
SFTP_HTTPS="<sftp_https>" \
SFTP_DESTINATION_PATH="<sftp_destination_path>" \
python <your_python_script>
```
or

_.env_
```
SFTP_HOST                = <sftp_host>
SFTP_LOGIN               = <sftp_login>
SFTP_PASSWD              = <sftp_passwd>
SFTP_HTTPS               = <sftp_https>
SFTP_DESTINATION_PATH    = <sftp_destination_path>
```

In which you can find these information in your favorite FTP tool (mine is FileZilla):
  + `<sftp_host>` is the server path `sftp.` ...
  + `<sftp_login>` and `<sftp_passwd>` that you use in FileZilla
  + `<sftp_destination_path>` is the remote folder path
  + `<sftp_https>` corresponds to the web URL of `<sftp_destination_path>`
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

`sftp_helper` never disables host key verification. The default policy is
`paramiko.RejectPolicy()` and `~/.ssh/known_hosts` is loaded automatically. To
trust a server in a non-default location, point at an extra known_hosts file
via the optional `sftp_known_hosts` credential.

## Multi-surface exposure

`sftp-helper` is not just a library — the same functions are exposed
as a CLI, a FastAPI HTTP surface, and an MCP tool set:

```bash
# Python library (default)
import sftp_helper as sftph

# argparse-based CLI (installed automatically)
sftp-helper upload   --config sftp_config.json --input local.txt --remote /uploads/local.txt
sftp-helper download --config sftp_config.json --remote /uploads/local.txt --output out.txt
sftp-helper exists   --config sftp_config.json --remote /uploads/local.txt
sftp-helper mkdir    --config sftp_config.json --remote /uploads/a/b/c

# click-based CLI twin (needs the [cli] extra)
pip install 'sftp-helper[cli] @ git+https://github.com/warith-harchaoui/sftp-helper.git@v2.3.0'
sftp-helper-click upload --config sftp_config.json --input local.txt --remote /uploads/local.txt

# FastAPI HTTP surface (needs the [api] extra)
pip install 'sftp-helper[api] @ git+https://github.com/warith-harchaoui/sftp-helper.git@v2.3.0'
SFTP_HELPER_CONFIG=./sftp_config.json uvicorn sftp_helper.api:app --port 8000
# → OpenAPI docs at http://localhost:8000/docs

# MCP tools over FastAPI (needs the [api,mcp] extras)
pip install 'sftp-helper[api,mcp] @ git+https://github.com/warith-harchaoui/sftp-helper.git@v2.3.0'
sftp-helper-mcp                  # serves FastAPI + MCP on port 8000
```

Docker image (HTTP + MCP on port 8000):

```bash
docker build -t sftp-helper .
docker run --rm -p 8000:8000 \
  -v $PWD/sftp_config.json:/app/sftp_config.json:ro \
  -e SFTP_HELPER_CONFIG=/app/sftp_config.json \
  sftp-helper
```

### Use it as an agent skill

The same operations are packaged as a **Claude / OpenCode skill** so an agent can
run them for you without a terminal. See
[`skills/README.md`](https://github.com/warith-harchaoui/sftp-helper/blob/main/skills/README.md)
to install it, and
[`TRIGGERS.md`](https://github.com/warith-harchaoui/sftp-helper/blob/main/TRIGGERS.md)
for the exhaustive catalogue of phrasings, commands, and functions that invoke it
(and when to reach for `bucket-helper` / `youtube-helper` instead).

There is **no GUI** — a forward-looking dashboard *design plan* (pipeline
dashboard, storage-health panel, live transfer feed) lives in
[GUI.md](https://github.com/warith-harchaoui/sftp-helper/blob/main/GUI.md), but no
such code ships today.

The competitive landscape (paramiko, pysftp, asyncssh, Fabric,
smart-open, PyFilesystem2, lftp, Rclone, …) is analysed in
[LANDSCAPE.md](https://github.com/warith-harchaoui/sftp-helper/blob/main/LANDSCAPE.md).

## Author

 - [Warith HARCHAOUI](https://linkedin.com/in/warith-harchaoui)

## Acknowledgements

Special thanks to [Mohamed Chelali](https://mchelali.github.io) and [Bachir Zerroug](https://www.linkedin.com/in/bachirzerroug) for fruitful discussions.

## License

This project is licensed under the BSD-3-Clause License — see the [LICENSE](LICENSE) file for details.
