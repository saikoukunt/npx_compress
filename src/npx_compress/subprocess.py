import os
import re
import subprocess
import sys
from pathlib import Path

OOM_PATTERN = re.compile(
    r"out of memory|cannot allocate|bad_alloc|MemoryError", re.IGNORECASE
)

SIGKILL_RETURNCODES = (-9, 137)


class BackendError(RuntimeError):
    """A backend command exited non-zero."""

    def __init__(self, command: list[str], returncode: int, stderr: str):
        super().__init__(f"`{command[0]}` failed with exit code {returncode}:\n{stderr}")
        self.command = command
        self.returncode = returncode
        self.stderr = stderr


def run_backend(command: list[str]) -> str:
    """Run a backend command, raising BackendError if it fails."""
    process = subprocess.Popen(
        command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )
    stderr = echo_stream(process.stderr)
    if process.wait() != 0:
        raise BackendError(command, process.returncode, stderr)

    return stderr


def echo_stream(stream) -> str:
    """Forward output as it arrives so progress bars animate, keeping a copy for errors."""
    chunks = []
    while chunk := os.read(stream.fileno(), 4096):
        text = chunk.decode(errors="replace")
        sys.stderr.write(text)
        sys.stderr.flush()
        chunks.append(text)

    return "".join(chunks)


def output_matches_file(
    command: list[str], path: Path, chunk_size: int = 1 << 20
) -> bool:
    """Compare a command's output against a file without staging a copy on disk."""
    process = subprocess.Popen(command, stdout=subprocess.PIPE)
    matched = True
    with open(path, "rb") as original:
        while matched:
            decoded = process.stdout.read(chunk_size)
            matched = decoded == original.read(chunk_size)
            if not decoded:
                break

    if not matched:
        process.kill()

    return matched and process.wait() == 0


def is_oom(error: BackendError) -> bool:
    """Did the backend run out of memory? Retrying the next file is pointless if so."""
    return error.returncode in SIGKILL_RETURNCODES or bool(
        OOM_PATTERN.search(error.stderr)
    )
