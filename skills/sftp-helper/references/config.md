# sftp-helper credentials contract

Every network operation takes a `cred` dict, produced by `credentials(...)`.
The loader (`os_helper.get_config`) resolves the required keys from, in order:

1. an explicit JSON/YAML file path passed to `credentials("…")`,
2. a directory passed to `credentials("…")` that contains one such file,
3. `SFTP_*` environment variables, then a `.env` file.

If none of those supplies the full required set, the loader raises
`RuntimeError` — callers never get a half-populated dict.

## Keys

| Key | Required | Meaning |
|-----|----------|---------|
| `sftp_host` | yes | Hostname of the SFTP server (e.g. `sftp.example.com`). |
| `sftp_login` | yes | SSH/SFTP username. |
| `sftp_passwd` | yes | Password. Empty string → password auth is skipped and paramiko falls through to the SSH agent / default identity files (`~/.ssh/id_*`). |
| `sftp_destination_path` | yes | Remote base folder for auto-named uploads and `remote_tempfile`. |
| `sftp_https` | yes | Public web URL that maps to `sftp_destination_path` (used to hand a consumer a live URL). |
| `sftp_port` | no | SSH port (default `22`). |
| `sftp_known_hosts` | no | Extra known-hosts file to trust, in addition to `~/.ssh/known_hosts`. |

## Example files (committed at the repo root)

- `sftp_config.json.example` — JSON template.
- `sftp_config.yaml.example` — heavily-commented YAML template (preferred, since
  YAML supports inline docs for every key).

Copy either to a real name and edit in place:

```bash
cp sftp_config.json.example sftp_config.json
# then edit sftp_config.json with your credentials
```

Real `*config.json` / `*config.yaml` files are gitignored so secrets can never be
committed by accident — only the `*.example` templates are tracked. **Never** put
real credentials, private keys, or `.env` contents into a commit, an issue, or a
skill file.

## Host-key verification (always on)

`get_client_sftp` loads `~/.ssh/known_hosts`, plus `sftp_known_hosts` if set, and
installs `paramiko.RejectPolicy()`. Connecting to a host whose key is in neither
store raises `paramiko.SSHException`. There is **no flag to disable** verification
— to trust a server whose key lives elsewhere, point `sftp_known_hosts` at that
file.

## Env-var form (for the API / CI / containers)

```bash
SFTP_HOST=sftp.example.com \
SFTP_LOGIN=alice \
SFTP_PASSWD=secret \
SFTP_DESTINATION_PATH=/var/www/uploads \
SFTP_HTTPS=https://example.com/uploads \
python your_script.py
```

The FastAPI surface reads `SFTP_HELPER_CONFIG` (a file path) or these same env
vars once at import time.
