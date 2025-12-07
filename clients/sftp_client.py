from __future__ import annotations

import logging
import posixpath
from typing import Optional

import paramiko

from utils.settings import SftpUploadConfig

logger = logging.getLogger(__name__)


class SftpClient:
    """Small helper to upload files over SFTP."""

    def __init__(self, config: SftpUploadConfig) -> None:
        self._config = config
        self._ssh_client: Optional[paramiko.SSHClient] = None
        self._sftp: Optional[paramiko.SFTPClient] = None

    def __enter__(self) -> "SftpClient":
        self._connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _connect(self) -> None:
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        client.connect(
            hostname=self._config.host,
            port=self._config.port,
            username=self._config.username,
            password=self._config.password,
            key_filename=str(self._config.key_file) if self._config.key_file else None,
            timeout=self._config.timeout,
            look_for_keys=False,
        )
        self._ssh_client = client
        self._sftp = client.open_sftp()

    def close(self) -> None:
        if self._sftp is not None:
            try:
                self._sftp.close()
            except Exception:  # pragma: no cover - defensive
                logger.debug("Failed to close SFTP client", exc_info=True)
            self._sftp = None

        if self._ssh_client is not None:
            try:
                self._ssh_client.close()
            except Exception:  # pragma: no cover - defensive
                logger.debug("Failed to close SSH client", exc_info=True)
            self._ssh_client = None

    def _ensure_remote_dir(self, remote_dir: str) -> None:
        """Create remote directories if missing."""
        if not remote_dir or remote_dir == "/":
            return

        assert self._sftp is not None
        parts = [part for part in remote_dir.split("/") if part]
        current = ""
        for part in parts:
            current = f"{current}/{part}"
            try:
                self._sftp.stat(current)
            except IOError:
                self._sftp.mkdir(current)

    def upload_bytes(self, payload: bytes, remote_dir: str, filename: str) -> str:
        """Upload bytes to the remote SFTP server and return the remote path."""
        if self._sftp is None:
            raise RuntimeError("SFTP connection not established")

        self._ensure_remote_dir(remote_dir)
        remote_path = filename if not remote_dir or remote_dir == "/" else posixpath.join(remote_dir, filename)

        with self._sftp.file(remote_path, "wb") as remote_file:
            remote_file.write(payload)
        return remote_path
