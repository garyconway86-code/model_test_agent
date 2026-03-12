"""Execute commands inside a Docker container and capture output.

This tool wraps ``subprocess`` to run Docker commands for fix verification.
It is intentionally stateless — the caller decides *what* to run; this tool
only handles *how* to run it safely.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class ExecutionResult:
    """Outcome of a Docker command execution."""

    command: str
    return_code: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.return_code == 0

    @property
    def output(self) -> str:
        """Combined stdout + stderr for easy logging."""
        parts = []
        if self.stdout.strip():
            parts.append(self.stdout.strip())
        if self.stderr.strip():
            parts.append(f"[stderr]\n{self.stderr.strip()}")
        return "\n".join(parts) if parts else "(no output)"


class DockerExecutor:
    """Run shell commands via ``subprocess``, optionally inside Docker.

    Parameters
    ----------
    docker_image : str | None
        If set, commands are wrapped with ``docker run``.
    timeout : int
        Max seconds per command.
    work_dir : str
        Working directory mapped into the container (``-v`` bind mount).
    """

    def __init__(
        self,
        docker_image: str | None = None,
        timeout: int = 300,
        work_dir: str = "/workspace",
    ) -> None:
        self.docker_image = docker_image
        self.timeout = timeout
        self.work_dir = work_dir

    def run(self, command: str) -> ExecutionResult:
        """Execute *command* and return structured result."""
        if self.docker_image:
            full_cmd = [
                "docker", "run", "--rm",
                "-v", f"{self.work_dir}:/workspace",
                "-w", "/workspace",
                self.docker_image,
                "bash", "-c", command,
            ]
        else:
            full_cmd = ["bash", "-c", command]

        try:
            proc = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            return ExecutionResult(
                command=command,
                return_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                command=command,
                return_code=-1,
                stdout="",
                stderr=f"Command timed out after {self.timeout}s",
            )
        except Exception as exc:
            return ExecutionResult(
                command=command,
                return_code=-2,
                stdout="",
                stderr=str(exc),
            )
