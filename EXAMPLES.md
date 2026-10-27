# SFTP Helper Examples

[🇫🇷 EXEMPLES.md](https://github.com/warith-harchaoui/sftp-helper/blob/main/EXEMPLES.md) · 🇬🇧 English

Practical recipes for `sftp-helper`, each one a scenario rather than a
function listing. Everything past [Setup](#setup) assumes the imports and the
`cred` dict that section establishes.

---

## Table of Contents

[Setup](#setup) · [Command line](#command-line) · [Troubleshooting](#troubleshooting)

1. [Load credentials](#1-load-credentials)
2. [Upload / download / delete](#2-upload--download--delete)
3. [Existence checks](#3-existence-checks)
4. [Create remote directories](#4-create-remote-directories)
5. [Temporary remote files (auto-cleanup)](#5-temporary-remote-files-auto-cleanup)
6. [Listing and stat](#6-listing-and-stat)
7. [Path helpers (no server needed)](#7-path-helpers-no-server-needed)
8. [Strict host-key verification](#8-strict-host-key-verification)
9. [Combining with bucket-helper / os-helper](#9-combining-with-bucket-helper--os-helper)

---

## Setup

Install from PyPI:

```bash
pip install --force-reinstall --no-cache-dir \
    sftp-helper
```

`sftp-helper` drives the system OpenSSH `sftp` client. It ships on macOS,
most Linux distributions, and Windows 10 1809+ / Server 2019+; if `sftp` is
not on your `PATH`, install your platform's `openssh-client` package (on
Windows, enable the "OpenSSH Client" optional feature).

Every snippet below starts from these two imports:

```python
import sftp_helper as sftph
import os_helper as osh
```

and, except in [§7](#7-path-helpers-no-server-needed), from a `cred` dict
built by [§1](#1-load-credentials) — so a section can be read on its own
without hunting for what `sftph` and `cred` were bound to.

## 1. Load credentials

`credentials(...)` returns a dict assembled from JSON / YAML / `.env` /
environment variables. The fallback order is dictated by
`os_helper.get_config`.

```python
# From a JSON / YAML file
cred = sftph.credentials("path/to/settings.yaml")

# Or fall back to .env / SFTP_* environment variables
cred = sftph.credentials()
```

Required keys: `sftp_host`, `sftp_login`, `sftp_https`. Optional keys:
`sftp_key` (path to your SSH key, recommended: your **public** key
`~/.ssh/id_ed25519.pub`, so the agent/token signs and no private-key material
is named here; a private-key path also works; empty ⇒ SSH agent + default
`~/.ssh` identities), `sftp_passwd` (password fallback, needs
`sshpass`), `sftp_destination_path` (default: server root `/`),
`sftp_port` (default `22`), `sftp_known_hosts` (extra known-hosts file).

### No SSH key yet?

The `ssh-keygen` command is identical on every OS: it writes the private key
to `~/.ssh/id_ed25519` and the public key to `~/.ssh/id_ed25519.pub`:

```bash
ssh-keygen -t ed25519 -C "you@example.com"
```

Load the **private** key into your SSH agent so the public key can sign:

```bash
# macOS
ssh-add --apple-use-keychain ~/.ssh/id_ed25519
# Ubuntu / Linux
eval "$(ssh-agent -s)" && ssh-add ~/.ssh/id_ed25519
# Windows (PowerShell)
Start-Service ssh-agent; ssh-add $HOME\.ssh\id_ed25519
```

Install the **public** key on the server (`~/.ssh/authorized_keys`):

```bash
# macOS / Ubuntu
ssh-copy-id -i ~/.ssh/id_ed25519.pub your-login@sftp.example.com
# Windows (PowerShell)
type $HOME\.ssh\id_ed25519.pub | ssh your-login@sftp.example.com "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
```

## 2. Upload / download / delete

```python
# Upload a local file. If sftp_address is empty, sftp-helper builds a
# content-hashed name under cred["sftp_destination_path"].
remote_uri = sftph.upload("report.pdf", cred)
# remote_uri is the full sftp:// or remote-path form of the destination.

# Or upload to a deterministic destination:
sftph.upload("report.pdf", cred, "/inbox/report.pdf")

# Download (defaults to the remote basename in cwd)
sftph.download("/inbox/report.pdf", cred)
sftph.download("/inbox/report.pdf", cred, "local_copy.pdf")

# Delete, idempotent (returns True if the remote file is gone after the call)
sftph.delete("/inbox/report.pdf", cred)
```

Both directions are resumable, retried with exponential backoff, and atomic:
an upload lands in a temp remote path and is renamed onto its destination
only once its size matches, while a download lands in a `<local_path>.part`
sidecar and is `os.replace`-d only once verified. A caller never observes a
half-written file. Pass `sha256=` to `download` to content-verify on top of
the size check:

```python
sftph.download("/inbox/report.pdf", cred, "report.pdf", sha256="e3b0c442...")
```

`overwrite=False` turns a repeat call into an incremental sync (skip what is
already there with a matching size), `resume=False` discards a stale partial
instead of continuing it, and `progress=False` suppresses the bar even on a
terminal:

```python
sftph.upload("report.pdf", cred, "/inbox/report.pdf", overwrite=False, progress=False)
```

A **directory** goes through the same two calls. `sftp_address` is then
required — there is no single file to hash a default name from — and names
the destination directory:

```python
sftph.upload("./renders", cred, "/inbox/renders")  # every non-hidden file, recursively
sftph.download("/inbox/renders", cred, "./renders_copy")
```

Omitting the destination for a directory is the one argument mistake worth
knowing by heart:

```python
sftph.upload("./renders", cred, "")
# ValueError: sftp_address is required when uploading a folder (there is no
# single file to derive a content-hashed default from).
```

For an explicit batch with per-file destinations, call `upload_many` /
`download_many` directly. On a server that also accepts `ssh` exec they
collapse the batch into one `tar.gz` transfer plus one remote extraction
instead of one round trip per file; elsewhere they fall back to the per-file
loop, unaffected:

```python
sent = sftph.upload_many(
    [("a.png", "/inbox/img/a.png"), ("b.png", "/inbox/img/b.png")],
    cred,
)
# {"a.png": "/inbox/img/a.png", "b.png": "/inbox/img/b.png"}
```

## 3. Existence checks

```python
if sftph.remote_file_exists("/inbox/report.pdf", cred):
    print("still on the server")
    # still on the server

if sftph.remote_dir_exist("/inbox/", cred):
    print("inbox directory is ready")
    # inbox directory is ready
```

## 4. Create remote directories

`make_remote_directory(path, cred)` is recursive: it walks each
intermediate level and creates the missing ones.

```python
sftph.make_remote_directory("/inbox/2026-06/raw", cred)
```

## 5. Temporary remote files (auto-cleanup)

`remote_tempfile(...)` reserves a unique random remote path and deletes
it automatically on block exit, even if an exception is raised.

```python
with sftph.remote_tempfile(cred, ext="json") as (sftp_address, url):
    # The file does NOT exist yet: upload to it:
    sftph.upload("payload.json", cred, sftp_address)

    # Hand the URL to a downstream consumer (webhook, transcoder, ...).
    assert osh.is_working_url(url), f"URL not live: {url}"
    print(f"ready for the downstream consumer: {url}")
# At this point, the remote file is gone.
```

Use the `subdir="..."` argument to scope the reservation under a
sub-folder of `cred["sftp_destination_path"]`:

```python
with sftph.remote_tempfile(cred, ext="mp4", subdir="renders/2026") as (addr, url):
    sftph.upload("clip.mp4", cred, addr)
    print(f"queue this for transcoding: {url}")
```

## 6. Listing and stat

Before deciding what to transfer, ask the server what it already holds.
`list_dir` returns the immediate entries, or relative paths through the whole
tree with `recursive=True`:

```python
sftph.list_dir("/inbox", cred)
# ['2026-06', 'readme.txt']

sftph.list_dir("/inbox", cred, recursive=True)
# ['readme.txt', '2026-06/report.pdf']
```

`remote_stat` gives one file's size and mtime, or `None` when the path is
absent (or is a directory — this is a file stat):

```python
info = sftph.remote_stat("/inbox/readme.txt", cred)
if info is not None:
    print(info["size"], info["mtime"].isoformat())
```

`mtime` is parsed from the server's `ls -l` line, so it has minute
resolution and carries no timezone: good enough for "is my local copy
newer", not for anything needing seconds.

`list_dir_stat` is the bulk form — one walk, one `{relative_path: {"size",
"mtime"}}` map for the whole tree — so a sync decision needs no per-file
round trip:

```python
remote = sftph.list_dir_stat("/inbox", cred)
empty = [path for path, meta in remote.items() if meta["size"] == 0]
```

## 7. Path helpers (no server needed)

`normalize_path` and `strip_sftp_path` are pure functions needing no
connection, so these are the snippets you can run straight after installing.
`normalize_path` gives a remote path its canonical form — one leading `/`,
no trailing one:

```python
>>> sftph.normalize_path("uploads/reports///")
'/uploads/reports'
```

`strip_sftp_path` is the inverse of writing a full address: it drops the
scheme and the host, reading only `cred["sftp_host"]`, and is idempotent on
a path that is already bare:

```python
>>> sftph.strip_sftp_path("sftp://sftp.example.com/inbox/report.pdf",
...                       {"sftp_host": "sftp.example.com"})
'/inbox/report.pdf'
```

`normalize_path` is also the package's injection guard. Every function that
accepts a remote path funnels through it, and it rejects a path that could
break out of an `sftp -b` batch command's quoting:

```python
>>> sftph.normalize_path('/inbox/"; rm -rf /')
Traceback (most recent call last):
ValueError: Unsafe remote path (contains a newline, NUL byte, or double quote, any of which could break out of an sftp/ssh command string): '/inbox/"; rm -rf /'
```

## 8. Strict host-key verification

`sftp-helper` never disables host-key verification. Every `sftp` call
passes `StrictHostKeyChecking=yes` and `~/.ssh/known_hosts` is consulted
automatically. To trust a server whose key lives in a non-default
location, point at the extra known-hosts file via the optional
`sftp_known_hosts` credential:

```python
cred = sftph.credentials("path/to/settings.yaml")
cred["sftp_known_hosts"] = "/etc/ssh/known_hosts.d/inbox-prod"
sftph.upload("payload.json", cred, "/inbox/payload.json")
```

That store is *added* to the default ones rather than replacing them, so
hosts you already trust keep working.

If you connect to a host whose key is not in any consulted store, the
`sftp` connection is refused and the operation raises. There is no
opt-out flag by design.

## 9. Combining with bucket-helper / os-helper

A common pipeline: write a file locally, push it to S3 (long-term
storage), then mirror to an SFTP partner inbox (one-shot consumer):

```python
import os_helper as osh
import bucket_helper as bh
import sftp_helper as sftph

osh.verbosity(2)

# Long-term archive on S3
s3_cred = bh.credentials("path/to/settings.yaml")
s3_uri = bh.upload("monthly_report.pdf", s3_cred, "reports/2026-06.pdf")

# Mirror to SFTP partner
sftp_cred = sftph.credentials("path/to/settings.yaml")
sftph.upload("monthly_report.pdf", sftp_cred, "/inbox/2026-06.pdf")

print(f"Archived at {s3_uri}; delivered to SFTP partner.")
# Archived at s3://my-bucket/reports/2026-06.pdf; delivered to SFTP partner.
```

## Command line

One click CLI, `sftp-helper`, covering twelve subcommands. Every one that
touches the server takes `--config` (a JSON/YAML file or a directory holding
one; omit it to fall back to `.env` / `SFTP_*` environment variables):

```bash
sftp-helper upload           --config settings.yaml --input local.txt --remote /inbox/local.txt
sftp-helper upload           --config settings.yaml --input ./renders --remote /inbox/renders
sftp-helper download         --config settings.yaml --remote /inbox/local.txt --output out.txt
sftp-helper delete           --config settings.yaml --remote /inbox/local.txt
sftp-helper exists           --config settings.yaml --remote /inbox/local.txt
sftp-helper dir-exists       --config settings.yaml --remote /inbox
sftp-helper list             --config settings.yaml --remote /inbox --recursive
sftp-helper remote-stat      --config settings.yaml --remote /inbox/local.txt
sftp-helper mkdir            --config settings.yaml --remote /inbox/a/b/c
sftp-helper strip-path       --config settings.yaml --address sftp://sftp.example.com/inbox/local.txt
sftp-helper tempfile         --config settings.yaml --ext json --subdir renders/2026
sftp-helper show-credentials --config settings.yaml
sftp-helper normalize-path   --path "uploads/reports///"
```

`normalize-path` is the one subcommand needing neither a server nor a
config, which makes it the quickest way to prove an install works:

```console
$ sftp-helper normalize-path --path "uploads/reports///"
/uploads/reports
```

`upload` and `download` also take `--no-overwrite` (skip destinations
already present with a matching size), `--no-resume` (discard a stale
partial instead of continuing it) and `--no-progress`.

Exit codes carry the answer where there is one to carry: `exists` and
`dir-exists` print `true` and exit 0, or print `false` and exit 1;
`remote-stat` prints JSON, or `null` and exits 1 when the path is absent. So
a shell `if` needs no output parsing:

```bash
if sftp-helper exists --config settings.yaml --remote /inbox/local.txt; then
    sftp-helper download --config settings.yaml --remote /inbox/local.txt
fi
```

`show-credentials` prints the resolved config as JSON with `sftp_passwd`
replaced by `***`. `-h` / `--help` works on the group and on every
subcommand; `-V` / `--version` prints the installed version.

## Troubleshooting

**`The OpenSSH 'sftp' client was not found on PATH.`** — `sftp-helper` drives
the system client rather than an in-process SSH library, so it needs the
binary. The error names the install command for your OS (`apt` / `dnf` /
`pacman` on Linux, Homebrew on macOS, the "OpenSSH Client" optional feature
on Windows). It is checked up front, before any connection is attempted.

**`Missing required keys for 'SFTP' configuration in files, .env files, or
environment variables.`** — only three keys are required: `sftp_host`,
`sftp_login`, `sftp_https`. Either pass `--config` / `credentials(path)`
explicitly, or export `SFTP_HOST` / `SFTP_LOGIN` / `SFTP_HTTPS`. Run
`sftp-helper show-credentials` to see exactly what got resolved, password
masked.

**`Host key verification failed`** — expected, and not a bug to work around:
`StrictHostKeyChecking=yes` is passed on every invocation and no flag
disables it. Record the server's key first, the ordinary way:

```bash
ssh your-login@sftp.example.com    # accept the fingerprint once, interactively
# or, non-interactively:
ssh-keyscan -t ed25519 sftp.example.com >> ~/.ssh/known_hosts
```

If the key has to live somewhere else, set `sftp_known_hosts` — see
[§8](#8-strict-host-key-verification).

**`sftp_passwd is set but the 'sshpass' helper is not installed.`** — OpenSSH
refuses to read a password from the command line, so password auth needs the
`sshpass` shim, which has no native Windows build. The fix that works
everywhere is to stop using a password: set `sftp_key` (or load your key into
the SSH agent) and leave `sftp_passwd` empty.

**A transfer that hangs** — `ConnectTimeout=30` only bounds *reaching* the
host; a session that connects and then goes quiet is bounded by
`ServerAliveInterval=15` with `ServerAliveCountMax=4`, about a minute. Both
are tunable, and connection multiplexing makes this matter more than it would
in a one-shot client: a wedged master connection hangs every later call that
attaches to its control socket.

```bash
export SFTP_HELPER_SERVER_ALIVE_INTERVAL=30   # seconds; 0 disables keepalives
export SFTP_HELPER_SERVER_ALIVE_COUNT_MAX=4   # unanswered probes before giving up
```

**`ValueError: Unsafe remote path ...`** — a newline, carriage return, NUL
byte or double quote in a remote path is rejected rather than quoted, because
any of them can break out of an `sftp -b` batch command. See
[§7](#7-path-helpers-no-server-needed).

**An upload that failed and left something behind** — that is deliberate. The
partial sits at a temp remote path ending in `.sftp-helper-upload`, so the
next `upload` to the same destination resumes instead of restarting. Pass
`resume=False` (or `--no-resume`) to discard it.
