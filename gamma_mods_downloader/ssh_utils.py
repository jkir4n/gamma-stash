"""
SSH/SCP utilities for the Gamma Mods Downloader.

Provides remote command execution and file transfer over SSH.
Used when the destination is a remote machine (e.g., a Windows gaming PC).
"""

import os
import subprocess
from typing import Optional, Tuple


class SSHClient:
    """Lightweight SSH/SCP client using the system's ssh/scp binaries."""

    def __init__(
        self,
        host: str,
        user: str,
        port: int = 22,
        key_file: Optional[str] = None,
        timeout: int = 15,
    ):
        self.host = host
        self.user = user
        self.port = port
        self.key_file = key_file
        self.timeout = timeout

    @property
    def _base_args(self) -> list[str]:
        args = [
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
            "-o", "BatchMode=yes",
            "-p", str(self.port),
        ]
        if self.key_file and os.path.exists(self.key_file):
            args.extend(["-i", self.key_file])
        return args

    @property
    def _host_spec(self) -> str:
        return f"{self.user}@{self.host}"

    def run(self, command: str, timeout: Optional[int] = None) -> Tuple[str, str, int]:
        """Run a command on the remote host. Returns (stdout, stderr, returncode)."""
        cmd = ["ssh", *self._base_args, self._host_spec, command]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout or self.timeout,
            )
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired as e:
            return "", f"SSH timeout after {timeout or self.timeout}s", 1
        except FileNotFoundError:
            return "", "ssh binary not found. Install OpenSSH client.", 1

    def copy_to(self, local_path: str, remote_path: str, timeout: int = 60) -> bool:
        """Copy a local file to the remote host via SCP."""
        cmd = [
            "scp",
            *self._base_args,
            local_path,
            f"{self._host_spec}:{remote_path}",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def copy_from(self, remote_path: str, local_path: str, timeout: int = 60) -> bool:
        """Copy a file from the remote host to local via SCP."""
        cmd = [
            "scp",
            *self._base_args,
            f"{self._host_spec}:{remote_path}",
            local_path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def file_exists(self, remote_path: str) -> bool:
        """Check if a file exists on the remote host."""
        stdout, _, rc = self.run(
            f'if exist "{remote_path}" (echo YES) else (echo NO)',
            timeout=10,
        )
        return "YES" in stdout

    def read_file(self, remote_path: str) -> Optional[str]:
        """Read a remote file's content (Windows)."""
        stdout, stderr, rc = self.run(f'type "{remote_path}"', timeout=15)
        if rc != 0:
            return None
        return stdout

    def write_file(self, content: str, remote_path: str) -> bool:
        """Write content to a remote file via temp file + SCP."""
        tmp = os.path.join("/tmp", f"_gmd_remote_{os.getpid()}.txt")
        try:
            with open(tmp, "w", newline="\r\n") as f:
                f.write(content)
            return self.copy_to(tmp, remote_path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
