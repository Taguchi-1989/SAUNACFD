"""Tests for mesh_runner module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from harness.mesh_runner import parse_check_mesh, run_mesh

SAMPLE_CHECKMESH_OUTPUT = """
Checking geometry...
    Overall domain bounding box (-0.5 -0.5 -0.5) (0.5 0.5 0.5)
    Mesh has 3 geometric (non-empty/wedge) directions (1 1 1)
    Mesh has 3 solution (non-empty) directions (1 1 1)
    All edges aligned with or perpendicular to non-empty directions.
    Boundary openness (3.46945e-18 0 0) OK.
    Max cell openness = 2.22045e-16 OK.
    Max aspect ratio = 1 OK.
    Minimum face area = 0.000694444. Maximum face area = 0.000694444.
    Min volume = 1.15741e-05. Max volume = 1.15741e-05. Total volume = 1.
    Mesh non-orthogonality Max: 0 average: 0
    Max skewness = 4.44089e-16 OK.
    Min/max edge length = 0.0208333 0.0208333 OK.
    Min determinant = 1 OK.
    Min face weight = 0.5 OK.
    Min vol ratio = 1 OK.

    Number of cells = 110592
    Overall number of points = 117649
    Number of faces = 330624
    Number of internal faces = 318816
    Number of cells by type:
        hexahedra:  110592

Mesh OK.
"""


class TestParseCheckMesh:
    def test_cell_count(self) -> None:
        # Use a simpler format that matches the regex
        output = "    cells:           9600\n" + SAMPLE_CHECKMESH_OUTPUT
        count, _ = parse_check_mesh(output)
        assert count == 9600

    def test_quality_metrics(self) -> None:
        count, quality = parse_check_mesh(SAMPLE_CHECKMESH_OUTPUT)
        assert count == 110592
        assert quality["max_aspect_ratio"] == 1.0
        assert quality["max_non_orthogonality"] == 0.0

    def test_empty_output(self) -> None:
        count, quality = parse_check_mesh("")
        assert count == 0
        assert quality == {}


class TestRunMesh:
    @patch("harness.mesh_runner.wsl_exec")
    def test_success(self, mock_wsl) -> None:
        mock_wsl.return_value = MagicMock(
            stdout="cells:           9600\n" + SAMPLE_CHECKMESH_OUTPUT,
            returncode=0,
        )
        result = run_mesh(Path("D:/fake/case"))
        assert result.success is True
        assert mock_wsl.call_count == 2  # blockMesh + checkMesh

    @patch("harness.mesh_runner.wsl_exec")
    def test_no_check(self, mock_wsl) -> None:
        mock_wsl.return_value = MagicMock(stdout="", returncode=0)
        result = run_mesh(Path("D:/fake/case"), check=False)
        assert result.success is True
        assert mock_wsl.call_count == 1  # only blockMesh
