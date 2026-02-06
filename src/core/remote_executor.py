"""
RemoteExecutor - Sends action commands to Windows VM via SSH.

This module runs on the Linux container (LXC 140) and communicates
with the ActionExecutor running on the Windows VM.
"""

import json
import logging
import subprocess
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result from executing an action on Windows."""
    success: bool
    action_type: str
    output: str = ""
    error: str = ""
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "action_type": self.action_type,
            "output": self.output,
            "error": self.error,
            "duration_ms": self.duration_ms
        }


class RemoteExecutor:
    """
    Executes actions on a remote Windows VM via SSH.

    The Windows VM must have:
    - OpenSSH server enabled
    - Python installed with ActionExecutor module
    - SSH key authentication configured
    """

    def __init__(
        self,
        windows_host: str,
        windows_user: str = "analyst",
        ssh_port: int = 22,
        ssh_key_path: Optional[str] = None,
        python_path: str = "python",
        executor_path: str = "C:\\sedt\\action_executor.py"
    ):
        """
        Initialize the remote executor.

        Args:
            windows_host: IP or hostname of Windows VM
            windows_user: SSH username
            ssh_port: SSH port (default 22)
            ssh_key_path: Path to SSH private key (optional)
            python_path: Path to Python on Windows
            executor_path: Path to action_executor.py on Windows
        """
        self.windows_host = windows_host
        self.windows_user = windows_user
        self.ssh_port = ssh_port
        self.ssh_key_path = ssh_key_path
        self.python_path = python_path
        self.executor_path = executor_path

        self._validate_connection()

    def _validate_connection(self):
        """Test SSH connection to Windows VM."""
        try:
            result = self._run_ssh_command("echo connected")
            if "connected" in result:
                logger.info(f"SSH connection to {self.windows_host} validated")
            else:
                logger.warning(f"SSH connection test returned unexpected: {result}")
        except Exception as e:
            logger.error(f"SSH connection failed: {e}")
            raise ConnectionError(f"Cannot connect to Windows VM: {e}")

    def _build_ssh_command(self, remote_command: str) -> list:
        """Build SSH command with proper arguments."""
        cmd = ["ssh"]

        # Add SSH key if specified
        if self.ssh_key_path:
            cmd.extend(["-i", self.ssh_key_path])

        # Add port if non-standard
        if self.ssh_port != 22:
            cmd.extend(["-p", str(self.ssh_port)])

        # Disable host key checking for lab environment
        cmd.extend([
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "LogLevel=ERROR"
        ])

        # Add user@host
        cmd.append(f"{self.windows_user}@{self.windows_host}")

        # Add the remote command
        cmd.append(remote_command)

        return cmd

    def _run_ssh_command(self, remote_command: str, timeout: int = 30) -> str:
        """Execute a command on the Windows VM via SSH."""
        cmd = self._build_ssh_command(remote_command)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            if result.returncode != 0:
                raise RuntimeError(f"SSH command failed: {result.stderr}")

            return result.stdout.strip()

        except subprocess.TimeoutExpired:
            raise TimeoutError(f"SSH command timed out after {timeout}s")

    def execute(self, action_type: str, target: str, parameters: dict) -> ExecutionResult:
        """
        Execute an action on the Windows VM.

        Args:
            action_type: Type of action (e.g., "open_application", "browse_web")
            target: Target of action (e.g., "chrome", "linkedin.com")
            parameters: Additional parameters for the action

        Returns:
            ExecutionResult with success status and details
        """
        # Build the action payload
        payload = {
            "action_type": action_type,
            "target": target,
            "parameters": parameters
        }

        # Escape the JSON for PowerShell
        payload_json = json.dumps(payload).replace('"', '\\"')

        # Build the remote command to invoke ActionExecutor
        remote_cmd = (
            f'{self.python_path} {self.executor_path} '
            f'--action "{payload_json}"'
        )

        try:
            output = self._run_ssh_command(remote_cmd, timeout=60)

            # Parse the JSON response from ActionExecutor
            try:
                response = json.loads(output)
                return ExecutionResult(
                    success=response.get("success", False),
                    action_type=action_type,
                    output=response.get("output", ""),
                    error=response.get("error", ""),
                    duration_ms=response.get("duration_ms", 0)
                )
            except json.JSONDecodeError:
                # If not JSON, treat raw output as success
                return ExecutionResult(
                    success=True,
                    action_type=action_type,
                    output=output
                )

        except TimeoutError as e:
            return ExecutionResult(
                success=False,
                action_type=action_type,
                error=str(e)
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                action_type=action_type,
                error=str(e)
            )

    def execute_powershell(self, script: str) -> ExecutionResult:
        """
        Execute a PowerShell script directly on the Windows VM.

        Useful for complex actions that don't fit the ActionExecutor model.

        Args:
            script: PowerShell script to execute

        Returns:
            ExecutionResult with output
        """
        # Escape for SSH
        escaped_script = script.replace('"', '\\"').replace("'", "''")

        remote_cmd = f'powershell -Command "{escaped_script}"'

        try:
            output = self._run_ssh_command(remote_cmd, timeout=60)
            return ExecutionResult(
                success=True,
                action_type="powershell",
                output=output
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                action_type="powershell",
                error=str(e)
            )

    def check_windows_ready(self) -> bool:
        """Check if Windows VM is ready to receive actions."""
        try:
            # Check if ActionExecutor exists
            result = self._run_ssh_command(
                f'if exist "{self.executor_path}" echo exists'
            )
            if "exists" not in result:
                logger.warning("ActionExecutor not found on Windows VM")
                return False

            # Check if Python is available
            result = self._run_ssh_command(f'{self.python_path} --version')
            if "Python" not in result:
                logger.warning("Python not found on Windows VM")
                return False

            return True

        except Exception as e:
            logger.error(f"Windows readiness check failed: {e}")
            return False
