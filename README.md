# SFTP Helper

`SFTP Helper` belongs to a collection of libraries called `AI Helpers` developped for building Artificial Intelligence

This toolbox requires:
  - a `config.json` for the sftp parameters (or YAML or environment variables or .env)
  - that you previously added you SSH key of your local machine in the SFTP server

[🕸️ AI Helpers](https://harchaoui.org/warith/ai-helpers)

[![logo](assets/repository-open-graph-template.png)](https://harchaoui.org/warith/ai-helpers)

SFTP Helper is a Python library that provides utility functions for working with SFTP servers via [paramiko](https://www.paramiko.org/). Host key verification is on by default — `~/.ssh/known_hosts` is loaded and unknown hosts are rejected.

# Installation

## Install Package

We can recommand python environments. Check this link if you don't know how

[🥸 Tech tips](https://harchaoui.org/warith/4ml/#install)


```bash
pip install --force-reinstall --no-cache-dir git+https://github.com/warith-harchaoui/sftp-helper.git@v2.0.0
```

Or, from a checkout:

```bash
pip install -r requirements.txt
pip install -e .
```

## Write your own configuration file

You have to write your own `sftp_config.json` file or `sftp_config.yaml` file or environment variables (in case you don't provide neither `yaml` nor `json` files) or `.env` file:

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

Here are an example of how to use SFTP helper **which cannot work without a well written `path/to/sftp_config.json`** :
```python
import sftp_helper as sftph
import os_helper as osh

# Write a small text file
local_file = "example.txt"
with open(local_file, "wt") as fout:
    fout.write("A small example of text")

credentials = sftph.credentials("path/to/sftp_config.json") # or path/to/sftp_config.yaml
# or nothing in order to fall back on .env or environment variables

remote_file = credentials["sftp_destination_path"] + "/" + local_file
url = credentials["sftp_https"] + "/" + local_file

u = sftph.upload(local_file, credentials, remote_file)

osh.check(not(u is None), msg=f'Upload of {local_file} to {u} failed')

print(f"Upload of {local_file} to {u} is successful" if not(u is None) else f"Failed upload of {local_file} to {u}")

url_exist = osh.is_working_url(url)

print(f"URL is working:\n\t{url}" if url_exist else f"Failed URL:\n\t{url}")

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

# Authors
 - [Warith Harchaoui](https://harchaoui.org/warith)
 - [Mohamed Chelali](https://mchelali.github.io)
 - [Bachir Zerroug](https://www.linkedin.com/in/bachirzerroug)

