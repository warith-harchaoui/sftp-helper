"""
SFTP Helper — public API surface.

Re-exports the utility functions from :mod:`sftp_helper.main` so that
downstream code can simply write ``import sftp_helper as sftph`` and reach
every supported operation (credentials loading, upload, download, exists,
delete, mkdir -p, remote temp file with auto-cleanup) without knowing about
the module layout.

Backed by the system OpenSSH ``sftp`` client with strict host-key
verification. See the module docs for the full policy — there is no flag to
disable verification.

Usage Example
-------------
>>> import sftp_helper as sftph
>>> cred = sftph.credentials("settings.yaml")
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
    "list_dir",
    "list_dir_stat",
    "remote_stat",
    "upload_many",
    "download_many",
]

from .main import (
    credentials,
    delete,
    download,
    download_many,
    get_client_sftp,
    list_dir,
    list_dir_stat,
    make_remote_directory,
    normalize_path,
    remote_dir_exist,
    remote_file_exists,
    remote_stat,
    remote_tempfile,
    strip_sftp_path,
    upload,
    upload_many,
)
