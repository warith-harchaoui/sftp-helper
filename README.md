# SFTP Helper

[🇫🇷](https://github.com/warith-harchaoui/sftp-helper/blob/main/LISEZMOI.md) · [🇬🇧](https://github.com/warith-harchaoui/sftp-helper/blob/main/README.md)

[![CI](https://github.com/warith-harchaoui/sftp-helper/actions/workflows/ci.yml/badge.svg)](https://github.com/warith-harchaoui/sftp-helper/actions/workflows/ci.yml) [![PyPI](https://img.shields.io/pypi/v/sftp-helper.svg)](https://pypi.org/project/sftp-helper/) [![License: BSD-3-Clause](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](https://github.com/warith-harchaoui/sftp-helper/blob/main/LICENSE) [![Python](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue.svg)](#)

`SFTP Helper` belongs to a collection of libraries called `AI Helpers`, built for developing Artificial Intelligence applications.

SFTP, the SSH File Transfer Protocol, moves files to and from a remote server over the same encrypted channel used for a remote terminal login (SSH). The server never asks for a password if you would rather it did not: a key pair proves who you are, the same way a physical key proves you are allowed into a building; the server only needs to know your key's public half. An AI pipeline that produces files (a rendered video, a trained model, a batch of transcripts) usually needs to hand them off to somewhere else without a human clicking through a file manager; `sftp-helper` is that hand-off, done from Python, with the file-integrity checks (resumable transfers, content hashing, atomic writes) that a script running unattended needs and a human with a mouse does not.

This toolbox requires:
  - a `settings.yaml` for the sftp parameters (or JSON or environment variables or .env)
  - that you previously added you SSH key of your local machine in the SFTP server

[🌍 AI Helpers](https://harchaoui.org/warith/ai-helpers)

[![logo](https://raw.githubusercontent.com/warith-harchaoui/sftp-helper/main/assets/logo.png)](https://harchaoui.org/warith/ai-helpers)

SFTP Helper is a Python library that provides utility functions for working with SFTP servers via the system OpenSSH `sftp` client. Host key verification is on by default: `~/.ssh/known_hosts` is consulted and unknown hosts are rejected.

## The Promise

**Remote by design.** `sftp-helper` exists to move data to and from a *remote*
server, so it is deliberately **not** local-first and ships **no GUI**. For
cloud object storage (S3 / GCS / Azure / MinIO) use `bucket-helper`; for
downloading media from a URL use `youtube-helper`.

**Battle-tested.** Twelve tagged releases, a green CI on every push (unit
tests plus a linter that blocks the merge exactly like a failing test), and a
dedicated security pass (v3.2.1) that closed a path-injection gap in the
batch-command builder before it ever shipped to a user. Nothing here is
promised without a check backing it: the numbers above come straight from
this repository's own tags and `CHANGELOG.md`, not from a marketing claim.

## Documentation

[💻 Documentation](https://harchaoui.org/warith/ai-helpers/docs/sftp-helper-doc/)

[🗺️ Landscape](https://github.com/warith-harchaoui/sftp-helper/blob/main/LANDSCAPE.md)

[📋 Examples](https://github.com/warith-harchaoui/sftp-helper/blob/main/EXAMPLES.md)

## Features

- **Upload** a local file **or directory** to the server. Pass an explicit
  `sftp://host/path`, or omit it (single file only) to get a deterministic
  **content-hashed** name under `sftp_destination_path` (identical bytes
  de-duplicate to the same path). A directory is sent via `upload_many`,
  which packs-and-ships as one `tar.gz` archive (one `put` + one remote
  `tar` extraction) whenever the server accepts exec, instead of one round
  trip per file.
  `overwrite`/`resume`/`progress` knobs: skip destinations already present
  with a matching size (incremental sync), discard a stale partial transfer,
  or suppress the progress bar.
- **Download** a remote file **or directory** to disk (defaults to the remote
  basename for a single file), archive-accelerated the same way via
  `download_many`, with the same `overwrite`/`resume`/`progress` knobs.
- **Delete** a remote file, **idempotent**: removing an absent file succeeds.
- **Existence checks** for a remote **file** (`remote_file_exists`) and a remote
  **directory** (`remote_dir_exist`).
- **List a remote directory** (`list_dir`, optionally `recursive`) or list with
  per-entry size/mtime in one pass (`list_dir_stat`); **stat a single remote
  file** (`remote_stat`).
- **Create remote directories** with `mkdir -p` semantics
  (`make_remote_directory`): every missing intermediate level is created.
- **Path helpers**: `normalize_path` (single leading `/`, no trailing `/`) and
  `strip_sftp_path` (drop the `sftp://` scheme + host).
- **`remote_tempfile`** context manager: reserve a unique random remote path
  (optionally under a subdir, optionally with an extension) that is
  **auto-deleted on block exit**, even if an exception propagates; hands back
  both the `sftp://` address and its public HTTPS URL.
- **Credentials loader** (`credentials`) resolving JSON / YAML / directory /
  `SFTP_*` env vars / `.env`, with a masked `show-credentials` view.
- **Strict host-key verification, always on**: OpenSSH
  `StrictHostKeyChecking=yes`, no opt-out; trust an extra key via the optional
  `sftp_known_hosts` credential.
- **Three surfaces, one behavior**: Python library, argparse CLI (`sftp-helper`),
  click CLI twin (`sftp-helper-click`), and FastAPI HTTP surface. See the
  [multi-surface section](#multi-surface-exposure).
- Trigger catalogue in
  [`TRIGGERS.md`](https://github.com/warith-harchaoui/sftp-helper/blob/main/TRIGGERS.md).

## Installation

**Prerequisites**: **Python 3.10–3.13** and **git**, cross-platform:

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
git clone https://github.com/warith-harchaoui/sftp-helper.git
cd sftp-helper
pip install -e .

# Optional surfaces
pip install -e ".[cli]"
pip install -e ".[api]"
```

## Write your own configuration file

A ready-to-fill template is committed at [`settings.yaml.example`](https://github.com/warith-harchaoui/sftp-helper/blob/main/settings.yaml.example), with inline comments explaining every key and how to obtain its value. Copy it and edit in place; the real `settings.yaml` is gitignored so you cannot accidentally commit secrets:

```bash
cp settings.yaml.example settings.yaml
# then edit settings.yaml with your credentials
```

You may also provide a JSON file, environment variables, or an `.env` file; `sftp-helper` falls back in that order via `os_helper.get_config`:

Only **three** fields are required: `sftp_host`, `sftp_login`, `sftp_https`.
Authenticate with an SSH key (recommended: no password) by pointing `sftp_key`
at your **public** key (`~/.ssh/id_ed25519.pub`); OpenSSH lets your SSH agent or
hardware token do the signing, so no private-key material is ever named in this
file. Or load your key into the SSH agent and leave `sftp_key` empty.
`sftp_destination_path` is optional and defaults to the server root `/`.

_YAML_ (`settings.yaml`)
```yaml
sftp_host: "<sftp_host>"
sftp_login: "<sftp_login>"
sftp_https: "<sftp_https>"
sftp_key: "~/.ssh/id_ed25519.pub" # optional public key; empty -> SSH agent + default keys
# sftp_passwd: "<sftp_passwd>"    # optional fallback (needs `sshpass`)
# sftp_destination_path: "/base"  # optional; empty -> server root "/"
# sftp_port: "2022"               # optional; default 22
```
or

_JSON_
```json
{
    "sftp_host": "<sftp_host>",
    "sftp_login": "<sftp_login>",
    "sftp_https": "<sftp_https>",
    "sftp_key": "~/.ssh/id_ed25519.pub"
}
```
or

_ENVIRONMENT VARIABLES_
```bash
SFTP_HOST="<sftp_host>" \
SFTP_LOGIN="<sftp_login>" \
SFTP_HTTPS="<sftp_https>" \
SFTP_KEY="~/.ssh/id_ed25519.pub" \
python <your_python_script>
```
or

_.env_
```
SFTP_HOST                = <sftp_host>
SFTP_LOGIN               = <sftp_login>
SFTP_HTTPS               = <sftp_https>
SFTP_KEY                 = ~/.ssh/id_ed25519.pub
```

Where to find these (in your favorite FTP tool; mine is FileZilla):
  + `<sftp_host>` is the server host, e.g. `sftp.example.com`
  + `<sftp_login>` is your username
  + `<sftp_https>` corresponds to the web URL of `sftp_destination_path`
  + `sftp_key` points at the **public** half of the key you already use to
    `ssh`/`sftp` into the server (that same public key must be installed in the
    server's `authorized_keys`, and the private key loaded in your SSH agent);
    or leave it empty and rely on your SSH agent. Only if you run no agent,
    point it at the private key (`~/.ssh/id_ed25519`) instead.
  + <your_python_script> is your python script :)

### No SSH key yet?

The `ssh-keygen` command is identical on every OS: it writes the private key
to `~/.ssh/id_ed25519` and the public key to `~/.ssh/id_ed25519.pub`:

```bash
ssh-keygen -t ed25519 -C "you@example.com"
```

Load the **private** key into your SSH agent so the public key can sign, then
install the **public** key on the server:

```bash
# Load the private key into the agent
ssh-add --apple-use-keychain ~/.ssh/id_ed25519          # macOS
eval "$(ssh-agent -s)" && ssh-add ~/.ssh/id_ed25519     # Ubuntu / Linux
Start-Service ssh-agent; ssh-add $HOME\.ssh\id_ed25519  # Windows (PowerShell)

# Install the public key on the server (~/.ssh/authorized_keys)
ssh-copy-id -i ~/.ssh/id_ed25519.pub your-login@sftp.example.com   # macOS / Ubuntu
type $HOME\.ssh\id_ed25519.pub | ssh your-login@sftp.example.com "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"  # Windows
```

## Usage

For the full catalog of recipes (uploads, downloads, existence checks, recursive directory creation, temporary remote files with auto-cleanup, strict host-key verification), see [📋 EXAMPLES.md](https://github.com/warith-harchaoui/sftp-helper/blob/main/EXAMPLES.md).

Here's an example of how to use SFTP helper (**won't work without a valid `path/to/settings.yaml`**):

```python
import sftp_helper as sftph
import os_helper as osh

# Write a small text file
local_file = "example.txt"
with open(local_file, "wt") as f:
    f.write("A small example of text")

# Load creds from JSON / YAML file, or fall back to .env / environment vars.
cred = sftph.credentials("path/to/settings.yaml")

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

credentials = sftph.credentials("path/to/settings.yaml")

with sftph.remote_tempfile(credentials, ext="txt") as (sftp_address, url):
    sftph.upload("local.txt", credentials, sftp_address)
    assert osh.is_working_url(url)
# On exit, the remote file is deleted.
```

## Host key verification

A server's host key is how your machine recognizes it: the first time you
connect, OpenSSH records that key in `~/.ssh/known_hosts`; every later
connection checks the key still matches. Without that check, someone who can
intercept your network traffic could impersonate the server and read
everything you upload or download; the check is what makes that attack fail
silently instead of succeeding silently. `sftp_helper` never disables host key
verification. Every `sftp` invocation passes `StrictHostKeyChecking=yes` and
`~/.ssh/known_hosts` is consulted automatically, so a host whose key you have
not already accepted is rejected. To trust a server whose key lives
elsewhere, point at an extra known_hosts file via the optional
`sftp_known_hosts` credential.

## Multi-surface exposure

`sftp-helper` is not just a library: the same functions are exposed
as a CLI, a FastAPI HTTP surface, and MCP tools:

```bash
# Python library (default)
import sftp_helper as sftph

# argparse-based CLI (installed automatically)
sftp-helper upload      --config settings.yaml --input local.txt --remote /uploads/local.txt
sftp-helper upload      --config settings.yaml --input ./local_dir --remote /uploads/dir
sftp-helper download    --config settings.yaml --remote /uploads/local.txt --output out.txt
sftp-helper exists      --config settings.yaml --remote /uploads/local.txt
sftp-helper list        --config settings.yaml --remote /uploads --recursive
sftp-helper remote-stat --config settings.yaml --remote /uploads/local.txt
sftp-helper mkdir       --config settings.yaml --remote /uploads/a/b/c

# click-based CLI twin (needs the [cli] extra)
pip install "sftp-helper[cli]"
sftp-helper-click upload --config settings.yaml --input local.txt --remote /uploads/local.txt

# FastAPI HTTP surface (needs the [api] extra)
pip install "sftp-helper[api]"
SFTP_HELPER_CONFIG=./settings.yaml uvicorn sftp_helper.api:app --port 8000
# → OpenAPI docs at http://localhost:8000/docs

# MCP tools for any MCP-aware agent host (needs the [mcp] extra), the same app
# with an added /mcp endpoint
pip install "sftp-helper[mcp]"
SFTP_HELPER_CONFIG=./settings.yaml sftp-helper-mcp
```

Docker image (HTTP on port 8000):

```bash
docker build -t sftp-helper .
docker run --rm -p 8000:8000 \
  -v $PWD/settings.yaml:/app/settings.yaml:ro \
  -e SFTP_HELPER_CONFIG=/app/settings.yaml \
  sftp-helper
```

See [`TRIGGERS.md`](https://github.com/warith-harchaoui/sftp-helper/blob/main/TRIGGERS.md)
for the exhaustive catalogue of phrasings, commands, and functions that invoke it
(and when to reach for `bucket-helper` / `youtube-helper` instead).

There is **no GUI**. A forward-looking dashboard *design plan* (pipeline
dashboard, storage-health panel, live transfer feed) lives in
[GUI.md](https://github.com/warith-harchaoui/sftp-helper/blob/main/GUI.md), but no
such code ships today.

## Author

 - [Warith HARCHAOUI](https://linkedin.com/in/warith-harchaoui)

## Acknowledgements

Special thanks to [Mohamed Chelali](https://mchelali.github.io) and [Bachir Zerroug](https://www.linkedin.com/in/bachirzerroug) for fruitful discussions.

## License

This project is licensed under the BSD-3-Clause License; see the [LICENSE](https://github.com/warith-harchaoui/sftp-helper/blob/main/LICENSE) file for details.
