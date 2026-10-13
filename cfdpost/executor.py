"""Execute approved requests and create auditable result files."""

from __future__ import annotations

import csv
import json
import numbers
import os
import resource
import socket
import time
from pathlib import Path
from typing import Any

import numpy as np

from . import custom
from .kernel.data import KernelData, Partition
from .models import AnalysisRequest, RequestError
from .operations import (angular_coverage, azimuthal_average, azimuthal_profile, azimuthal_samples,
                         save_azimuthal_profile, streamlines, threshold)
from .plotting import (field_values, line_plot, sample_line, save_line_samples, sample_slice,
                       save_slice_samples, slice_contour)


def _mpi():
    launcher_size = next((os.environ[name] for name in (
        "OMPI_COMM_WORLD_SIZE", "PMI_SIZE", "PMIX_SIZE", "MV2_COMM_WORLD_SIZE"
    ) if os.environ.get(name)), None)
    if launcher_size is None and os.environ.get("SLURM_PROCID") is not None:
        launcher_size = os.environ.get("SLURM_NTASKS")
    if launcher_size is None or int(launcher_size) <= 1:
        return None
    try:
        from mpi4py import MPI
    except ImportError as exc:
        raise RequestError("This job was launched with multiple MPI ranks, but mpi4py is unavailable.") from exc
    return MPI.COMM_WORLD


def _threads(count: int) -> None:
    try:
        import vtk

        vtk.vtkMultiThreader.SetGlobalDefaultNumberOfThreads(int(count))
    except (ImportError, AttributeError):
        pass
    os.environ["OMP_NUM_THREADS"] = str(count)


def _target_snapshot(kernel: KernelData, action: dict[str, Any]):
    if len(kernel.snapshots) == 1:
        return kernel.snapshots[0]
    if "time" not in action:
        raise RequestError(
            f"Action {action['type']} selects temporal data. Provide a physical 'time' or use mean/rms."
        )
    return kernel.closest_snapshot(float(action["time"]))


def _add_custom_result(dataset: object, name: str, result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise RequestError("Custom functions must return a mapping with name, association, and values, or global.")
    if "global" in result:
        return {"global": result["global"], "reduction": result.get("reduction")}
    import vtk
    from vtk.util.numpy_support import numpy_to_vtk

    field_name = str(result.get("name", name))
    assoc = result.get("association")
    if assoc not in {"point", "cell"} or "values" not in result:
        raise RequestError("Custom field result requires association='point' or 'cell' and values.")
    values = np.asarray(result["values"])
    if values.ndim == 0:
        raise RequestError("Custom point/cell values must include one leading value per mesh item.")
    expected = dataset.GetNumberOfPoints() if assoc == "point" else dataset.GetNumberOfCells()
    if values.shape[0] != expected:
        raise RequestError(f"Custom {assoc} field {field_name!r} has {values.shape[0]} values; mesh requires {expected}.")
    vtk_array = numpy_to_vtk(np.ascontiguousarray(values), deep=True)
    vtk_array.SetName(field_name)
    attributes = dataset.GetPointData() if assoc == "point" else dataset.GetCellData()
    attributes.AddArray(vtk_array)
    return {"name": field_name, "association": assoc, "tuples": int(values.shape[0])}


def _reduce_custom_global(result: dict[str, Any], comm) -> dict[str, Any]:
    value, operation = result["global"], result.get("reduction")
    if comm is None or comm.Get_size() == 1:
        return {"global": value, "reduction": operation or "local"}
    from mpi4py import MPI

    if operation == "identical":
        values = comm.allgather(value)
        encoded = [json.dumps(item, sort_keys=True, default=str) for item in values]
        if len(set(encoded)) != 1:
            raise RequestError("Custom global result declared identical but ranks returned different values.")
        return {"global": values[0], "reduction": operation}
    if operation == "mean":
        if not isinstance(value, dict) or "sum" not in value or "count" not in value:
            raise RequestError("A custom mean reduction returns global={'sum': local_sum, 'count': local_count}.")
        total = comm.allreduce(float(value["sum"]), op=MPI.SUM)
        count = comm.allreduce(float(value["count"]), op=MPI.SUM)
        if count <= 0:
            raise RequestError("Custom mean reduction has no samples.")
        return {"global": total / count, "reduction": operation, "count": count}
    operations = {"sum": MPI.SUM, "min": MPI.MIN, "max": MPI.MAX}
    if operation not in operations:
        raise RequestError("MPI custom global results require reduction='sum', 'min', 'max', 'mean', or 'identical'.")
    if isinstance(value, numbers.Real):
        reduced = comm.allreduce(float(value), op=operations[operation])
    elif isinstance(value, dict) and all(isinstance(item, numbers.Real) for item in value.values()):
        reduced = {key: comm.allreduce(float(item), op=operations[operation]) for key, item in value.items()}
    else:
        raise RequestError("MPI sum/min/max custom results must be a number or a flat mapping of numbers.")
    return {"global": reduced, "reduction": operation}


def _combine_custom_global_results(results_by_rank: list[list[dict[str, Any]]]) -> dict[str, Any]:
    results = [result for rank_results in results_by_rank for result in rank_results]
    if not results:
        raise RequestError("A custom global calculation received no data partitions.")
    operations = {result.get("reduction") for result in results}
    if len(operations) != 1:
        raise RequestError("Custom global results from all partitions must declare the same reduction.")
    operation = operations.pop()
    values = [result["global"] for result in results]
    if operation == "identical":
        encoded = [json.dumps(value, sort_keys=True, default=str) for value in values]
        if len(set(encoded)) != 1:
            raise RequestError("Custom global result declared identical but partitions returned different values.")
        return {"global": values[0], "reduction": operation}
    if operation == "mean":
        if any(not isinstance(value, dict) or "sum" not in value or "count" not in value for value in values):
            raise RequestError("A custom mean reduction returns global={'sum': local_sum, 'count': local_count}.")
        total = sum(float(value["sum"]) for value in values)
        count = sum(float(value["count"]) for value in values)
        if count <= 0:
            raise RequestError("A custom mean reduction has no samples.")
        return {"global": total / count, "reduction": operation, "count": count}
    if operation not in {"sum", "min", "max"}:
        raise RequestError("MPI custom global results require reduction='sum', 'min', 'max', 'mean', or 'identical'.")
    if all(isinstance(value, numbers.Real) for value in values):
        scalars = [float(value) for value in values]
        reduced = sum(scalars) if operation == "sum" else min(scalars) if operation == "min" else max(scalars)
    elif all(isinstance(value, dict) and value for value in values):
        keys = set(values[0])
        if any(set(value) != keys or any(not isinstance(item, numbers.Real) for item in value.values()) for value in values):
            raise RequestError("MPI custom mapping reductions require matching flat mappings of numbers.")
        reducer = sum if operation == "sum" else min if operation == "min" else max
        reduced = {key: reducer(float(value[key]) for value in values) for key in keys}
    else:
        raise RequestError("MPI custom sum/min/max results must be numbers or matching flat mappings of numbers.")
    return {"global": reduced, "reduction": operation}


def _write_derived(partitions: list[Partition], arrays: list[np.ndarray], action: dict[str, Any], path: Path, rank: int = 0,
                   size: int = 1) -> None:
    import vtk
    from vtk.util.numpy_support import numpy_to_vtk

    for part, values in zip(partitions, arrays):
        array = numpy_to_vtk(np.ascontiguousarray(values), deep=True)
        array.SetName(action.get("result", f"{action['type']}_{action['field']}"))
        target = part.dataset.GetPointData() if action.get("association") == "point" else part.dataset.GetCellData()
        target.AddArray(array)
        writer = vtk.vtkDataSetWriter()
        rank_suffix = f"_rank{rank:04d}" if size > 1 else ""
        safe_field = "".join(c if c.isalnum() or c in "-_" else "_" for c in action["field"])
        writer.SetFileName(str(path / f"derived_{action['type']}_{safe_field}{rank_suffix}_part{part.index:04d}.vtk"))
        writer.SetInputData(part.dataset)
        writer.Write()


def _merge_line_samples(groups: list[dict[str, np.ndarray | None]]) -> dict[str, np.ndarray | None]:
    if not groups:
        raise RequestError("No input pieces were available for the requested line plot.")
    first = next((group["values"] for group in groups if group["values"] is not None), None)
    coordinates = groups[0]["coordinates"]
    distances = groups[0]["distance"]
    merged_mask = np.zeros(len(distances), dtype=bool)
    merged_values = None if first is None else np.zeros_like(first)
    for group in groups:
        valid = group["valid"] & ~merged_mask
        if group["values"] is not None:
            if merged_values is None:
                merged_values = np.zeros_like(group["values"])
            merged_values[valid] = group["values"][valid]
        merged_mask[valid] = True
    return {"distance": distances, "coordinates": coordinates, "values": merged_values, "valid": merged_mask}


def _spatial_values_and_weights(dataset: object, values: np.ndarray, association: str,
                                weighting: str) -> tuple[np.ndarray, np.ndarray]:
    scalar = np.linalg.norm(values, axis=1) if values.ndim > 1 else values.astype(float)
    if weighting == "uniform":
        return scalar.reshape(-1), np.ones(scalar.size, dtype=np.float64)
    if weighting != "cell_measure":
        raise RequestError("spatial_weighting must be 'uniform' or 'cell_measure'.")

    import vtk
    from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy

    if association == "point":
        temporary_name = "__cfdpost_temporal_statistic__"
        array = numpy_to_vtk(np.ascontiguousarray(values), deep=True)
        array.SetName(temporary_name)
        dataset.GetPointData().AddArray(array)
        conversion = vtk.vtkPointDataToCellData()
        conversion.SetInputData(dataset)
        conversion.PassPointDataOff()
        conversion.Update()
        cell_values = conversion.GetOutput().GetCellData().GetArray(temporary_name)
        if cell_values is None:
            raise RequestError("Could not map point values to cells for cell_measure weighting.")
        scalar = vtk_to_numpy(cell_values)
        scalar = np.linalg.norm(scalar, axis=1) if scalar.ndim > 1 else scalar.astype(float)

    measure = vtk.vtkCellSizeFilter()
    measure.SetInputData(dataset)
    measure.ComputeVertexCountOff()
    measure.ComputeLengthOn()
    measure.ComputeAreaOn()
    measure.ComputeVolumeOn()
    measure.Update()
    cell_data = measure.GetOutput().GetCellData()
    weights = None
    for array_name in ("Volume", "Area", "Length"):
        size_array = cell_data.GetArray(array_name)
        if size_array is None:
            continue
        candidate = np.asarray(vtk_to_numpy(size_array), dtype=np.float64)
        if np.any(np.isfinite(candidate) & (candidate > 0)):
            weights = candidate
            break
    if weights is None:
        weights = np.zeros(dataset.GetNumberOfCells(), dtype=np.float64)
    valid = np.isfinite(weights) & (weights > 0)
    if len(scalar) != len(weights) or not np.any(valid):
        raise RequestError("cell_measure weighting found no positive cell volumes, areas, or lengths.")
    return np.asarray(scalar[valid], dtype=np.float64), weights[valid]


def _time_statistic(kernel: KernelData, action: dict[str, Any], output: Path, index: int, rank: int, comm=None) -> dict[str, Any]:
    from vtk.util.numpy_support import vtk_to_numpy
    from .plotting import association

    assoc = action.get("association")
    accumulated: list[dict[str, Any]] = []
    times = [item.time for item in kernel.snapshots]
    if any(value is None for value in times):
        raise RequestError("Time-weighted statistics require physical timestamps from a PVD or time_series request.")
    if len(times) < 2:
        raise RequestError("Time-weighted statistics require at least two physical snapshots.")
    if any(b <= a for a, b in zip(times, times[1:])):
        raise RequestError("Physical timestamps must be strictly increasing.")
    for snap_index, snapshot in enumerate(kernel.snapshots):
        partitions = list(kernel.read(snapshot))
        if snap_index == 0:
            accumulated = [
                {"part": part, "assoc": association(part.dataset, action["field"], assoc), "previous": None,
                 "first": None, "second": None}
                for part in partitions
            ]
        if len(partitions) != len(accumulated):
            raise RequestError("Partition count changed between physical snapshots.")
        dt = 0.0 if snap_index == 0 else float(times[snap_index] - times[snap_index - 1])
        for entry, part in zip(accumulated, partitions):
            attrs = part.dataset.GetPointData() if entry["assoc"] == "point" else part.dataset.GetCellData()
            array = attrs.GetArray(action["field"])
            if array is None:
                raise RequestError(f"Field {action['field']!r} missing at time {snapshot.time}.")
            value = np.asarray(vtk_to_numpy(array), dtype=np.float64)
            if entry["previous"] is not None:
                if entry["previous"].shape != value.shape:
                    raise RequestError("Field size changed between snapshots; the mesh must remain fixed.")
                entry["first"] += 0.5 * (entry["previous"] + value) * dt
                entry["second"] += 0.5 * (entry["previous"] ** 2 + value ** 2) * dt
            else:
                entry["first"] = np.zeros_like(value, dtype=np.float64)
                entry["second"] = np.zeros_like(value, dtype=np.float64)
            entry["previous"] = value.copy()
            entry["part"] = part
    duration = float(times[-1] - times[0])
    derived_arrays = []
    local_sum = local_square = local_weight = 0.0
    local_count = 0
    local_min, local_max = float("inf"), float("-inf")
    for entry in accumulated:
        mean = entry["first"] / duration
        mean_square = entry["second"] / duration
        raw = np.sqrt(np.maximum(mean_square, 0.0))
        fluct = np.sqrt(np.maximum(mean_square - mean * mean, 0.0))
        kind = action.get("result", "mean" if action["type"] == "mean" else "raw_rms")
        if kind not in {"mean", "raw_rms", "fluctuation_rms"}:
            raise RequestError("Statistic result must be mean, raw_rms, or fluctuation_rms.")
        chosen = mean if kind == "mean" else raw if kind == "raw_rms" else fluct
        derived_arrays.append(chosen)
        displayed, weights = _spatial_values_and_weights(
            entry["part"].dataset, chosen, entry["assoc"], action.get("spatial_weighting", "uniform")
        )
        local_sum += float(np.sum(displayed * weights))
        local_square += float(np.sum(displayed * displayed * weights))
        local_weight += float(np.sum(weights))
        local_count += int(displayed.size)
        if displayed.size:
            local_min = min(local_min, float(np.min(displayed[weights > 0])))
            local_max = max(local_max, float(np.max(displayed[weights > 0])))
    if comm is not None and comm.Get_size() > 1:
        from mpi4py import MPI

        global_sum = comm.allreduce(local_sum, op=MPI.SUM)
        global_square = comm.allreduce(local_square, op=MPI.SUM)
        global_count = comm.allreduce(local_count, op=MPI.SUM)
        global_weight = comm.allreduce(local_weight, op=MPI.SUM)
        global_min = comm.allreduce(local_min, op=MPI.MIN)
        global_max = comm.allreduce(local_max, op=MPI.MAX)
    else:
        global_sum, global_square, global_count, global_weight = local_sum, local_square, local_count, local_weight
        global_min, global_max = local_min, local_max
    if global_weight <= 0:
        raise RequestError("No positive spatial measure was available for the requested statistic.")
    result_name = action.get("result", "mean" if action["type"] == "mean" else "raw_rms")
    csv_path = output / f"statistics_action{index:02d}.csv"
    if rank == 0:
        row = {
            "time_start": times[0], "time_end": times[-1], "duration": duration,
            "field": action["field"], "result": result_name,
            "association": assoc or (accumulated[0]["assoc"] if accumulated else "unknown"),
            "spatial_weighting": action.get("spatial_weighting", "uniform"),
            "value_mean": global_sum / global_weight,
            "value_rms": (global_square / global_weight) ** 0.5,
            "value_min": global_min, "value_max": global_max, "sample_count": global_count,
        }
        with csv_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(row))
            writer.writeheader()
            writer.writerow(row)
    suffix = f"_rank{rank:04d}" if kernel.size > 1 else ""
    if action.get("save_field"):
        np.savez_compressed(output / f"stat_field_{index:02d}{suffix}.npz", **{
            f"part_{i:04d}": values for i, values in enumerate(derived_arrays)
        })
    if action.get("save_field") and accumulated:
        derived_action = dict(action)
        derived_action["association"] = assoc or accumulated[0]["assoc"]
        derived_action["result"] = action.get("variable", f"{result_name}_{action['field']}")
        _write_derived([entry["part"] for entry in accumulated], derived_arrays, derived_action, output, rank, kernel.size)
    return {"csv": str(csv_path), "fields": len(derived_arrays), "result": result_name}


def _write_observations(output: Path) -> None:
    rows = []
    for csv_path in sorted(output.glob("statistics_action*.csv")):
        if "_rank" in csv_path.stem:
            continue
        with csv_path.open(encoding="utf-8") as stream:
            rows.extend((row, csv_path.name) for row in csv.DictReader(stream))
    if not rows:
        return
    lines = ["# Numerical observations", "", "These are descriptive summaries; evaluate them against the saved fields and plots.", ""]
    for row, evidence_file in rows:
        evidence = f"[{evidence_file}]({evidence_file}): {row['field']} / {row['result']} ({row['time_start']} to {row['time_end']})"
        lines.append(
            f"- `{row['field']}` {row['result']}: mean={float(row['value_mean']):.6g}, "
            f"range=[{float(row['value_min']):.6g}, {float(row['value_max']):.6g}] ({evidence})."
        )
    (output / "observations.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def execute(request: AnalysisRequest, request_path: Path | None = None) -> Path:
    request.validate()
    if not request.approved:
        raise RequestError("This request has not been approved. Review and approve it before execution.")
    output = Path(request.output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    comm = _mpi()
    rank, size = (0, 1) if comm is None else (comm.Get_rank(), comm.Get_size())
    _threads(request.cpus_per_node or request.cpus)
    kernel = KernelData(request.input, request.as_dict().get("time_series"), rank, size)
    started = time.perf_counter()
    log = output / (f"run_rank{rank:04d}.log" if size > 1 else "run.log")
    outputs: list[str] = []
    current_key: tuple[str, float | None] | None = None
    current: list[Partition] = []
    selections: dict[str, list[Partition]] = {}
    for index, action in enumerate(request.actions, 1):
        if action["type"] in {"mean", "rms"}:
            result = _time_statistic(kernel, action, output, index, rank, comm)
            outputs.append(json.dumps(result))
            continue
        snapshot = _target_snapshot(kernel, action)
        key = (str(snapshot.path), snapshot.time)
        if key != current_key:
            current = list(kernel.read(snapshot))
            current_key = key
        selection_name = action.get("selection")
        if selection_name and selection_name not in selections:
            raise RequestError(f"Action {index}: selection {selection_name!r} has not been created by an earlier threshold.")
        selected_partitions = selections[selection_name] if selection_name else current
        kind = action["type"]
        if kind == "threshold":
            selections.setdefault(action.get("name", f"threshold_{index}"), [])

        if (size > 1 or snapshot.path.suffix.lower() == ".vtm") and kind == "derived":
            function = custom.load(action["function"], request.custom_registry)
            local_results = [
                (part, _add_custom_result(part.dataset, action["function"], function(part.dataset, request.constants)))
                for part in selected_partitions
            ]
            has_global = any("global" in result for _, result in local_results)
            has_fields = any("global" not in result for _, result in local_results)
            local_mode = "mixed" if has_global and has_fields else "global" if has_global else "field" if has_fields else "empty"
            modes = comm.allgather(local_mode) if comm is not None else [local_mode]
            if "mixed" in modes or ("global" in modes and "field" in modes):
                raise RequestError("A custom action must return either a global result or a point/cell field on every partition.")
            if "global" in modes:
                local_globals = [result for _, result in local_results]
                all_globals = comm.allgather(local_globals) if comm is not None else [local_globals]
                result = _combine_custom_global_results(all_globals)
                if rank == 0:
                    result_path = output / (
                        f"derived_variables_rank{rank:04d}.jsonl" if size > 1 else "derived_variables.jsonl"
                    )
                    with result_path.open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps({"action": index, "time": snapshot.time, "rank": rank,
                                                "partition": None, "result": result}, default=str) + "\n")
                    outputs.append(json.dumps(result, default=str))
                continue
            if "field" in modes:
                for part, result in local_results:
                    if action.get("save_field"):
                        import vtk

                        field_name = result.get("name", action["function"])
                        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(field_name))
                        writer = vtk.vtkDataSetWriter()
                        writer.SetFileName(str(output / f"derived_custom_{safe_name}_rank{rank:04d}_part{part.index:04d}.vtk"))
                        writer.SetInputData(part.dataset)
                        writer.Write()
                    result_path = output / (
                        f"derived_variables_rank{rank:04d}.jsonl" if size > 1 else "derived_variables.jsonl"
                    )
                    with result_path.open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps({"action": index, "time": snapshot.time, "rank": rank,
                                                "partition": part.index, "result": result}, default=str) + "\n")
                continue
            outputs.append(f"Action {index}: rank {rank} assigned no data pieces.")
            continue

        aggregate_local = size > 1 or snapshot.path.suffix.lower() == ".vtm"
        if aggregate_local and kind in {"line_plot", "slice_contour", "azimuthal_average"}:
            label = f"_t{snapshot.time:g}" if snapshot.time is not None else ""
            if kind == "line_plot":
                line_action = dict(action)
                if line_action.get("resolution") is None:
                    local_bounds = None
                    local_points = 0
                    for part in selected_partitions:
                        if not part.dataset.GetNumberOfPoints():
                            continue
                        bounds = part.dataset.GetBounds()
                        if local_bounds is None:
                            local_bounds = list(bounds)
                        else:
                            for axis in range(6):
                                local_bounds[axis] = min(local_bounds[axis], bounds[axis]) if axis % 2 == 0 else max(local_bounds[axis], bounds[axis])
                        local_points += part.dataset.GetNumberOfPoints()
                    local_summary = (local_bounds, local_points)
                    summaries = comm.allgather(local_summary) if comm is not None else [local_summary]
                    usable = [item for item in summaries if item[0] is not None and item[1] > 0]
                    if usable:
                        global_bounds = [min(item[0][axis] for item in usable) if axis % 2 == 0
                                         else max(item[0][axis] for item in usable) for axis in range(6)]
                        diagonal = sum((global_bounds[axis + 1] - global_bounds[axis]) ** 2 for axis in (0, 2, 4)) ** 0.5
                        length = float(np.linalg.norm(np.asarray(action["end"]) - np.asarray(action["start"])))
                        spacing = diagonal / max(sum(item[1] for item in usable) ** 0.5, 2.0)
                        line_action["resolution"] = max(2, min(10000, int(np.ceil(length / max(spacing, length / 1000.0)))))
                local_samples = [sample_line(part.dataset, line_action) for part in selected_partitions
                                 if part.dataset.GetNumberOfPoints()]
                sample_groups = comm.gather(local_samples, root=0) if comm is not None else [local_samples]
                merge_error = None
                if rank == 0:
                    try:
                        all_samples = [group for rank_groups in sample_groups for group in rank_groups]
                        result = save_line_samples(_merge_line_samples(all_samples), action["field"], output, label)
                        outputs.append(str(result))
                    except Exception as exc:
                        merge_error = f"Could not combine distributed line samples: {type(exc).__name__}: {exc}"
                if comm is not None:
                    merge_error = comm.bcast(merge_error, root=0)
                if merge_error:
                    raise RequestError(merge_error)
                continue

            if kind == "slice_contour":
                local_slices = [sample_slice(part.dataset, action) for part in selected_partitions]
                sample_groups = comm.gather(local_slices, root=0) if comm is not None else [local_slices]
                merge_error = None
                if rank == 0:
                    try:
                        all_slices = [sample for rank_samples in sample_groups for sample in rank_samples]
                        result = save_slice_samples(all_slices, action, output, label)
                        outputs.append(str(result))
                    except Exception as exc:
                        merge_error = f"Could not combine distributed slice results: {type(exc).__name__}: {exc}"
                if comm is not None:
                    merge_error = comm.bcast(merge_error, root=0)
                if merge_error:
                    raise RequestError(merge_error)
                continue

            samples = [azimuthal_samples(part.dataset, action) for part in selected_partitions]
            local_samples = {
                name: np.concatenate([sample[name] for sample in samples]) if samples else np.empty(0)
                for name in ("radius", "theta", "values")
            }
            local_radius = local_samples["radius"]
            local_min = float(local_radius.min()) if local_radius.size else float("inf")
            local_max = float(local_radius.max()) if local_radius.size else float("-inf")
            if comm is not None:
                from mpi4py import MPI

                global_min = comm.allreduce(local_min, op=MPI.MIN)
                global_max = comm.allreduce(local_max, op=MPI.MAX)
            else:
                global_min, global_max = local_min, local_max
            if not np.isfinite(global_min) or not np.isfinite(global_max):
                raise RequestError("The requested azimuthal slice does not intersect the distributed mesh.")
            profile = azimuthal_profile(local_samples, action, (global_min, global_max))
            if comm is not None:
                sums, counts, angle_bins = (np.zeros_like(profile[key]) for key in ("sums", "counts", "angle_bins"))
                comm.Allreduce(profile["sums"], sums, op=MPI.SUM)
                comm.Allreduce(profile["counts"], counts, op=MPI.SUM)
                comm.Allreduce(profile["angle_bins"], angle_bins, op=MPI.SUM)
            else:
                sums, counts, angle_bins = profile["sums"], profile["counts"], profile["angle_bins"]
            merge_error = None
            if rank == 0:
                try:
                    global_profile = {"edges": profile["edges"], "sums": sums,
                                      "counts": counts, "angle_bins": angle_bins}
                    result = save_azimuthal_profile(global_profile, action, output, index,
                                                    angular_coverage(angle_bins))
                    outputs.append(str(result))
                except Exception as exc:
                    merge_error = f"Could not combine distributed azimuthal averages: {type(exc).__name__}: {exc}"
            if comm is not None:
                merge_error = comm.bcast(merge_error, root=0)
            if merge_error:
                raise RequestError(merge_error)
            continue

        if not current:
            outputs.append(f"Action {index}: rank {rank} assigned no data pieces.")
            continue
        for part in selected_partitions:
            label = f"_t{snapshot.time:g}" if snapshot.time is not None else ""
            if size > 1:
                label += f"_rank{rank:04d}_part{part.index:04d}"
            if kind == "line_plot":
                result = line_plot(part.dataset, action, output, label)
            elif kind == "slice_contour":
                result = slice_contour(part.dataset, action, output, label)
            elif kind == "threshold":
                result, selected = threshold(part.dataset, action, output, index * 1000000 + rank * 10000 + part.index)
                name = action.get("name", f"threshold_{index}")
                selections.setdefault(name, []).append(Partition(part.index, selected))
            elif kind == "streamlines":
                result = streamlines(part.dataset, action, output, index * 1000000 + rank * 10000 + part.index)
            elif kind == "azimuthal_average":
                result = azimuthal_average(part.dataset, action, output, index)
            elif kind == "derived":
                function = custom.load(action["function"], request.custom_registry)
                result = _add_custom_result(part.dataset, action["function"], function(part.dataset, request.constants))
                if "global" in result:
                    result = _reduce_custom_global(result, comm)
                if action.get("save_field") and "global" not in result:
                    import vtk

                    field_name = result.get("name", action["function"])
                    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(field_name))
                    writer = vtk.vtkDataSetWriter()
                    writer.SetFileName(str(output / f"derived_custom_{safe_name}_rank{rank:04d}_part{part.index:04d}.vtk"))
                    writer.SetInputData(part.dataset)
                    writer.Write()
                result_path = output / (f"derived_variables_rank{rank:04d}.jsonl" if size > 1 else "derived_variables.jsonl")
                if "global" not in result or rank == 0:
                    with result_path.open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps({"action": index, "time": snapshot.time, "rank": rank,
                                                "partition": part.index, "result": result}, default=str) + "\n")
                continue
            else:
                raise RequestError(f"Action {index}: unsupported runtime action {kind!r}.")
            outputs.append(str(result))
    elapsed = time.perf_counter() - started
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_bytes = int(rss if os.uname().sysname == "Darwin" else rss * 1024)
    host = socket.gethostname()
    stats = {"rank": rank, "host": host, "elapsed_seconds": elapsed,
             "input_case_bytes_total": kernel.input_bytes(), "partitions": len(current),
             "max_rss_bytes": rss_bytes, "nodes_requested": request.nodes,
             "threads_per_rank": request.cpus_per_node or request.cpus}
    (output / f"metrics_rank{rank:04d}.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    if comm is not None:
        all_outputs = comm.gather(outputs, root=0)
        all_stats = comm.gather(stats, root=0)
        comm.Barrier()
    else:
        all_outputs, all_stats = [outputs], [stats]
    if rank == 0:
        with log.open("w", encoding="utf-8") as stream:
            stream.write("Approved workflow completed.\n")
            stream.write("Actions executed in request order:\n")
            stream.writelines(f"  {i}. {action['type']} {action}\n" for i, action in enumerate(request.actions, 1))
            stream.write("Outputs:\n")
            stream.writelines(f"  {value}\n" for group in all_outputs for value in group)
            stream.write("Performance by MPI rank:\n")
            stream.writelines(f"  {json.dumps(item)}\n" for item in all_stats)
        job_metrics = {
            "elapsed_seconds": max(item["elapsed_seconds"] for item in all_stats),
            "input_case_bytes_total": all_stats[0]["input_case_bytes_total"],
            "peak_memory_bytes_one_rank": max(item["max_rss_bytes"] for item in all_stats),
            "sum_of_rank_peak_memory_bytes": sum(item["max_rss_bytes"] for item in all_stats),
            "nodes_requested": request.nodes,
            "nodes_observed": len({item["host"] for item in all_stats}),
            "mpi_ranks": size,
            "threads_per_rank": request.cpus_per_node or request.cpus,
        }
        (output / "performance.json").write_text(json.dumps(job_metrics, indent=2) + "\n", encoding="utf-8")
        _write_observations(output)
        if request_path is not None:
            copied = output / "request.executed.json"
            copied.write_text(json.dumps(request.as_dict(), indent=2) + "\n", encoding="utf-8")
    return log


