# sftp-helper CLI reference

Full command surface for the `sftp-helper` skill. The argparse CLI
(`sftp-helper`) ships with the base package; the click twin
(`sftp-helper-click`, `[cli]` extra) mirrors the exact same subcommand and flag
names, so anything below works for both by swapping the program name.

## Subcommands

| Subcommand | Purpose | Notable flags |
|------------|---------|---------------|
| `upload` | Upload a local file to the server | `--config --input --remote` |
| `download` | Download a remote file to disk | `--config --remote --output` |
| `delete` | Delete a remote file (idempotent) | `--config --remote` |
| `exists` | File-existence probe (exit 0/1) | `--config --remote` |
| `dir-exists` | Directory-existence probe (exit 0/1) | `--config --remote` |
| `mkdir` | Create a remote dir (`mkdir -p`) | `--config --remote` |
| `normalize-path` | Canonicalize a remote path | `--path` |
| `strip-path` | Strip `sftp://<host>` from an address | `--config --address` |
| `tempfile` | Reserve a self-deleting remote path | `--config --ext --subdir` |
| `show-credentials` | Print resolved creds (masked) as JSON | `--config` |

`sftp-helper --version` and `sftp-helper <sub> --help` work for every subcommand.

## The shared `--config` flag

Every network-touching subcommand takes `--config`: a path to a JSON/YAML file,
a directory containing one, or omitted entirely (falls back to `SFTP_*` env vars
/ `.env`). Same discovery order as the library's `credentials()`. The two pure
helpers (`normalize-path`, and `strip-path` which needs only the host) are the
only ones with a different flag shape.

## Flag details

### upload
- `--input` (required) local file path.
- `--remote` optional full `sftp://host/path` or plain remote path. If omitted,
  a content-hashed name under `sftp_destination_path` is generated (identical
  bytes map to the same remote path). Prints the resulting address to stdout.

### download
- `--remote` (required) full `sftp://` address or plain remote path.
- `--output` optional local destination; defaults to the remote basename in the
  cwd. Prints the local path written.

### delete
- `--remote` (required). Idempotent: deleting an absent file still exits `0`.

### exists / dir-exists
- `--remote` (required). Prints `true` / `false` AND sets the exit code to the
  `test -e` convention: `0` when present, `1` when missing — so shell `if` reads
  naturally.

### mkdir
- `--remote` (required). `mkdir -p` semantics: every missing intermediate level
  is created. Prints the path back.

### normalize-path
- `--path` (required). Pure helper — no credentials, no network. Ensures a single
  leading `/` and no trailing `/` (root `"/"` preserved). e.g. `foo/bar///` → `/foo/bar`.

### strip-path
- `--address` (required). Removes the `sftp://` scheme and the host token (read
  from credentials) and normalizes what remains. Idempotent.

### tempfile
- `--ext` optional file extension (with or without leading dot).
- `--subdir` optional subdirectory under `sftp_destination_path` (created if
  missing). Prints `{"sftp_address": …, "url": …}` as JSON. NOTE: the reserved
  file is **deleted on exit** — the CLI reports the coordinates only. For a
  stage-and-share flow that keeps the file for the block's lifetime, use the
  library's `remote_tempfile` context manager directly.

### show-credentials
- Prints the resolved credentials as JSON with `sftp_passwd` masked to `***`.
  Handy for debugging config discovery (file vs env vs `.env`).

## Output contract (for scripting)

- `upload` prints the remote address; `download` prints the local path;
  `mkdir` / `strip-path` / `normalize-path` print the single resulting string.
- `exists` / `dir-exists` print `true`/`false` and encode the answer in `$?`.
- `tempfile` and `show-credentials` print JSON.
- Any failure (connection, transfer) propagates as a non-zero exit code with the
  wrapped error naming the endpoint(s) on stderr.
