"""Subprocess execution utilities."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class CompletedCommand:
    """Normalized completed command result."""

    args: List[str]
    returncode: int
    stdout: str


class CommandExecutionError(RuntimeError):
    """Raised when a checked command exits unsuccessfully."""

    def __init__(self, command: List[str], returncode: int, output: str) -> None:
        self.command = command
        self.returncode = returncode
        self.output = output
        summary = f"Command failed with exit code {returncode}: {' '.join(command)}"
        if output.strip():
            summary = f"{summary}\n{output.strip()}"
        super().__init__(summary)


class CommandRunner:
    """Execute commands with a consistent subprocess configuration."""

    def start(
        self,
        command: List[str],
        *,
        env: Dict[str, str],
        cwd: str,
        line_buffered: bool = False,
    ) -> subprocess.Popen:
        return subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1 if line_buffered else -1,
            universal_newlines=line_buffered,
            env=env,
            cwd=cwd,
        )

    def wait(self, process: subprocess.Popen) -> int:
        return process.wait()

    def iter_lines(self, process: subprocess.Popen):
        if process.stdout is None:
            return
        for line in process.stdout:
            yield line.rstrip()

    def run(
        self,
        command: List[str],
        *,
        env: Dict[str, str],
        cwd: str,
        check: bool = True,
    ) -> CompletedCommand:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            cwd=cwd,
            check=False,
        )
        result = CompletedCommand(
            args=command,
            returncode=completed.returncode,
            stdout=completed.stdout or "",
        )
        if check and completed.returncode != 0:
            raise CommandExecutionError(command, completed.returncode, result.stdout)
        return result

    def run_checked(
        self,
        command: List[str],
        *,
        env: Dict[str, str],
        cwd: str,
    ) -> CompletedCommand:
        return self.run(command, env=env, cwd=cwd, check=True)
