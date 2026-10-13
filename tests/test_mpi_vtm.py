import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cfdpost.models import AnalysisRequest
from cfdpost.workflow import prepare


class MpiVtmAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import vtk  # noqa: F401
            import numpy  # noqa: F401
            import matplotlib  # noqa: F401
            import mpi4py  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("VTK, NumPy, Matplotlib, and mpi4py are required for the MPI acceptance test")
        cls.mpiexec = shutil.which("mpiexec") or shutil.which("mpirun")
        if cls.mpiexec is None:
            raise unittest.SkipTest("mpiexec or mpirun is required for the MPI acceptance test")

    def _write_vtm(self, root: Path, name: str = "case", duplicate_second: bool = False,
                   pressure: float = 5, block_count: int = 2) -> Path:
        for index in range(block_count):
            x0, x1 = index, index + 1
            ghost_array = '<DataArray type="UInt8" Name="vtkGhostType" format="ascii">1</DataArray>' \
                if duplicate_second and index == 1 else ""
            (root / f"{name}-block{index}.vtu").write_text(
                '<VTKFile type="UnstructuredGrid" version="1.0" byte_order="LittleEndian">'
                '<UnstructuredGrid><Piece NumberOfPoints="4" NumberOfCells="1">'
                '<PointData Scalars="pressure"><DataArray type="Float32" Name="pressure" format="ascii">'
                f'{pressure} {pressure} {pressure} {pressure}</DataArray></PointData>'
                '<CellData Scalars="temperature"><DataArray type="Float32" Name="temperature" format="ascii">'
                f'12</DataArray>{ghost_array}</CellData>'
                '<Points><DataArray type="Float32" NumberOfComponents="3" format="ascii">'
                f'{x0} 0 0 {x1} 0 0 {(x0 + x1) / 2} 1 0 {(x0 + x1) / 2} 0 1'
                '</DataArray></Points><Cells>'
                '<DataArray type="Int64" Name="connectivity" format="ascii">0 1 2 3</DataArray>'
                '<DataArray type="Int64" Name="offsets" format="ascii">4</DataArray>'
                '<DataArray type="UInt8" Name="types" format="ascii">10</DataArray>'
                '</Cells></Piece></UnstructuredGrid></VTKFile>',
                encoding="utf-8",
            )
        source = root / f"{name}.vtm"
        data_sets = "".join(
            f'<DataSet index="{index}" file="{name}-block{index}.vtu"/>'
            for index in range(block_count)
        )
        source.write_text(
            '<VTKFile type="vtkMultiBlockDataSet" version="1.0" byte_order="LittleEndian">'
            f'<vtkMultiBlockDataSet>{data_sets}</vtkMultiBlockDataSet></VTKFile>',
            encoding="utf-8",
        )
        return source

    def _request(self, source: Path, output: Path, timed: bool = False) -> AnalysisRequest:
        time = {"time": 0} if timed else {}
        actions = [
            {"type": "line_plot", "field": "pressure", "association": "point",
             "start": [0.05, 0.05, 0.05], "end": [1.95, 0.05, 0.05], "resolution": 16, **time},
            {"type": "line_plot", "field": "temperature", "association": "cell",
             "start": [0.05, 0.05, 0.05], "end": [1.95, 0.05, 0.05], "resolution": 16, **time},
            {"type": "slice_contour", "field": "pressure", "origin": [0, 0, 0.3],
             "normal": [0, 0, 1], **time},
        ]
        if timed:
            actions.extend([
                {"type": "mean", "field": "pressure"},
                {"type": "rms", "field": "pressure"},
            ])
        return AnalysisRequest.from_dict({
            "input": str(source), "output": str(output), "approved": True,
            "actions": actions,
        })

    def _rows(self, path: Path) -> list[list[str]]:
        with path.open(newline="", encoding="utf-8") as stream:
            return list(csv.reader(stream))

    def test_vtm_reader_assigns_blocks_to_distinct_rank_requests(self):
        from cfdpost.kernel.reader import read_snapshot

        with tempfile.TemporaryDirectory() as directory:
            source = self._write_vtm(Path(directory))
            complete = read_snapshot(source, rank=0, size=1)
            first_rank = read_snapshot(source, rank=0, size=2)
            second_rank = read_snapshot(source, rank=1, size=2)
            self.assertEqual(len(complete), 2)
            self.assertEqual(len(first_rank), 1)
            self.assertEqual(len(second_rank), 1)
            rank_ranges = [
                (datasets[0].GetBounds()[0], datasets[0].GetBounds()[1])
                for datasets in (first_rank, second_rank)
            ]
            self.assertCountEqual(rank_ranges, [(0.0, 1.0), (1.0, 2.0)])

    def test_vtm_reader_preserves_uneven_and_empty_rank_assignments(self):
        from cfdpost.kernel.reader import read_snapshot

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._write_vtm(root, block_count=3)
            assigned = [read_snapshot(source, rank=rank, size=2) for rank in range(2)]
            self.assertEqual(sum(dataset.GetNumberOfCells() for rank_data in assigned for dataset in rank_data), 3)
            self.assertEqual(sorted(len(rank_data) for rank_data in assigned), [1, 2])

            one_block = self._write_vtm(root, name="one", block_count=1)
            assigned = [read_snapshot(one_block, rank=rank, size=2) for rank in range(2)]
            self.assertEqual(sum(dataset.GetNumberOfCells() for rank_data in assigned for dataset in rank_data), 1)
            self.assertEqual(
                sum(not any(dataset.GetNumberOfCells() for dataset in rank_data) for rank_data in assigned), 1
            )

    def test_pvtu_reader_distributes_piece_requests_across_ranks(self):
        from cfdpost.kernel.reader import read_snapshot

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_vtm(root)
            source = root / "case.pvtu"
            source.write_text(
                '<VTKFile type="PUnstructuredGrid" version="1.0" byte_order="LittleEndian">'
                '<PUnstructuredGrid GhostLevel="0"><PPointData Scalars="pressure">'
                '<PDataArray type="Float32" Name="pressure"/></PPointData>'
                '<PCellData Scalars="temperature"><PDataArray type="Float32" Name="temperature"/></PCellData>'
                '<PPoints><PDataArray type="Float32" NumberOfComponents="3"/></PPoints>'
                '<Piece Source="case-block0.vtu"/><Piece Source="case-block1.vtu"/>'
                '</PUnstructuredGrid></VTKFile>',
                encoding="utf-8",
            )
            datasets = [read_snapshot(source, rank=rank, size=2)[0] for rank in range(2)]
            rank_ranges = [(dataset.GetBounds()[0], dataset.GetBounds()[1]) for dataset in datasets]
            self.assertCountEqual(rank_ranges, [(0.0, 1.0), (1.0, 2.0)])

    def test_vtm_reader_removes_marked_duplicate_ghost_cells(self):
        from cfdpost.kernel.reader import read_snapshot

        with tempfile.TemporaryDirectory() as directory:
            source = self._write_vtm(Path(directory), duplicate_second=True)
            datasets = read_snapshot(source)
            self.assertEqual(sum(dataset.GetNumberOfCells() for dataset in datasets), 1)
            self.assertTrue(all(dataset.GetCellData().GetArray("vtkGhostType") is None for dataset in datasets))

    def test_vtm_single_rank_line_plots_combine_all_blocks_once(self):
        from cfdpost.executor import execute

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._write_vtm(root)
            request = self._request(source, root / "single")
            prepare(request)
            execute(request)
            for field in ("pressure", "temperature"):
                rows = self._rows(root / "single" / f"line_{field}.csv")
                self.assertEqual(len(rows), 18)
                valid_x = [float(row[1]) for row in rows[1:] if row[-1] == "True"]
                self.assertTrue(any(x < 1 for x in valid_x))
                self.assertTrue(any(x > 1 for x in valid_x))
            self.assertEqual(len(list((root / "single").glob("line_*.csv"))), 2)
            self.assertEqual(len(list((root / "single").glob("slice_*.png"))), 1)

    def test_vtm_temporal_statistics_use_physical_times_across_all_blocks(self):
        from cfdpost.executor import execute

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_vtm(root, "time0", pressure=5)
            self._write_vtm(root, "time2", pressure=9)
            source = root / "series.pvd"
            source.write_text(
                '<VTKFile type="Collection"><Collection>'
                '<DataSet timestep="0" file="time0.vtm"/>'
                '<DataSet timestep="2" file="time2.vtm"/>'
                '</Collection></VTKFile>',
                encoding="utf-8",
            )
            request = AnalysisRequest.from_dict({
                "input": str(source), "output": str(root / "stats"), "approved": True,
                "actions": [{"type": "mean", "field": "pressure"}, {"type": "rms", "field": "pressure"}],
            })
            prepare(request)
            execute(request)
            with (root / "stats" / "statistics_action01.csv").open(encoding="utf-8") as stream:
                mean = next(csv.DictReader(stream))
            with (root / "stats" / "statistics_action02.csv").open(encoding="utf-8") as stream:
                rms = next(csv.DictReader(stream))
            self.assertEqual(float(mean["time_start"]), 0.0)
            self.assertEqual(float(mean["time_end"]), 2.0)
            self.assertAlmostEqual(float(mean["value_mean"]), 7.0)
            self.assertAlmostEqual(float(rms["value_mean"]), 53 ** 0.5)
            self.assertEqual(int(mean["sample_count"]), 8)

    def test_vtm_custom_global_results_combine_all_blocks(self):
        from cfdpost.executor import execute

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._write_vtm(root)
            function_file = root / "functions.py"
            function_file.write_text(
                "def cell_count(dataset, constants):\n"
                "    return {'global': dataset.GetNumberOfCells(), 'reduction': 'sum'}\n",
                encoding="utf-8",
            )
            registry = root / "functions.json"
            registry.write_text(json.dumps({
                "cell_count": {"source": str(function_file), "function": "cell_count"},
            }), encoding="utf-8")
            request = AnalysisRequest.from_dict({
                "input": str(source), "output": str(root / "derived"), "approved": True,
                "custom_registry": str(registry),
                "actions": [{"type": "derived", "function": "cell_count"}],
            })
            prepare(request)
            execute(request)
            with (root / "derived" / "derived_variables.jsonl").open(encoding="utf-8") as stream:
                result = json.loads(next(stream))["result"]
            self.assertEqual(result, {"global": 2.0, "reduction": "sum"})

    def test_monolithic_legacy_vtk_fails_clearly_for_multi_rank(self):
        from cfdpost.kernel.reader import read_snapshot
        from cfdpost.models import RequestError

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "monolithic.vtk"
            source.write_text("legacy input", encoding="utf-8")
            with self.assertRaisesRegex(RequestError, "Convert it to .pvtu or a .vtm"):
                read_snapshot(source, rank=0, size=2)

    def test_slurm_allocation_without_an_mpi_task_stays_single_process(self):
        from cfdpost.executor import _mpi

        with patch.dict(os.environ, {"SLURM_NTASKS": "4"}, clear=True):
            self.assertIsNone(_mpi())

    def test_vtm_workflow_matches_single_rank_outputs_across_mpi_ranks(self):
        if os.environ.get("CFDPOST_RUN_MPI_TESTS") != "1":
            raise unittest.SkipTest("Set CFDPOST_RUN_MPI_TESTS=1 in an MPI-enabled environment to run this acceptance test")
        from cfdpost.executor import execute

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_vtm(root, "time0", pressure=5)
            self._write_vtm(root, "time2", pressure=9)
            source = root / "series.pvd"
            source.write_text(
                '<VTKFile type="Collection"><Collection>'
                '<DataSet timestep="0" file="time0.vtm"/>'
                '<DataSet timestep="2" file="time2.vtm"/>'
                '</Collection></VTKFile>',
                encoding="utf-8",
            )
            single_request = self._request(source, root / "single", timed=True)
            prepare(single_request)
            execute(single_request)

            mpi_request = self._request(source, root / "mpi", timed=True)
            prepare(mpi_request)
            environment = os.environ.copy()
            environment["OMPI_ALLOW_RUN_AS_ROOT"] = "1"
            environment["OMPI_ALLOW_RUN_AS_ROOT_CONFIRM"] = "1"
            result = subprocess.run(
                [self.mpiexec, "-n", "2", sys.executable, "-m", "cfdpost", "execute",
                 str(root / "mpi" / "request.json")],
                cwd=Path.cwd(), env=environment, capture_output=True, text=True, timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for field in ("pressure", "temperature"):
                self.assertEqual(
                    self._rows(root / "single" / f"line_t0_{field}.csv"),
                    self._rows(root / "mpi" / f"line_t0_{field}.csv"),
                )
            for action in (4, 5):
                self.assertEqual(
                    self._rows(root / "single" / f"statistics_action{action:02d}.csv"),
                    self._rows(root / "mpi" / f"statistics_action{action:02d}.csv"),
                )
            self.assertTrue((root / "mpi" / "slice_t0_pressure.png").is_file())
            self.assertTrue((root / "mpi" / "performance.json").is_file())
            self.assertEqual(len(list((root / "mpi").glob("line_t0_*.csv"))), 2)
            self.assertEqual(len(list((root / "mpi").glob("metrics_rank*.json"))), 2)


if __name__ == "__main__":
    unittest.main()
