"""
SFTP Helper

This module provides various helper functions to interact with an SFTP server.
It includes functionality for uploading, downloading, deleting, and verifying the existence of remote files via SFTP.

Authors:
- Warith Harchaoui <warith.harchaoui@deraison.ai>
"""

from .main import (
    credentials,
    get_client_sftp,
    strip_sftp_path,
    remote_file_exists,
    delete,
    upload,
    download
)

