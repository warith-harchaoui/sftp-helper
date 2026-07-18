# SFTP Helper Examples

Practical recipes for `sftp-helper`. Every snippet assumes:

```python
import sftp_helper as sftph
import os_helper as osh
```

and that you have written your credentials to `path/to/sftp_config.json`
(or YAML, or `.env`, or environment variables — see the README for the
required keys).

---

## Table of Contents

1. [Setup](#setup)
2. [Load credentials](#load-credentials)
3. [Upload / download / delete](#upload--download--delete)
4. [Existence checks](#existence-checks)
5. [Create remote directories](#create-remote-directories)
6. [Temporary remote files (auto-cleanup)](#temporary-remote-files-auto-cleanup)
7. [Strict host-key verification](#strict-host-key-verification)
8. [Combining with bucket-helper / os-helper](#combining-with-bucket-helper--os-helper)

---

## Setup

Install with pip (pin the version you want):

```bash
pip install --force-reinstall --no-cache-dir \
    git+https://github.com/warith-harchaoui/sftp-helper.git@v2.2.4
```

`sftp-helper` is built on top of [paramiko](https://www.paramiko.org/);
no extra system dependency is needed (paramiko ships its own OpenSSL
bindings).

## Load credentials

`credentials(...)` returns a dict assembled from JSON / YAML / `.env` /
environment variables. The fallback order is dictated by
`os_helper.get_config`.

```python
# From a JSON / YAML file
cred = sftph.credentials("path/to/sftp_config.json")

# Or fall back to .env / SFTP_* environment variables
cred = sftph.credentials()
```

Required keys: `sftp_host`, `sftp_login`, `sftp_passwd`,
`sftp_destination_path`, `sftp_https`. Optional keys:
`sftp_port` (default `22`), `sftp_known_hosts` (extra known-hosts file).

## Upload / download / delete

```python
# Upload a local file. If sftp_address is empty, sftp-helper builds a
# content-hashed name under cred["sftp_destination_path"].
remote_uri = sftph.upload("report.pdf", cred)
# remote_uri is the full sftp:// or remote-path form returned by paramiko.

# Or upload to a deterministic destination:
sftph.upload("report.pdf", cred, "/inbox/report.pdf")

# Download (defaults to the remote basename in cwd)
sftph.download("/inbox/report.pdf", cred)
sftph.download("/inbox/report.pdf", cred, "local_copy.pdf")

# Delete — idempotent (returns True if the remote file is gone after the call)
sftph.delete("/inbox/report.pdf", cred)
```

## Existence checks

```python
if sftph.remote_file_exists("/inbox/report.pdf", cred):
    print("still on the server")
    # still on the server

if sftph.remote_dir_exist("/inbox/", cred):
    print("inbox directory is ready")
    # inbox directory is ready
```

## Create remote directories

`make_remote_directory(path, cred)` is recursive — it walks each
intermediate level and creates the missing ones.

```python
sftph.make_remote_directory("/inbox/2026-06/raw", cred)
```

## Temporary remote files (auto-cleanup)

`remote_tempfile(...)` reserves a unique random remote path and deletes
it automatically on block exit, even if an exception is raised.

```python
with sftph.remote_tempfile(cred, ext="json") as (sftp_address, url):
    # The file does NOT exist yet — upload to it:
    sftph.upload("payload.json", cred, sftp_address)

    # Hand the URL to a downstream consumer (webhook, transcoder, ...).
    assert osh.is_working_url(url), f"URL not live: {url}"
    notify_downstream(url)
# At this point, the remote file is gone.
```

Use the `subdir="..."` argument to scope the reservation under a
sub-folder of `cred["sftp_destination_path"]`:

```python
with sftph.remote_tempfile(cred, ext="mp4", subdir="renders/2026") as (addr, url):
    sftph.upload("clip.mp4", cred, addr)
    queue_for_transcoding(url)
```

## Strict host-key verification

`sftp-helper` never disables host-key verification. The default policy
is `paramiko.RejectPolicy()` and `~/.ssh/known_hosts` is loaded
automatically. To trust a server whose key lives in a non-default
location, point at the extra known-hosts file via the optional
`sftp_known_hosts` credential:

```python
cred = sftph.credentials("path/to/sftp_config.json")
cred["sftp_known_hosts"] = "/etc/ssh/known_hosts.d/inbox-prod"
sftph.upload("payload.json", cred, "/inbox/payload.json")
```

If you connect to a host whose key is not in any loaded store,
`get_client_sftp` raises `paramiko.SSHException`. There is no opt-out
flag by design.

## Combining with bucket-helper / os-helper

A common pipeline: write a file locally, push it to S3 (long-term
storage), then mirror to an SFTP partner inbox (one-shot consumer):

```python
import os_helper as osh
import bucket_helper as bh
import sftp_helper as sftph

osh.verbosity(2)

# Long-term archive on S3
s3_cred = bh.credentials("path/to/s3_config.json")
s3_uri = bh.upload("monthly_report.pdf", s3_cred, "reports/2026-06.pdf")

# Mirror to SFTP partner
sftp_cred = sftph.credentials("path/to/sftp_config.json")
sftph.upload("monthly_report.pdf", sftp_cred, "/inbox/2026-06.pdf")

print(f"Archived at {s3_uri}; delivered to SFTP partner.")
# Archived at s3://my-bucket/reports/2026-06.pdf; delivered to SFTP partner.
```
