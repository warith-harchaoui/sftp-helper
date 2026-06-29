"""
SFTP Helper

This module provides functions to interact with an SFTP server, allowing users
to perform file uploads, downloads, and deletions, as well as to check file
existence remotely. Backed by paramiko with strict host-key verification.

Author:
- Warith HARCHAOUI (https://linkedin.com/in/warith-harchaoui)
"""

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
