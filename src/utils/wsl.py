"""WSL2 execution wrapper and Windows/WSL path translation."""

from __future__ import annotations

import subprocess
from pathlib import Path, PurePosixPath


class OpenFOAMError(RuntimeError):
    """Raised when an OpenFOAM command fails."""


def win_to_wsl_path(win_path: Path) -> str:
    """Convert a Windows path to a WSL path.

    Example: D:\\dev\\SaunaFEM → /mnt/d/dev/SaunaFEM
    """
    resolved = Path(win_path).resolve()
    drive = resolved.drive  # e.g. "D:"
    if not drive:
        raise ValueError(f"Cannot convert path without drive letter: {win_path}")
    letter = drive[0].lower()
    remainder = resolved.as_posix()[len(drive):]  # strip "D:" prefix
    return f"/mnt/{letter}{remainder}"


def wsl_to_win_path(wsl_path: str) -> Path:
    """Convert a WSL /mnt/ path to a Windows path.

    Example: /mnt/d/dev/SaunaFEM → D:\\dev\\SaunaFEM
    """
    posix = PurePosixPath(wsl_path)
    parts = posix.parts  # ('/', 'mnt', 'd', 'dev', ...)
    if len(parts) < 3 or parts[1] != "mnt":
        raise ValueError(f"Not a /mnt/ path: {wsl_path}")
    drive_letter = parts[2].upper()
    remainder = "/".join(parts[3:])
    return Path(f"{drive_letter}:/{remainder}")


def wsl_exec(
    cmd: str,
    cwd: Path | None = None,
    timeout: int = 600,
) -> subprocess.CompletedProcess[str]:
    """Execute a command inside WSL2.

    Args:
        cmd: Shell command to run inside WSL.
        cwd: Windows path to use as working directory (auto-translated).
        timeout: Maximum execution time in seconds.

    Returns:
        CompletedProcess with stdout/stderr captured as text.

    Raises:
        OpenFOAMError: If the command exits with a non-zero code.
        subprocess.TimeoutExpired: If timeout is exceeded.
    """
    if cwd is not None:
        wsl_cwd = win_to_wsl_path(cwd)
        full_cmd = f"cd '{wsl_cwd}' && {cmd}"
    else:
        full_cmd = cmd

    result = subprocess.run(
        ["wsl", "-e", "bash", "-lc", full_cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        raise OpenFOAMError(
            f"Command failed (exit {result.returncode}): {cmd}\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
    return result


def check_openfoam_available() -> bool:
    """Check if OpenFOAM is available in WSL2."""
    try:
        result = subprocess.run(
            ["wsl", "-e", "bash", "-lc", "which blockMesh && which buoyantSimpleFoam"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False
