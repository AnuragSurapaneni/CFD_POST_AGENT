import json
import csv
import math
import os
import tempfile
import unittest
from pathlib import Path

from cfdpost.models import AnalysisRequest, RequestError
from cfdpost.clusters import save_cluster
from cfdpost.session import AnalysisSession
from cfdpost.workflow import prepare


class WorkflowTests(unittest.TestCase):
    def test_notebook_session_requires_approval_then_writes_python_script(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "tiny.vtk"
            source.write_text("placeholder", encoding="utf-8")
            session = AnalysisSession(str(source), str(root / "result"), cpus=3)
            session.line_plot("pressure", [0, 0, 0], [1, 0, 0], resolution=4)
            self.assertIn("1. line_plot", session.review())
            with self.assertRaisesRegex(RequestError, "approve"):
                session.write()
            script = Path(session.approve().write())
            request = json.loads((script.parent / "request.json").read_text(encoding="utf-8"))
            self.assertTrue(request["approved"])
            self.assertEqual(request["cpus"], 3)
            self.assertEqual(request["actions"][0]["start"], [0, 0, 0])
            self.assertIn("'cfdpost', 'execute'", script.read_text(encoding="utf-8"))

    def test_slurm_script_uses_user_resources_and_does_not_submit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "case.pvtu"
            source.write_text('<VTKFile><PUnstructuredGrid><Piece Source="part.vtu"/></PUnstructuredGrid></VTKFile>',
                              encoding="utf-8")
            (root / "part.vtu").write_text("placeholder", encoding="utf-8")
            request = AnalysisRequest.from_dict({
                "input": str(source), "output": str(root / "result"), "approved": True,
                "execution": "slurm", "nodes": 4, "cpus_per_node": 12,
                "slurm": {"account": "flow", "partition": "compute"},
                "actions": [{"type": "line_plot", "field": "p", "start": [0, 0, 0], "end": [1, 0, 0]}],
            })
            prepare(request)
            slurm = (root / "result" / "submit.slurm").read_text(encoding="utf-8")
            self.assertIn("#SBATCH --nodes=4", slurm)
            self.assertIn("#SBATCH --ntasks=4", slurm)
            self.assertIn("#SBATCH --cpus-per-task=12", slurm)
            self.assertIn("srun python -m cfdpost execute", slurm)
            self.assertNotIn("sbatch ", slurm)
            script = root / "result" / "run_analysis.py"
            self.assertTrue(script.is_file())
            self.assertIn(str(root / "result" / "request.json"), script.read_text(encoding="utf-8"))
            self.assertEqual(json.loads((root / "result" / "request.json").read_text())["output"],
                             str((root / "result").resolve()))

    def test_saved_cluster_profile_is_overridden_by_per_job_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "case.pvtu"
            source.write_text('<VTKFile><PUnstructuredGrid><Piece Source="part.vtu"/></PUnstructuredGrid></VTKFile>',
                              encoding="utf-8")
            (root / "part.vtu").write_text("placeholder", encoding="utf-8")
            previous = Path.cwd()
            try:
                os.chdir(root)
                save_cluster("local_hpc", {"account": "project-a", "partition": "compute", "time": "02:00:00"})
                request = AnalysisRequest.from_dict({
                    "input": str(source), "output": str(root / "result"), "approved": True,
                    "execution": "slurm", "nodes": 2, "cpus_per_node": 8,
                    "slurm_profile": "local_hpc", "slurm": {"time": "04:00:00"},
                    "actions": [{"type": "line_plot", "field": "p", "start": [0, 0, 0], "end": [1, 0, 0]}],
                })
                prepare(request)
                slurm = (root / "result" / "submit.slurm").read_text(encoding="utf-8")
                self.assertIn("#SBATCH --account=project-a", slurm)
                self.assertIn("#SBATCH --partition=compute", slurm)
                self.assertIn("#SBATCH --time=04:00:00", slurm)
            finally:
                os.chdir(previous)

    def test_temporal_line_plot_requires_physical_time_before_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "series.pvd"
            source.write_text(
                '<VTKFile><Collection><DataSet timestep="0" file="a.vtu"/>'
                '<DataSet timestep="1" file="b.vtu"/></Collection></VTKFile>', encoding="utf-8"
            )
            (root / "a.vtu").write_text("fixture", encoding="utf-8")
            (root / "b.vtu").write_text("fixture", encoding="utf-8")
            with self.assertRaisesRegex(RequestError, "physical 'time'"):
                AnalysisRequest.from_dict({
                    "input": str(source), "output": str(root / "out"),
                    "actions": [{"type": "line_plot", "field": "p", "start": [0, 0, 0], "end": [1, 0, 0]}],
                })

    def test_incomplete_line_and_streamline_requests_are_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "case.vtk"
            source.write_text("placeholder", encoding="utf-8")
            with self.assertRaisesRegex(RequestError, "please provide.*end"):
                AnalysisRequest.from_dict({
                    "input": str(source), "output": str(root / "out"),
                    "actions": [{"type": "line_plot", "field": "pressure", "start": [0, 0, 0]}],
                })
            with self.assertRaisesRegex(RequestError, "point seeds need one or more 3D coordinates"):
                AnalysisRequest.from_dict({
                    "input": str(source), "output": str(root / "out"),
                    "actions": [{"type": "streamlines", "field": "velocity",
                                 "seeds": {"type": "points", "points": []}}],
                })
            with self.assertRaisesRegex(RequestError, "please provide.*field"):
                AnalysisRequest.from_dict({
                    "input": str(source), "output": str(root / "out"),
                    "actions": [{"type": "slice_contour", "origin": [0, 0, 0], "normal": [0, 0, 1]}],
                })


class VtkAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import vtk  # noqa: F401
            import numpy  # noqa: F401
            import matplotlib  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("VTK, NumPy, and Matplotlib are required for the data-path acceptance test")

    def test_approved_vtk_line_workflow_writes_csv_png_script_and_log(self):
        from cfdpost.executor import execute

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "triangle.vtk"
            source.write_text(
                "# vtk DataFile Version 3.0\nsmall triangle\nASCII\nDATASET POLYDATA\n"
                "POINTS 3 float\n0 0 0  1 0 0  0 1 0\nPOLYGONS 1 4\n3 0 1 2\n"
                "POINT_DATA 3\nSCALARS pressure float 1\nLOOKUP_TABLE default\n1 2 3\n",
                encoding="utf-8",
            )
            request = AnalysisRequest.from_dict({
                "input": str(source), "output": str(root / "result"), "approved": True, "cpus": 2,
                "actions": [{"type": "line_plot", "field": "pressure", "start": [0.1, 0.1, 0],
                             "end": [0.7, 0.1, 0], "resolution": 8}],
            })
            prepare(request)
            execute(request)
            result = root / "result"
            self.assertTrue((result / "line_pressure.csv").is_file())
            self.assertTrue((result / "line_pressure.png").is_file())
            self.assertTrue((result / "run.log").is_file())
            self.assertTrue((result / "run_analysis.py").is_file())
            metrics = json.loads((result / "metrics_rank0000.json").read_text(encoding="utf-8"))
            self.assertEqual(metrics["threads_per_rank"], 2)
            self.assertGreater(metrics["elapsed_seconds"], 0)
            self.assertGreater(metrics["input_case_bytes_total"], 0)
            self.assertGreater(metrics["max_rss_bytes"], 0)
            performance = json.loads((result / "performance.json").read_text(encoding="utf-8"))
            self.assertEqual(performance["nodes_requested"], 1)
            self.assertEqual(performance["nodes_observed"], 1)
            self.assertEqual(performance["mpi_ranks"], 1)

    def test_user_temporal_pvtu_fixture_supports_serial_line_slice_and_statistics(self):
        from cfdpost.executor import execute

        source_root = Path(__file__).resolve().parents[1] / "data" / "vtk"
        source = source_root / "fin_rate_autoig_gri_no_nsi.pvd"
        # t=0 is the mesh-only initial condition, so temporal statistics use the two populated snapshots.
        series = [
            {"time": 0.0005, "file": str(source_root / "fin_rate_autoig_gri_no_nsi_00000010.pvtu")},
            {"time": 0.001, "file": str(source_root / "fin_rate_autoig_gri_no_nsi_00000020.pvtu")},
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = AnalysisRequest.from_dict({
                "input": str(source), "output": str(root / "result"), "approved": True, "time_series": series,
                "actions": [
                    {"type": "line_plot", "field": "TEMPE", "association": "point",
                     "start": [-0.0015, 0, 0], "end": [0.0015, 0, 0], "resolution": 32, "time": 0.0005},
                    {"type": "slice_contour", "field": "TEMPE", "origin": [0, 0, 0],
                     "normal": [0, 0, 1], "time": 0.0005},
                    {"type": "mean", "field": "TEMPE", "association": "point"},
                    {"type": "rms", "field": "TEMPE", "association": "point"},
                ],
            })
            execute(request)
            result = root / "result"
            self.assertTrue((result / "line_t0.0005_TEMPE.png").is_file())
            self.assertTrue((result / "slice_t0.0005_TEMPE.png").is_file())
            with (result / "statistics_action03.csv").open(encoding="utf-8") as stream:
                mean = next(csv.DictReader(stream))
            with (result / "statistics_action04.csv").open(encoding="utf-8") as stream:
                raw_rms = next(csv.DictReader(stream))
            self.assertEqual(float(mean["time_start"]), 0.0005)
            self.assertEqual(float(mean["time_end"]), 0.001)
            self.assertEqual(int(mean["sample_count"]), 84)
            self.assertAlmostEqual(float(mean["value_mean"]), 1983.467379426408)
            self.assertAlmostEqual(float(raw_rms["value_mean"]), 2040.507734479687)

    def _write_pvtu(self, root: Path, point_values: str = "1 2 3", cell_values: str = "7") -> Path:
        master = root / "case.pvtu"
        master.write_text(
            '<VTKFile type="PUnstructuredGrid" version="1.0" byte_order="LittleEndian">'
            '<PUnstructuredGrid GhostLevel="0"><PPointData Scalars="pressure">'
            '<PDataArray type="Float32" Name="pressure"/></PPointData><PCellData>'
            '<PDataArray type="Float32" Name="temperature"/></PCellData>'
            '<PPoints><PDataArray type="Float32" NumberOfComponents="3"/></PPoints>'
            '<Piece Source="piece.vtu"/></PUnstructuredGrid></VTKFile>', encoding="utf-8"
        )
        (root / "piece.vtu").write_text(
            '<VTKFile type="UnstructuredGrid" version="1.0" byte_order="LittleEndian">'
            '<UnstructuredGrid><Piece NumberOfPoints="3" NumberOfCells="1">'
            f'<PointData Scalars="pressure"><DataArray type="Float32" Name="pressure" format="ascii">{point_values}</DataArray></PointData>'
            f'<CellData Scalars="temperature"><DataArray type="Float32" Name="temperature" format="ascii">{cell_values}</DataArray></CellData>'
            '<Points><DataArray type="Float32" NumberOfComponents="3" format="ascii">'
            '0 0 0 1 0 0 0 1 0</DataArray></Points><Cells>'
            '<DataArray type="Int64" Name="connectivity" format="ascii">0 1 2</DataArray>'
            '<DataArray type="Int64" Name="offsets" format="ascii">3</DataArray>'
            '<DataArray type="UInt8" Name="types" format="ascii">5</DataArray>'
            '</Cells></Piece></UnstructuredGrid></VTKFile>', encoding="utf-8"
        )
        return master

    def test_pvtu_line_workflow_reads_piece_and_writes_results(self):
        from cfdpost.executor import execute

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._write_pvtu(root)
            request = AnalysisRequest.from_dict({
                "input": str(source), "output": str(root / "result"), "approved": True,
                "actions": [
                    {"type": "line_plot", "field": "pressure", "start": [0.1, 0.1, 0],
                     "end": [0.7, 0.1, 0], "resolution": 8},
                    {"type": "line_plot", "field": "temperature", "association": "cell",
                     "start": [0.1, 0.1, 0], "end": [0.7, 0.1, 0], "resolution": 8},
                ],
            })
            prepare(request)
            source_bytes = source.read_bytes()
            execute(request)
            self.assertTrue((root / "result" / "line_pressure.png").is_file())
            self.assertTrue((root / "result" / "line_temperature.png").is_file())
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_array_size_mismatch_stops_before_plotting_and_keeps_source(self):
        from cfdpost.executor import execute

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._write_pvtu(root, "1 2")
            original = (root / "piece.vtu").read_bytes()
            request = AnalysisRequest.from_dict({
                "input": str(source), "output": str(root / "result"), "approved": True,
                "actions": [{"type": "line_plot", "field": "pressure", "start": [0, 0, 0], "end": [1, 0, 0]}],
            })
            with self.assertRaisesRegex(RequestError, "size mismatch"):
                execute(request)
            self.assertEqual((root / "piece.vtu").read_bytes(), original)
            self.assertFalse((root / "result" / "line_pressure.png").exists())

    def test_cell_array_size_mismatch_stops_before_plotting_and_keeps_source(self):
        from cfdpost.executor import execute

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._write_pvtu(root, cell_values="")
            original = (root / "piece.vtu").read_bytes()
            request = AnalysisRequest.from_dict({
                "input": str(source), "output": str(root / "result"), "approved": True,
                "actions": [{"type": "line_plot", "field": "temperature", "association": "cell",
                             "start": [0, 0, 0], "end": [1, 0, 0]}],
            })
            with self.assertRaisesRegex(RequestError, "Structural size mismatch|size mismatch"):
                execute(request)
            self.assertEqual((root / "piece.vtu").read_bytes(), original)
            self.assertFalse((root / "result" / "line_temperature.png").exists())

    def test_custom_cell_variable_is_saved_and_reused_by_a_later_plot(self):
        from cfdpost.custom import register
        from cfdpost.executor import execute
        import vtk
        from vtk.util.numpy_support import vtk_to_numpy

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._write_pvtu(root)
            function_file = root / "cell_functions.py"
            function_file.write_text(
                "from vtk.util.numpy_support import vtk_to_numpy\n"
                "def double_temperature(dataset, constants):\n"
                "    values = vtk_to_numpy(dataset.GetCellData().GetArray('temperature')) * 2\n"
                "    return {'name': 'double_temperature', 'association': 'cell', 'values': values}\n",
                encoding="utf-8",
            )
            previous = Path.cwd()
            try:
                os.chdir(root)
                register("double_temperature", str(function_file), "double_temperature")
                request = AnalysisRequest.from_dict({
                    "input": str(source), "output": str(root / "result"), "approved": True,
                    "actions": [
                        {"type": "derived", "function": "double_temperature", "save_field": True},
                        {"type": "line_plot", "field": "double_temperature", "association": "cell",
                         "start": [0.1, 0.1, 0], "end": [0.7, 0.1, 0], "resolution": 8},
                    ],
                })
                prepare(request)
                execute(request)

                later_session = AnalysisRequest.from_dict({
                    "input": str(source), "output": str(root / "later-session"), "approved": True,
                    "actions": [
                        {"type": "derived", "function": "double_temperature", "save_field": True},
                        {"type": "line_plot", "field": "double_temperature", "association": "cell",
                         "start": [0.1, 0.1, 0], "end": [0.7, 0.1, 0], "resolution": 8},
                    ],
                })
                prepare(later_session)
                execute(later_session)
            finally:
                os.chdir(previous)

            result = root / "result"
            self.assertTrue((result / "line_double_temperature.png").is_file())
            derived = result / "derived_custom_double_temperature_rank0000_part0000.vtk"
            self.assertTrue(derived.is_file())
            reader = vtk.vtkDataSetReader()
            reader.SetFileName(str(derived))
            reader.ReadAllScalarsOn()
            reader.Update()
            values = vtk_to_numpy(reader.GetOutput().GetCellData().GetArray("double_temperature"))
            self.assertEqual(values.tolist(), [14.0])
            self.assertTrue((root / "later-session" / "line_double_temperature.png").is_file())

    def test_partial_azimuthal_sector_requires_explicit_acceptance(self):
        from cfdpost.executor import execute

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "tetra.vtk"
            source.write_text(
                "# vtk DataFile Version 3.0\ntetra\nASCII\nDATASET UNSTRUCTURED_GRID\n"
                "POINTS 4 float\n0 0 0  1 0 0  0 1 0  0 0 1\n"
                "CELLS 1 5\n4 0 1 2 3\nCELL_TYPES 1\n10\n"
                "POINT_DATA 4\nSCALARS pressure float 1\nLOOKUP_TABLE default\n1 2 3 4\n",
                encoding="utf-8",
            )
            action = {"type": "azimuthal_average", "field": "pressure", "axis": [0, 0, 1],
                      "origin": [0, 0, 0], "slice": {"origin": [0, 0, 0.2], "normal": [0, 0, 1]},
                      "bins": 4, "full_circumference": True}
            request = AnalysisRequest.from_dict({
                "input": str(source), "output": str(root / "result"), "approved": True,
                "actions": [action],
            })
            with self.assertRaisesRegex(RequestError, "confirm partial-sector interpretation"):
                execute(request)

            action["accept_partial_as_full"] = True
            accepted = AnalysisRequest.from_dict({
                "input": str(source), "output": str(root / "result"), "approved": True,
                "actions": [action],
            })
            execute(accepted)
            with (root / "result" / "azimuthal_01.csv").open(encoding="utf-8") as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual(row["full_circumference_interpretation"], "True")
            self.assertLess(float(row["angular_coverage_degrees"]), 342.0)

    def test_ambiguous_streamline_field_requires_explicit_association(self):
        from cfdpost.executor import execute

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "ambiguous.vtk"
            source.write_text(
                "# vtk DataFile Version 3.0\ntriangle\nASCII\nDATASET POLYDATA\n"
                "POINTS 3 float\n0 0 0  1 0 0  0 1 0\nPOLYGONS 1 4\n3 0 1 2\n"
                "POINT_DATA 3\nVECTORS velocity float\n1 0 0  1 0 0  1 0 0\n"
                "CELL_DATA 1\nSCALARS velocity float 1\nLOOKUP_TABLE default\n1\n",
                encoding="utf-8",
            )
            request = AnalysisRequest.from_dict({
                "input": str(source), "output": str(root / "result"), "approved": True,
                "actions": [{"type": "streamlines", "field": "velocity",
                             "seeds": {"type": "points", "points": [[0.1, 0.1, 0]]}}],
            })
            with self.assertRaisesRegex(RequestError, "exists as both point and cell data; specify association"):
                execute(request)

    def test_ambiguous_slice_field_requires_explicit_association(self):
        from cfdpost.executor import execute

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "ambiguous.vtk"
            source.write_text(
                "# vtk DataFile Version 3.0\ntriangle\nASCII\nDATASET POLYDATA\n"
                "POINTS 3 float\n0 0 0  1 0 0  0 1 0\nPOLYGONS 1 4\n3 0 1 2\n"
                "POINT_DATA 3\nSCALARS pressure float 1\nLOOKUP_TABLE default\n1 2 3\n"
                "CELL_DATA 1\nSCALARS pressure float 1\nLOOKUP_TABLE default\n2\n",
                encoding="utf-8",
            )
            request = AnalysisRequest.from_dict({
                "input": str(source), "output": str(root / "result"), "approved": True,
                "actions": [{"type": "slice_contour", "field": "pressure",
                             "origin": [0.1, 0.1, 0], "normal": [0, 0, 1]}],
            })
            with self.assertRaisesRegex(RequestError, "exists as both point and cell data; specify association"):
                execute(request)

    def test_time_weighted_statistics_use_physical_timestamps(self):
        from cfdpost.executor import execute

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for time_value, pressure in ((0, 0), (1, 1), (3, 3)):
                source = root / f"case-{time_value}.vtk"
                source.write_text(
                    "# vtk DataFile Version 3.0\ntime sample\nASCII\nDATASET POLYDATA\n"
                    "POINTS 3 float\n0 0 0  1 0 0  0 1 0\nPOLYGONS 1 4\n3 0 1 2\n"
                    f"POINT_DATA 3\nSCALARS pressure float 1\nLOOKUP_TABLE default\n{pressure} {pressure} {pressure}\n",
                    encoding="utf-8",
                )
            pvd = root / "series.pvd"
            pvd.write_text(
                '<VTKFile><Collection><DataSet timestep="0" file="case-0.vtk"/>'
                '<DataSet timestep="1" file="case-1.vtk"/><DataSet timestep="3" file="case-3.vtk"/>'
                '</Collection></VTKFile>', encoding="utf-8"
            )
            request = AnalysisRequest.from_dict({
                "input": str(pvd), "output": str(root / "result"), "approved": True,
                "actions": [{"type": "mean", "field": "pressure", "save_field": True,
                             "spatial_weighting": "cell_measure"},
                            {"type": "rms", "field": "pressure"},
                            {"type": "rms", "field": "pressure", "result": "fluctuation_rms"}],
            })
            execute(request)
            with (root / "result" / "statistics_action01.csv").open(encoding="utf-8") as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual(float(row["time_start"]), 0.0)
            self.assertEqual(float(row["time_end"]), 3.0)
            self.assertAlmostEqual(float(row["value_mean"]), 1.5)
            self.assertTrue(math.isclose(float(row["duration"]), 3.0))
            self.assertTrue(list((root / "result").glob("derived_mean_pressure_part*.vtk")))
            with (root / "result" / "statistics_action02.csv").open(encoding="utf-8") as stream:
                raw_rms = next(csv.DictReader(stream))
            with (root / "result" / "statistics_action03.csv").open(encoding="utf-8") as stream:
                fluctuation_rms = next(csv.DictReader(stream))
            self.assertEqual(raw_rms["result"], "raw_rms")
            self.assertAlmostEqual(float(raw_rms["value_mean"]), math.sqrt(3.5))
            self.assertEqual(fluctuation_rms["result"], "fluctuation_rms")
            self.assertAlmostEqual(float(fluctuation_rms["value_mean"]), math.sqrt(1.25))

    def test_composed_temporal_workflow_covers_derived_line_slice_threshold_streamline_and_average(self):
        from cfdpost.custom import register
        from cfdpost.executor import execute

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for time_value, offset in ((0, 0), (2, 2)):
                source = root / f"tetra-{time_value}.vtk"
                source.write_text(
                    "# vtk DataFile Version 3.0\ntetra mesh\nASCII\nDATASET UNSTRUCTURED_GRID\n"
                    "POINTS 4 float\n0 0 0  1 0 0  0 1 0  0 0 1\n"
                    "CELLS 1 5\n4 0 1 2 3\nCELL_TYPES 1\n10\n"
                    f"POINT_DATA 4\nSCALARS pressure float 1\nLOOKUP_TABLE default\n{1+offset} {2+offset} {3+offset} {4+offset}\n"
                    "VECTORS velocity float\n1 0 0  1 0 0  1 0 0  1 0 0\n",
                    encoding="utf-8",
                )
            collection = root / "series.pvd"
            collection.write_text(
                '<VTKFile><Collection><DataSet timestep="0" file="tetra-0.vtk"/>'
                '<DataSet timestep="2" file="tetra-2.vtk"/></Collection></VTKFile>', encoding="utf-8"
            )
            functions = root / "analysis_functions.py"
            functions.write_text(
                "from vtk.util.numpy_support import vtk_to_numpy\n"
                "def double_pressure(dataset, constants):\n"
                "    values = vtk_to_numpy(dataset.GetPointData().GetArray('pressure')) * 2\n"
                "    return {'name': 'double_pressure', 'association': 'point', 'values': values}\n",
                encoding="utf-8",
            )
            previous = Path.cwd()
            try:
                os.chdir(root)
                register("double_pressure", str(functions), "double_pressure")
                request = AnalysisRequest.from_dict({
                    "input": str(collection), "output": str(root / "result"), "approved": True,
                    "actions": [
                        {"type": "derived", "function": "double_pressure", "time": 0},
                        {"type": "line_plot", "field": "double_pressure", "start": [0.05, 0.05, 0.1],
                         "end": [0.4, 0.05, 0.1], "time": 0, "resolution": 8},
                        {"type": "slice_contour", "field": "pressure", "origin": [0, 0, 0.2],
                         "normal": [0, 0, 1], "time": 0, "scale": [0, 5]},
                        {"type": "slice_contour", "field": "pressure", "origin": [0, 0, 0.2],
                         "normal": [0, 0, 1], "time": 2, "scale": [0, 5]},
                        {"type": "threshold", "field": "pressure", "range": [1.5, 3.5], "name": "middle",
                         "time": 0},
                        {"type": "line_plot", "field": "pressure", "start": [0.05, 0.05, 0.1],
                         "end": [0.4, 0.05, 0.1], "time": 0, "selection": "middle", "resolution": 8},
                        {"type": "streamlines", "field": "velocity", "seeds": {"type": "points", "points": [[0.1, 0.1, 0.1]]},
                         "time": 0, "step": 0.01},
                        {"type": "streamlines", "field": "velocity", "seeds": {"type": "line", "start": [0.1, 0.1, 0.1],
                         "end": [0.2, 0.1, 0.1], "count": 3}, "time": 0, "step": 0.01},
                        {"type": "streamlines", "field": "velocity", "seeds": {"type": "plane", "origin": [0.05, 0.05, 0.05],
                         "point1": [0.15, 0.05, 0.05], "point2": [0.05, 0.15, 0.05], "x_count": 2, "y_count": 2},
                         "time": 0, "step": 0.01},
                        {"type": "azimuthal_average", "field": "pressure", "axis": [0, 0, 1],
                         "origin": [0, 0, 0], "slice": {"origin": [0, 0, 0.2], "normal": [0, 0, 1]},
                         "time": 0, "bins": 5},
                        {"type": "mean", "field": "pressure", "save_field": True},
                        {"type": "rms", "field": "pressure", "result": "fluctuation_rms"},
                    ],
                })
                prepare(request)
                prepared = AnalysisRequest.from_dict(json.loads((root / "result" / "request.json").read_text()))
                execute(prepared)
            finally:
                os.chdir(previous)
            result = root / "result"
            self.assertTrue((result / "line_t0_double_pressure.png").is_file())
            self.assertTrue((result / "line_t0_pressure.png").is_file())
            self.assertTrue((result / "slice_t0_pressure.png").is_file())
            self.assertTrue((result / "slice_t2_pressure.png").is_file())
            self.assertTrue(list(result.glob("threshold_*.vtk")))
            self.assertTrue(list(result.glob("streamlines_*.png")))
            self.assertTrue(list(result.glob("azimuthal_*.csv")))
            self.assertTrue((result / "statistics_action11.csv").is_file())
            self.assertTrue((result / "statistics_action12.csv").is_file())
            self.assertEqual(len(list(result.glob("streamlines_*.png"))), 3)
            import vtk
            line_counts = {}
            for streamline_file in result.glob("streamlines_*.vtp"):
                reader = vtk.vtkXMLPolyDataReader()
                reader.SetFileName(str(streamline_file))
                reader.Update()
                line_counts[streamline_file.name] = reader.GetOutput().GetNumberOfLines()
            self.assertEqual(len(line_counts), 3)
            self.assertTrue(all(line_counts.values()), line_counts)
            self.assertTrue((result / "observations.md").is_file())
            observations = (result / "observations.md").read_text(encoding="utf-8")
            self.assertIn("[statistics_action11.csv](statistics_action11.csv)", observations)
            self.assertIn("pressure` mean", observations)
            self.assertIn("evaluate them against the saved fields and plots", observations)
            azimuthal_path = next(result.glob("azimuthal_*.csv"))
            with azimuthal_path.open(encoding="utf-8") as stream:
                azimuthal_rows = list(csv.DictReader(stream))
            self.assertEqual(len(azimuthal_rows), 5)
            self.assertEqual(float(azimuthal_rows[0]["time"]), 0.0)
            self.assertIn("angular_coverage_degrees", azimuthal_rows[0])
            self.assertTrue(any(math.isfinite(float(row["pressure_mean"])) for row in azimuthal_rows))


if __name__ == "__main__":
    unittest.main()
