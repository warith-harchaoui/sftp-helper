"""
SFTP Helper — public API surface.

Re-exports the utility functions from :mod:`sftp_helper.main` so that
downstream code can simply write ``import sftp_helper as sftph`` and reach
every supported operation (credentials loading, connection context manager,
upload, download, exists, delete, mkdir -p, remote temp file with
auto-cleanup) without knowing about the module layout.

Backed by paramiko with strict host-key verification. See the module docs
for the full policy — there is no flag to disable verification.

Usage Example
-------------
>>> import sftp_helper as sftph
>>> cred = sftph.credentials("sftp_config.json")
>>> sftph.upload("local.txt", cred, "/remote/base/local.txt")
>>> assert sftph.remote_file_exists("/remote/base/local.txt", cred)
>>> sftph.download("/remote/base/local.txt", cred, "roundtrip.txt")
>>> sftph.delete("/remote/base/local.txt", cred)

Author
------
Warith Harchaoui, Ph.D. — https://linkedin.com/in/warith-harchaoui/
"""

__author__ = "Warith Harchaoui, Ph.D."
__email__ = "warithmetics@deraison.ai"

# Specify the public API of this module using __all__
__all__ = [
    "credentials",
    "get_client_sftp",
    "normalize_path",
    "strip_sftp_path",
    "remote_file_exists",
    "delete",
    "upload",
    "download",
    "remote_dir_exist",
    "make_remote_directory",
    "remote_tempfile",
]

from .main import (
    credentials,
    delete,
    download,
    get_client_sftp,
    make_remote_directory,
    normalize_path,
    remote_dir_exist,
    remote_file_exists,
    remote_tempfile,
    strip_sftp_path,
    upload,
)
