"""
SFTP Helper

This module provides functions to interact with an SFTP server, allowing users to perform file uploads, downloads, 
and deletions, as well as to check file existence remotely. The module relies on pysftp for SFTP operations and 
osh for auxiliary tasks.

Authors:
- [Warith Harchaoui](https://harchaoui.org/warith)
- [Mohamed Chelali](https://mchelali.github.io)
- [Bachir Zerroug](https://www.linkedin.com/in/bachirzerroug)

Dependencies:
- pysftp: Python SFTP client, https://pypi.org/project/pysftp/
- osh: Custom helper functions for file and system operations
"""

import pysftp
import os_helper as osh
from contextlib import contextmanager
import logging


def credentials(config_path: str=None) -> dict:
    """
    Retrieve SFTP credentials from a configuration file or folder.

    This function loads SFTP credentials from a given config path (file or folder). 
    It expects certain mandatory keys in the configuration file.

    Parameters
    ----------
    config_path : str
        The file or folder path containing the SFTP configuration.

    Returns
    -------
    dict
        A dictionary containing SFTP credentials.

    Raises
    ------
    SystemExit
        If the configuration file does not contain the required keys (or not present in capitals in the environment variables).
    """
    keys = ['sftp_host', 'sftp_login', 'sftp_passwd', 'sftp_destination_path', 'sftp_https']
    return osh.get_config(keys, "SFTP", config_path)


@contextmanager
def get_client_sftp(cred: dict):
    """
    Establish an SFTP connection using the provided credentials.

    This function wraps the pysftp Connection using a context manager
    to ensure the connection is safely closed after use.

    Parameters
    ----------
    cred : dict
        Dictionary containing SFTP credentials (host, login, password, etc.).

    Yields
    ------
    pysftp.Connection
        The SFTP client connection for use within the 'with' context.

    Example
    -------
    >>> with get_client_sftp(cred) as sftp:
    ...     sftp.put('local_file.txt', '/remote/path/file.txt')
    ...     sftp.get('/remote/path/file.txt', 'local_copy.txt')

    Raises
    ------
    SystemExit
        If the SFTP connection fails.
    """
    cnopts = pysftp.CnOpts()
    cnopts.hostkeys = None  # Disable host key checking for simplicity

    try:
        with pysftp.Connection(
            cred["sftp_host"], username=cred["sftp_login"],
            cnopts=cnopts, password=cred["sftp_passwd"]
        ) as client:
            yield client  # Yield the connection for use within a 'with' context
    except Exception as err:
        raise Exception(f"Failed to establish SFTP connection:\n{sftp://{cred['sftp_login']}@{cred['sftp_host']}}\nError: {str(err)}")

def normalize_path(path: str) -> str:
    """
    Normalize a given path, ensuring it starts with a '/' and has no trailing slashes.

    Parameters
    ----------
    path : str
        The path to normalize.

    Returns
    -------
    str
        The normalized path.
    """
    # Ensure path starts with a single '/'
    if not path.startswith('/'):
        path = '/' + path

    # Remove any trailing slashes
    return path.rstrip('/')


def strip_sftp_path(sftp_address: str, cred: dict) -> str:
    """
    Remove the SFTP protocol and host from an SFTP address.

    This function strips the 'sftp://' prefix and the host from the full SFTP path, 
    returning the relative path on the remote server.

    Parameters
    ----------
    sftp_address : str
        The full SFTP path (e.g., sftp://host/path/to/file).
    cred : dict
        SFTP credentials dictionary.

    Returns
    -------
    str
        The stripped SFTP path (e.g., /path/to/file).

    Example
    -------
    >>> strip_sftp_path('sftp://example.com/folder/file.txt', cred)
    '/folder/file.txt'
    """
    stripped_path = sftp_address.replace('sftp://', '').replace(cred["sftp_host"], '')
    return normalize_path(stripped_path)


def remote_file_exists(sftp_address: str, cred: dict) -> bool:
    """
    Check if a remote file exists on the SFTP server.

    Parameters
    ----------
    sftp_address : str
        The full SFTP path to the file.
    cred : dict
        SFTP credentials dictionary.

    Returns
    -------
    bool
        True if the remote file exists, False otherwise.

    Example
    -------
    >>> remote_file_exists('sftp://example.com/folder/file.txt', cred)
    True
    """
    remote_path = strip_sftp_path(sftp_address, cred)
    try:
        with get_client_sftp(cred) as sftp:
            exists = sftp.exists(remote_path)
            logging.info(f"SFTP file {sftp_address} existence check: {'True' if exists else 'False'}")
            return exists
    except Exception as err:
        raise Exception(f"Failed to check SFTP file existence for {sftp_address}.\nError: {str(err)}")
    return False


def remote_dir_exist(ftp_dir: str, cred: dict) -> bool:
    """
    Check if the specified remote directory exists.

    Parameters
    ----------
    ftp_dir : str
        The remote directory path to check.
    cred : dict
        Dictionary containing SFTP credentials.

    Returns
    -------
    bool
        True if the directory exists, False otherwise.
    """
    with get_client_sftp(cred) as sftp:
        try:
            sftp.cwd(ftp_dir)  # Try to change to the directory
            return True
        except IOError:
            return False

def make_remote_directory(ftp_directory: str, cred: dict):
    """
    Ensure the specified remote directory exists, creating it if necessary.

    Parameters
    ----------
    ftp_directory : str
        The full remote directory path to ensure.
    cred : dict
        Dictionary containing SFTP credentials.
    """
    if not remote_dir_exist(ftp_directory, cred):
        ftp_directories = [f for f in ftp_directory.split("/") if f]  # Split and clean up path
        with get_client_sftp(cred) as sftp:
            # Create each directory level if it does not exist
            for i in range(len(ftp_directories)):
                current_path = "/" + "/".join(ftp_directories[:i + 1])
                try:
                    sftp.cwd(current_path)  # Check if directory exists
                except IOError:
                    sftp.mkdir(current_path)  # Create directory if it doesn’t exist

        # Final verification step
        assert remote_dir_exist(ftp_directory, cred), f"Remote directory creation failed:\n\t{ftp_directory}\n\t(stopped at {current_path})"
    else:
        logging.info(f"Directory already exists: {ftp_directory}")


def delete(sftp_address: str, cred: dict) -> bool:
    """
    Delete a file from the remote SFTP server.

    Parameters
    ----------
    sftp_address : str
        The full SFTP path to the file.
    cred : dict
        SFTP credentials dictionary.

    Returns
    -------
    bool
        True if the file was successfully deleted or didn't exist. False otherwise.

    Example
    -------
    >>> delete('sftp://example.com/folder/file.txt', cred)
    True
    """
    remote_path = strip_sftp_path(sftp_address, cred)
    
    if not(remote_file_exists(remote_path, cred)):
        logging.info(f"SFTP remote file {remote_path} does not exist, skipping deletion.")
        return True

    try:
        with get_client_sftp(cred) as sftp:
            sftp.remove(remote_path)
            assert not remote_file_exists(sftp_address, cred), f"Failed to delete {sftp_address} on SFTP server."
            logging.info(f"SFTP file {sftp_address} successfully deleted.")
            return True
    except Exception as err:
        raise Exception(f"Failed to delete SFTP file:\n\t{sftp_address}.\nError:\n\t{str(err)}")
    return False


def upload(local_path: str, cred: dict, sftp_address: str = "") -> str:
    """
    Upload a local file to the remote SFTP server.

    If no destination path is provided, a random filename based on the file's hash will be used.

    Parameters
    ----------
    local_path : str
        Path to the local file.
    cred : dict
        SFTP credentials dictionary.
    sftp_address : str, optional
        Remote SFTP destination path. If not provided, a random path is generated.

    Returns
    -------
    str
        The remote path if upload is successful. None otherwise.

    Example
    -------
    >>> upload('local_file.txt', cred, 'sftp://example.com/folder/file.txt')
    'sftp://example.com/folder/file.txt'
    """
    if osh.emptystring(sftp_address):
        _, _, ext = osh.folder_name_ext(local_path)
        h = osh.hashfile(local_path, hash_content=True, date=True)
        sftp_address = f"{cred['sftp_destination_path']}/{h}.{ext}"

    delete(sftp_address, cred)

    remote_path = strip_sftp_path(sftp_address, cred)
    try:
        with get_client_sftp(cred) as sftp:
            sftp.put(local_path, remote_path, preserve_mtime=True, confirm=True)
            assert remote_file_exists(sftp_address, cred), f"Upload failed for {sftp_address}"
            logging.info(f"Upload successful: {local_path} -> {sftp_address}")
            return sftp_address
    except Exception as err:
        raise Exception(f"Upload failed:\n\t{local_path}\n\t->{sftp_address}.\nError:\n\t{str(err)}")


def download(sftp_address: str, cred: dict, local_path: str = "") -> str:
    """
    Download a file from the remote SFTP server to a local path.

    If no local path is provided, the filename will be based on the remote file's basename.

    Parameters
    ----------
    sftp_address : str"""
    remote_path = strip_sftp_path(sftp_address, cred)
    if osh.emptystring(local_path):
        local_path = remote_path.split('/')[-1]

    try:
        with get_client_sftp(cred) as sftp:
            sftp.get(remote_path, local_path, preserve_mtime=True)
            osh.checkfile(local_path, msg=f"Download failed for {sftp_address}")
            logging.info(f"Download successful: {sftp_address} -> {local_path}")
            return local_path
    except Exception as err:
        raise Exception(f"Download failed:\n\t{sftp_address}\n\t->{local_path}.\nError:\n\t{str(err)}")
