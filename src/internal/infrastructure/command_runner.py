"""Subprocess execution utilities."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional


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


class CommandCancelledError(RuntimeError):
    """Raised when a command is stopped because the build was canceled."""

    def __init__(self, command: List[str]) -> None:
        self.command = command
        super().__init__(f"Command cancelled: {' '.join(command)}")


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
            env=env,
            cwd=cwd,
            start_new_session=True,
        )

    def wait(self, process: subprocess.Popen) -> int:
        return process.wait()

    def terminate(self, process: subprocess.Popen, *, kill_after_seconds: float = 5.0) -> None:
        if process.poll() is not None:
            return

        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return

        deadline = time.time() + kill_after_seconds
        while process.poll() is None and time.time() < deadline:
            time.sleep(0.1)

        if process.poll() is not None:
            return

        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return

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
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> CompletedCommand:
        process = self.start(
            command,
            env=env,
            cwd=cwd,
        )
        stdout = ""
        while True:
            if should_stop and should_stop():
                self.terminate(process)
                try:
                    stdout, _ = process.communicate(timeout=1)
                except subprocess.TimeoutExpired:
                    stdout = ""
                raise CommandCancelledError(command)
            try:
                stdout, _ = process.communicate(timeout=0.5)
                break
            except subprocess.TimeoutExpired:
                continue
        result = CompletedCommand(
            args=command,
            returncode=process.returncode,
            stdout=stdout or "",
        )
        if check and process.returncode != 0:
            raise CommandExecutionError(command, process.returncode, result.stdout)
        return result

    def run_checked(
        self,
        command: List[str],
        *,
        env: Dict[str, str],
        cwd: str,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> CompletedCommand:
        return self.run(command, env=env, cwd=cwd, check=True, should_stop=should_stop)
