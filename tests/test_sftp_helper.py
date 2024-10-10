import pytest
from unittest.mock import patch, MagicMock
import os_helper as osh
from sftp_helper import (
    credentials,
    get_client_sftp,
    strip_sftp_path,
    remote_file_exists,
    delete,
    upload,
    download
)

mock_cred = credentials("sftp_config.json")

# # Example SFTP credentials for tests
# mock_cred = {
#     "sftp_host": "test_host",
#     "sftp_login": "test_user",
#     "sftp_passwd": "test_passwd",
#     "sftp_destination_path": "/remote_path",
#     "sftp_https": "https://sftp.example.com"
# }

def test_strip_sftp_path():
    sftp_address = "sftp://test_host/folder/file.txt"
    result = strip_sftp_path(sftp_address, mock_cred)
    assert result == "/folder/file.txt"

@patch("pysftp.Connection")
def test_get_client_sftp(mock_sftp_conn):
    # Mock the SFTP connection and ensure it returns successfully
    mock_sftp_conn.return_value = MagicMock()
    with get_client_sftp(mock_cred) as client:
        assert client is not None
        mock_sftp_conn.assert_called_once_with(
            mock_cred["sftp_host"],
            username=mock_cred["sftp_login"],
            cnopts=MagicMock(),
            password=mock_cred["sftp_passwd"]
        )

@patch("pysftp.Connection")
def test_remote_file_exists(mock_sftp_conn):
    mock_sftp_instance = mock_sftp_conn.return_value.__enter__.return_value
    mock_sftp_instance.exists.return_value = True

    sftp_address = "sftp://test_host/folder/file.txt"
    result = remote_file_exists(sftp_address, mock_cred)
    
    assert result == True
    mock_sftp_instance.exists.assert_called_once_with("/folder/file.txt")

@patch("pysftp.Connection")
def test_delete(mock_sftp_conn):
    mock_sftp_instance = mock_sftp_conn.return_value.__enter__.return_value
    mock_sftp_instance.exists.return_value = True
    mock_sftp_instance.remove.return_value = None  # Simulate successful deletion

    sftp_address = "sftp://test_host/folder/file.txt"
    result = delete(sftp_address, mock_cred)

    assert result == True
    mock_sftp_instance.remove.assert_called_once_with("/folder/file.txt")

@patch("pysftp.Connection")
def test_upload(mock_sftp_conn):
    mock_sftp_instance = mock_sftp_conn.return_value.__enter__.return_value

    # Mock file upload behavior
    mock_sftp_instance.put.return_value = None
    mock_sftp_instance.exists.return_value = True

    local_path = "local_file.txt"
    sftp_address = "sftp://test_host/folder/file.txt"
    result = upload(local_path, mock_cred, sftp_address)

    assert result == "/remote_path/tt.txt"  # Assuming that strip_sftp_path was successful
    mock_sftp_instance.put.assert_called_once_with(local_path, "/folder/file.txt", preserve_mtime=True, confirm=True)

@patch("pysftp.Connection")
def test_download(mock_sftp_conn):
    mock_sftp_instance = mock_sftp_conn.return_value.__enter__.return_value

    # Mock download behavior
    mock_sftp_instance.get.return_value = None

    sftp_address = "sftp://test_host/folder/file.txt"
    local_path = "downloaded_file.txt"
    result = download(sftp_address, mock_cred, local_path)

    assert result == local_path
    mock_sftp_instance.get.assert_called_once_with("/folder/file.txt", local_path, preserve_mtime=True)

