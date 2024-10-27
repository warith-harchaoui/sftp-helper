"""
SFTP Helper

This module provides functions to interact with an SFTP server, allowing users to perform file uploads, downloads, 
and deletions, as well as to check file existence remotely. The module relies on pysftp for SFTP operations and 
os_helper for auxiliary tasks.

Authors:
- [Warith Harchaoui](https://harchaoui.org/warith)
- [Mohamed Chelali](https://mchelali.github.io)
- [Bachir Zerroug](https://www.linkedin.com/in/bachirzerroug)
"""

__all__ = [
    'credentials',
    'get_client_sftp',
    'strip_sftp_path',
    'remote_file_exists',
    'delete',
    'upload',
    'download',
    'remote_dir_exist',
    'make_remote_directory',
]

from .main import (
    credentials,
    get_client_sftp,
    strip_sftp_path,
    remote_file_exists,
    delete,
    upload,
    download,
    remote_dir_exist,
    make_remote_directory,
)

