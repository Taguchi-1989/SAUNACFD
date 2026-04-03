"""Tests for WSL2 utility module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from utils.wsl import (
    OpenFOAMError,
    check_openfoam_available,
    win_to_wsl_path,
    wsl_exec,
    wsl_to_win_path,
)


class TestWinToWslPath:
    def test_d_drive(self) -> None:
        result = win_to_wsl_path(Path("D:/dev/SaunaFEM"))
        assert result == "/mnt/d/dev/SaunaFEM"

    def test_c_drive(self) -> None:
        result = win_to_wsl_path(Path("C:/Users/test"))
        assert result == "/mnt/c/Users/test"

    def test_backslash_path(self) -> None:
        result = win_to_wsl_path(Path("D:\\dev\\SaunaFEM\\results"))
        assert result == "/mnt/d/dev/SaunaFEM/results"

    def test_deep_nested_path(self) -> None:
        result = win_to_wsl_path(Path("D:/a/b/c/d/e"))
        assert result == "/mnt/d/a/b/c/d/e"


class TestWslToWinPath:
    def test_basic(self) -> None:
        result = wsl_to_win_path("/mnt/d/dev/SaunaFEM")
        assert result == Path("D:/dev/SaunaFEM")

    def test_c_drive(self) -> None:
        result = wsl_to_win_path("/mnt/c/Users/test")
        assert result == Path("C:/Users/test")

    def test_not_mnt_raises(self) -> None:
        with pytest.raises(ValueError, match="Not a /mnt/ path"):
            wsl_to_win_path("/home/user/project")

    def test_roundtrip(self) -> None:
        original = Path("D:/dev/SaunaFEM/results/case1")
        wsl = win_to_wsl_path(original)
        back = wsl_to_win_path(wsl)
        assert back == original


class TestWslExec:
    @patch("utils.wsl.subprocess.run")
    def test_success(self, mock_run) -> None:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "OK"
        mock_run.return_value.stderr = ""

        result = wsl_exec("echo OK")
        assert result.stdout == "OK"
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["wsl", "-e", "bash", "-lc", "echo OK"]

    @patch("utils.wsl.subprocess.run")
    def test_with_cwd(self, mock_run) -> None:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = ""

        wsl_exec("ls", cwd=Path("D:/dev/SaunaFEM"))
        call_args = mock_run.call_args[0][0]
        assert "cd '/mnt/d/dev/SaunaFEM' && ls" in call_args[-1]

    @patch("utils.wsl.subprocess.run")
    def test_failure_raises(self, mock_run) -> None:
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = "error"

        with pytest.raises(OpenFOAMError, match="Command failed"):
            wsl_exec("bad_command")


class TestCheckOpenfoam:
    @patch("utils.wsl.subprocess.run")
    def test_available(self, mock_run) -> None:
        mock_run.return_value.returncode = 0
        assert check_openfoam_available() is True

    @patch("utils.wsl.subprocess.run")
    def test_not_available(self, mock_run) -> None:
        mock_run.return_value.returncode = 1
        assert check_openfoam_available() is False

    @patch("utils.wsl.subprocess.run", side_effect=FileNotFoundError)
    def test_wsl_not_installed(self, mock_run) -> None:
        assert check_openfoam_available() is False
