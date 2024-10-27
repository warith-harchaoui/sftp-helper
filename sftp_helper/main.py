"""
SFTP Helper

This module provides functions to interact with an SFTP server, allowing users to perform file uploads, downloads, 
and deletions, as well as to check file existence remotely. The module relies on pysftp for SFTP operations and 
os_helper for auxiliary tasks.

Authors:
- [Warith Harchaoui](https://harchaoui.org/warith)
- [Mohamed Chelali](https://mchelali.github.io)
- [Bachir Zerroug](https://www.linkedin.com/in/bachirzerroug)

Dependencies:
- pysftp: Python SFTP client, https://pypi.org/project/pysftp/
- os_helper: Custom helper functions for file and system operations
"""

import pysftp
import os_helper


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
    return os_helper.get_config(keys, "SFTP", config_path)


def get_client_sftp(cred: dict):
    """
    Establish an SFTP connection using the provided credentials.

    This function wraps the pysftp Connection in a 'with' statement for safe usage.
    It disables host key checking for simplicity, assuming trusted connections.

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
    ...     sftp.put('local_file.txt', 'remote_file.txt')
    ...     sftp.get('remote_file.txt', 'local_copy.txt')

    Raises
    ------
    SystemExit
        If the SFTP connection fails.
    """
    try:
        cnopts = pysftp.CnOpts()
        cnopts.hostkeys = None  # Disable host key checking for simplicity
        client = pysftp.Connection(
            cred["sftp_host"], username=cred["sftp_login"], cnopts=cnopts, password=cred["sftp_passwd"]
        )
        return client
    except Exception as err:
        os_helper.error(f"Failed to establish SFTP connection:\n{sftp://{cred['sftp_login']}@{cred['sftp_host']}}\nError: {str(err)}")

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
    a = sftp_address.replace('sftp://', '').replace(cred["sftp_host"], '')
    if not(a.startswith("/")):
        a = "/" + a
    return a


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
            os_helper.info(f"SFTP file {sftp_address} existence check: {'True' if exists else 'False'}")
            return exists
    except Exception as err:
        os_helper.error(f"Failed to check SFTP file existence for :\n\t{sftp_address}.\nError:\n\t{str(err)}")
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
        osh.check(remote_dir_exist(ftp_directory, cred), f"Remote directory creation failed:\n\t{ftp_directory}\n\t(stopped at {current_path})")
    else:
        osh.info(f"Directory already exists: {ftp_directory}")


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
        os_helper.info(f"SFTP remote file {remote_path} does not exist, skipping deletion.")
        return True

    try:
        with get_client_sftp(cred) as sftp:
            sftp.remove(remote_path)
            os_helper.check(
                not remote_file_exists(sftp_address, cred),
                msg=f"Failed to delete {sftp_address} on SFTP server."
            )
            os_helper.info(f"SFTP file {sftp_address} successfully deleted.")
            return True
    except Exception as err:
        os_helper.error(f"Error deleting SFTP file:\n\t{sftp_address}.\nError:\n\t{str(err)}")
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
    if os_helper.emptystring(sftp_address):
        _, _, ext = os_helper.folder_name_ext(local_path)
        h = os_helper.hashfile(local_path, hash_content=True, date=True)
        sftp_address = f"{cred['sftp_destination_path']}/{h}.{ext}"

    delete(sftp_address, cred)

    remote_path = strip_sftp_path(sftp_address, cred)
    try:
        with get_client_sftp(cred) as sftp:
            sftp.put(local_path, remote_path, preserve_mtime=True, confirm=True)
            os_helper.check(remote_file_exists(sftp_address, cred), msg=f"Upload failed for {sftp_address}")
            os_helper.info(f"Upload successful: {local_path} -> {sftp_address}")
            return sftp_address
    except Exception as err:
        os_helper.error(f"Upload failed:\n\t{local_path}\n\t->{sftp_address}.\nError:\n\t{str(err)}")


def download(sftp_address: str, cred: dict, local_path: str = "") -> str:
    """
    Download a file from the remote SFTP server to a local path.

    If no local path is provided, the filename will be based on the remote file's basename.

    Parameters
    ----------
    sftp_address : str
        The full SFTP path to the remote file.
    cred : dict
        SFTP credentials dictionary.
    local_path : str, optional
        The local destination path. If not provided, defaults to the remote file's basename.

    Returns
    -------
    str
        The local path if download is successful. None otherwise.

    Example
    -------
    >>> download('sftp://example.com/folder/file.txt', cred, 'local_file.txt')
    'local_file.txt'
    """
    remote_path = strip_sftp_path(sftp_address, cred)
    if os_helper.emptystring(local_path):
        local_path = os.path.basename(remote_path)

    try:
        with get_client_sftp(cred) as sftp:
            sftp.get(remote_path, local_path, preserve_mtime=True)
        os_helper.checkfile(local_path, msg=f"Download failed for {sftp_address}")
        os_helper.info(f"Download successful: {sftp_address} -> {local_path}")
        return local_path
    except (IOError, OSError) as err:
        os_helper.error(f"Download failed: {sftp_address} -> {local_path}. Error: {str(err)}")
