# sftp-helper CLI reference

Two CLIs over the same operations. `sftp-helper` (argparse) ships with the
core package; `sftp-helper-click` (needs `[cli]`) is the click twin.

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
| `sftp_key` | no | private-key path |
| `sftp_destination_path` | no | write root, default `/` |

A key-based login writing to the server root needs only the three required
fields. Start from the repo's `settings.yaml.example`.

```bash
sftp-helper show-credentials --config settings.yaml
```

prints the resolved config with `sftp_passwd` masked as `***`. The schema stays
stable so scripts can read it — but never echo a real secret anywhere.

## Transfer

```bash
sftp-helper upload   --config PATH --input LOCAL  --remote REMOTE
sftp-helper download --config PATH --remote REMOTE --output LOCAL
```

`upload` prints the public URL built from `sftp_https` — that URL is the
result worth reporting. An upload to an existing path **overwrites it**; run
`exists` first when that is a possibility.

For several files, use the library's `upload_many` / `download_many`: they
reuse one authenticated connection instead of paying the handshake per file.

## Inspection

```bash
sftp-helper exists      --config PATH --remote REMOTE
sftp-helper dir-exists  --config PATH --remote REMOTE
sftp-helper list        --config PATH --remote REMOTE_DIR
sftp-helper remote-stat --config PATH --remote REMOTE
```

`remote-stat` gives size and mtime — use it to decide whether a re-upload is
needed at all.

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

`tempfile` mints a collision-free remote path for pipeline intermediates.
`normalize-path` collapses double and trailing slashes. `strip-path` turns an
`sftp://host/...` address into the server-relative path. Use them instead of
string surgery.

## Output contract

- `upload` prints the public URL; `download` prints the local path written.
- `exists` / `dir-exists` print `true` / `false` and exit `0` either way; a
  genuine failure (auth, unreachable host) exits non-zero.
- `list` prints one entry per line; `remote-stat` prints size and mtime.
- Failures are logged through `os_helper` and exit non-zero; a partial
  download is removed rather than left behind.

## When a call fails

1. **Authentication failed** — check which config actually won the precedence
   order (`show-credentials`) before changing any value. A `.env` quietly
   overriding a YAML file is the usual surprise.
2. **No such file** — remote paths are absolute unless
   `sftp_destination_path` says otherwise; run `normalize-path` on what you
   are sending.
3. **Permission denied on write** — the parent directory may not exist. Run
   `mkdir` first; it creates parents.
