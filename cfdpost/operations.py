"""VTK operations for reusable selection, streamlines, and radial profiles."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np

from .models import RequestError
from .plotting import association, field_values


def threshold(dataset: object, action: dict[str, Any], output: Path, index: int) -> tuple[Path, object]:
    import vtk

    assoc = association(dataset, action["field"], action.get("association"))
    alg = vtk.vtkThreshold()
    alg.SetInputData(dataset)
    alg.SetInputArrayToProcess(0, 0, 0, 0 if assoc == "point" else 1, action["field"])
    alg.SetLowerThreshold(float(action["range"][0]))
    alg.SetUpperThreshold(float(action["range"][1]))
    alg.SetThresholdFunction(vtk.vtkThreshold.THRESHOLD_BETWEEN)
    alg.Update()
    selected = alg.GetOutput()
    path = output / f"threshold_{index:02d}.vtk"
    writer = vtk.vtkDataSetWriter()
    writer.SetFileName(str(path))
    writer.SetInputData(selected)
    writer.Write()
    return path, selected


def streamlines(dataset: object, action: dict[str, Any], output: Path, index: int) -> Path:
    import vtk
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from vtk.util.numpy_support import vtk_to_numpy

    assoc = association(dataset, action["field"], action.get("association"))
    if assoc == "cell":
        converted = vtk.vtkCellDataToPointData()
        converted.SetInputData(dataset)
        converted.Update()
        dataset = converted.GetOutput()
    seed_spec = action["seeds"]
    source = vtk.vtkPolyData()
    points = vtk.vtkPoints()
    kind = seed_spec.get("type")
    if kind == "points":
        seeds = seed_spec.get("points", [])
        if not seeds:
            raise RequestError("Provide at least one streamline seed point.")
        for point in seeds:
            points.InsertNextPoint(*point)
        source.SetPoints(points)
    elif kind == "line":
        start, end = seed_spec.get("start"), seed_spec.get("end")
        if start is None or end is None:
            raise RequestError("Line streamline seeds require start and end coordinates.")
        source_gen = vtk.vtkLineSource()
        source_gen.SetPoint1(*start)
        source_gen.SetPoint2(*end)
        source_gen.SetResolution(int(seed_spec.get("count", 20)))
        source_gen.Update()
        source = source_gen.GetOutput()
    elif kind == "plane":
        origin, point1, point2 = seed_spec.get("origin"), seed_spec.get("point1"), seed_spec.get("point2")
        if not origin or not point1 or not point2:
            raise RequestError("Plane streamline seeds require origin, point1, and point2.")
        source_gen = vtk.vtkPlaneSource()
        source_gen.SetOrigin(*origin)
        source_gen.SetPoint1(*point1)
        source_gen.SetPoint2(*point2)
        source_gen.SetXResolution(int(seed_spec.get("x_count", 10)))
        source_gen.SetYResolution(int(seed_spec.get("y_count", 10)))
        source_gen.Update()
        source = source_gen.GetOutput()
    else:
        raise RequestError("Streamline seed type must be points, line, or plane.")
    tracer = vtk.vtkStreamTracer()
    tracer.SetInputData(dataset)
    tracer.SetSourceData(source)
    tracer.SetInputArrayToProcess(
        0, 0, 0, vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS, action["field"]
    )
    tracer.SetIntegratorTypeToRungeKutta45()
    tracer.SetMaximumPropagation(float(action.get("max_propagation", 1000.0)))
    tracer.SetInitialIntegrationStep(float(action.get("step", 0.1)))
    tracer.SetIntegrationDirectionToBoth()
    tracer.Update()
    lines = tracer.GetOutput()
    path = output / f"streamlines_{index:02d}.vtp"
    writer = vtk.vtkXMLPolyDataWriter()
    writer.SetFileName(str(path))
    writer.SetInputData(lines)
    writer.Write()
    fig = plt.figure(figsize=(7, 6))
    ax = fig.add_subplot(111, projection="3d")
    for cell_index in range(lines.GetNumberOfCells()):
        cell = lines.GetCell(cell_index)
        coords = vtk_to_numpy(lines.GetPoints().GetData())[[cell.GetPointId(i) for i in range(cell.GetNumberOfPoints())]]
        ax.plot(coords[:, 0], coords[:, 1], coords[:, 2], linewidth=0.7)
    ax.set(xlabel="x", ylabel="y", zlabel="z", title=f"Streamlines: {action['field']}")
    image = output / f"streamlines_{index:02d}.png"
    fig.tight_layout()
    fig.savefig(image, dpi=150)
    plt.close(fig)
    return image


def azimuthal_samples(dataset: object, action: dict[str, Any]) -> dict[str, np.ndarray]:
    import vtk
    from vtk.util.numpy_support import vtk_to_numpy

    section = action["slice"]
    section_origin = np.asarray(section["origin"], dtype=float)
    section_normal = np.asarray(section["normal"], dtype=float)
    if section_normal.shape != (3,) or np.linalg.norm(section_normal) == 0:
        raise RequestError("Azimuthal slice needs a nonzero 3D normal.")
    plane = vtk.vtkPlane()
    plane.SetOrigin(*section_origin)
    plane.SetNormal(*(section_normal / np.linalg.norm(section_normal)))
    cutter = vtk.vtkCutter()
    cutter.SetCutFunction(plane)
    cutter.SetInputData(dataset)
    cutter.Update()
    sliced = cutter.GetOutput()
    if sliced.GetNumberOfCells() == 0:
        return {"radius": np.empty(0), "theta": np.empty(0), "values": np.empty(0)}
    assoc, values = field_values(sliced, action["field"], action.get("association"))
    if assoc == "point":
        coordinates = vtk_to_numpy(sliced.GetPoints().GetData())
    else:
        centers = vtk.vtkCellCenters()
        centers.SetInputData(sliced)
        centers.Update()
        coordinates = vtk_to_numpy(centers.GetOutput().GetPoints().GetData())
    origin = np.asarray(action["origin"], dtype=float)
    axis = np.asarray(action["axis"], dtype=float)
    axis /= np.linalg.norm(axis)
    relative = coordinates - origin
    radial = relative - (relative @ axis)[:, None] * axis
    radius = np.linalg.norm(radial, axis=1)
    reference = np.array([1.0, 0, 0]) if abs(axis[0]) < 0.9 else np.array([0, 1.0, 0])
    first_basis = np.cross(axis, reference)
    first_basis /= np.linalg.norm(first_basis)
    second_basis = np.cross(axis, first_basis)
    theta = np.mod(np.arctan2(radial @ second_basis, radial @ first_basis), 2 * np.pi)
    scalar = np.linalg.norm(values, axis=1) if values.ndim > 1 else values.astype(float)
    return {"radius": radius, "theta": theta, "values": scalar}


def azimuthal_profile(samples: dict[str, np.ndarray], action: dict[str, Any],
                      radius_range: tuple[float, float] | None = None) -> dict[str, np.ndarray]:
    radius, theta, values = samples["radius"], samples["theta"], samples["values"]
    if radius_range is None:
        if not radius.size:
            raise RequestError("The requested azimuthal slice does not intersect the mesh.")
        low, high = float(radius.min()), float(radius.max())
    else:
        low, high = radius_range
    if high <= low:
        high = low + max(abs(low), 1.0) * np.finfo(float).eps
    if "spacing" in action:
        spacing = float(action["spacing"])
        if spacing <= 0:
            raise RequestError("Radial spacing must be positive.")
        bin_count = max(1, int(np.ceil((high - low) / spacing)))
    else:
        bin_count = int(action.get("bins", 100))
        if bin_count < 1:
            raise RequestError("Radial bin count must be positive.")
    edges = np.linspace(low, high + np.finfo(float).eps, bin_count + 1)
    indices = np.clip(np.digitize(radius, edges) - 1, 0, bin_count - 1)
    sums = np.bincount(indices, weights=values, minlength=bin_count).astype(float)
    counts = np.bincount(indices, minlength=bin_count).astype(np.int64)
    angle_bins = np.zeros(3600, dtype=np.int64)
    if theta.size:
        angle_bins = np.histogram(theta, bins=len(angle_bins), range=(0, 2 * np.pi))[0].astype(np.int64)
    return {"edges": edges, "sums": sums, "counts": counts, "angle_bins": angle_bins}


def angular_coverage(angle_bins: np.ndarray) -> float:
    occupied = np.flatnonzero(angle_bins)
    if not len(occupied):
        return 0.0
    bin_width = 2 * np.pi / len(angle_bins)
    gaps = np.diff(np.r_[occupied, occupied[0] + len(angle_bins)])
    return float(2 * np.pi - (int(gaps.max()) - 1) * bin_width)


def save_azimuthal_profile(profile: dict[str, np.ndarray], action: dict[str, Any], output: Path,
                           index: int, coverage: float) -> Path:
    if action.get("full_circumference") and coverage < 2 * np.pi * 0.95 and not action.get("accept_partial_as_full"):
        raise RequestError(f"Available angular coverage is {np.degrees(coverage):.1f} degrees; confirm partial-sector interpretation.")
    centers = 0.5 * (profile["edges"][:-1] + profile["edges"][1:])
    means = np.divide(profile["sums"], profile["counts"], out=np.full(len(profile["counts"]), np.nan),
                      where=profile["counts"] > 0)
    path = output / f"azimuthal_{index:02d}.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["radius", action["field"] + "_mean", "sample_count", "angular_coverage_degrees",
                         "full_circumference_interpretation"])
        writer.writerows((r, v, c, np.degrees(coverage), bool(action.get("full_circumference")))
                         for r, v, c in zip(centers, means, profile["counts"]))
    return path


def azimuthal_average(dataset: object, action: dict[str, Any], output: Path, index: int) -> Path:
    samples = azimuthal_samples(dataset, action)
    profile = azimuthal_profile(samples, action)
    return save_azimuthal_profile(profile, action, output, index, angular_coverage(profile["angle_bins"]))
