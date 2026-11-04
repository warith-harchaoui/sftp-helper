# sftp-helper CLI reference

One CLI, `sftp-helper`, built with click and shipped with the core package,
over the same operations the library and the HTTP surface expose.

Every command takes `--config PATH`; without it, credentials resolve from the
environment.

## Configuration

Credentials resolve through `os_helper.get_config`, in precedence order:
a JSON / YAML config file, a `.env`, then environment variables.

| Key | Required | Meaning |
|---|---|---|
| `sftp_host` | yes | hostname |
| `sftp_login` | yes | username |
| `sftp_https` | yes | base public URL used to build published URLs |
| `sftp_passwd` | no | password (omit when using a key) |
| `sftp_key` | no | key path: the public key when an SSH agent holds the private one, else the private key |
| `sftp_destination_path` | no | write root, default `/` |
| `sftp_port` | no | SSH port, default `22` |
| `sftp_known_hosts` | no | extra known_hosts file; host-key checking is always on |

A key-based login writing to the server root needs only the three required
fields. Start from the repo's `settings.yaml.example`.

```bash
sftp-helper show-credentials --config settings.yaml
```

prints the resolved config with `sftp_passwd` masked as `***`. The schema stays
stable so scripts can read it — but never echo a real secret anywhere.

## Transfer

```bash
sftp-helper upload   --config PATH --input LOCAL  [--remote REMOTE] [--no-overwrite] [--no-resume] [--no-progress]
sftp-helper download --config PATH --remote REMOTE [--output LOCAL] [--no-overwrite] [--no-resume] [--no-progress]
```

Both take a file or a whole directory (a directory upload needs `--remote`).
`upload` prints the remote address it wrote (the `sftp://` address or plain
path it was given, or one under `sftp_destination_path` named from the file's hash when
`--remote` is omitted); for a public `https://` link, use `tempfile`, which
builds it from `sftp_https`. `download` without `--output` writes the remote
basename into the current directory.

An upload to an existing path **overwrites it** by default; `--no-overwrite`
skips destinations already present with the same size (an incremental sync),
`--no-resume` discards a stale partial transfer instead of continuing it, and
`--no-progress` silences the bar.

For several files, use the library's `upload_many` / `download_many`: they
reuse one authenticated connection instead of paying the handshake per file.

## Inspection

```bash
sftp-helper exists      --config PATH --remote REMOTE
sftp-helper dir-exists  --config PATH --remote REMOTE
sftp-helper list        --config PATH --remote REMOTE_DIR [--recursive]
sftp-helper remote-stat --config PATH --remote REMOTE
```

`remote-stat` gives size and mtime — use it to decide whether a re-upload is
needed at all. `list --recursive` walks sub-directories too, with paths
relative to `--remote`.

## Mutation — confirm with the user first

```bash
sftp-helper delete --config PATH --remote REMOTE
sftp-helper mkdir  --config PATH --remote /a/b/c        # creates parents
```

`delete` is not undoable, and a web host's document root is not a scratch
directory. Name the exact path back to the user before calling it.

## Utilities

```bash
sftp-helper tempfile       --config PATH [--ext txt] [--subdir batch-42]
sftp-helper normalize-path --path //foo/bar/
sftp-helper strip-path     --config PATH --address sftp://host/foo/bar
```

`tempfile` mints a collision-free remote path for pipeline intermediates and
prints `{"sftp_address": ..., "url": ...}`, the URL built from `sftp_https`;
it uploads nothing.
`normalize-path` collapses double and trailing slashes. `strip-path` turns an
`sftp://host/...` address into the server-relative path. Use them instead of
string surgery.

## Output contract

- `upload` prints the remote address written; `download` prints the local
  path written.
- `exists` / `dir-exists` print `true` and exit `0`, or print `false` and exit
  `1`, so they work in a shell `if`. A genuine failure (auth, unreachable
  host) prints one `Error: ...` line and exits `1` too: read the output, not
  only the exit code.
- `list` prints one entry per line; `remote-stat` prints
  `{"size": ..., "mtime": ...}` as JSON, or `null` with exit `1` when the path
  is absent.
- `delete` prints nothing and succeeds on an absent file; `mkdir` prints the
  directory it made.
- Failures exit non-zero. A failed download keeps its `.part` file and a
  failed upload its temporary remote file, so the next identical call resumes
  where the transfer stopped (unless `--no-resume`).

## When a call fails

1. **Authentication failed** — check which config actually won the precedence
   order (`show-credentials`) before changing any value. A `.env` quietly
   overriding a YAML file is the usual surprise.
2. **No such file** — remote paths are absolute unless
   `sftp_destination_path` says otherwise; run `normalize-path` on what you
   are sending.
3. **Permission denied on write** — the parent directory may not exist. Run
   `mkdir` first; it creates parents.
