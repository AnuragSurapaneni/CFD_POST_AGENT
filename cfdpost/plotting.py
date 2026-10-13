"""Visualization outputs. This module does not import the statistics module."""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

import numpy as np

from .models import RequestError


def association(dataset: object, name: str, requested: str | None = None) -> str:
    point = dataset.GetPointData().GetArray(name) is not None
    cell = dataset.GetCellData().GetArray(name) is not None
    if requested:
        if requested not in {"point", "cell"}:
            raise RequestError("association must be 'point' or 'cell'.")
        if not (point if requested == "point" else cell):
            raise RequestError(f"Field {name!r} is not available as {requested} data.")
        return requested
    if point and cell:
        raise RequestError(f"Field {name!r} exists as both point and cell data; specify association.")
    if point:
        return "point"
    if cell:
        return "cell"
    raise RequestError(f"Field {name!r} was not found. Available point fields: {array_names(dataset.GetPointData())}; "
                       f"cell fields: {array_names(dataset.GetCellData())}.")


def array_names(attributes: object) -> list[str]:
    return [attributes.GetArrayName(i) or f"array_{i}" for i in range(attributes.GetNumberOfArrays())]


def field_values(dataset: object, name: str, association_name: str | None = None) -> tuple[str, np.ndarray]:
    assoc = association(dataset, name, association_name)
    from vtk.util.numpy_support import vtk_to_numpy

    source = dataset.GetPointData() if assoc == "point" else dataset.GetCellData()
    return assoc, np.asarray(vtk_to_numpy(source.GetArray(name)))


def _component(values: np.ndarray, action: dict[str, Any]) -> np.ndarray:
    if values.ndim == 1:
        return values.astype(float)
    component = action.get("component", "magnitude")
    if component == "magnitude":
        return np.linalg.norm(values, axis=1)
    if isinstance(component, int) and 0 <= component < values.shape[1]:
        return values[:, component].astype(float)
    raise RequestError(f"Invalid component {component!r}; choose an index or 'magnitude'.")


def line_plot(dataset: object, action: dict[str, Any], output: Path, label: str = "") -> Path:
    return save_line_samples(sample_line(dataset, action), action["field"], output, label)


def sample_line(dataset: object, action: dict[str, Any]) -> dict[str, np.ndarray | None]:
    import vtk
    from vtk.util.numpy_support import vtk_to_numpy

    start, end = np.asarray(action["start"], dtype=float), np.asarray(action["end"], dtype=float)
    if start.shape != (3,) or end.shape != (3,):
        raise RequestError("Line start and end must each have three coordinates.")
    length = float(np.linalg.norm(end - start))
    if length == 0:
        raise RequestError("Line start and end coordinates must differ.")
    resolution = action.get("resolution")
    if resolution is None and dataset.GetNumberOfPoints():
        bounds = dataset.GetBounds()
        diagonal = math.sqrt(sum((bounds[i + 1] - bounds[i]) ** 2 for i in (0, 2, 4)))
        spacing = diagonal / max(math.sqrt(max(dataset.GetNumberOfPoints(), 2)), 2.0)
        resolution = max(2, min(10000, int(math.ceil(length / max(spacing, length / 1000.0)))))
    elif resolution is None:
        resolution = 100
    if int(resolution) < 2:
        raise RequestError("Line resolution must be at least 2.")
    has_field = (dataset.GetPointData().GetArray(action["field"]) is not None or
                 dataset.GetCellData().GetArray(action["field"]) is not None)
    if not has_field and dataset.GetNumberOfPoints() == 0 and dataset.GetNumberOfCells() == 0:
        assoc = action.get("association", "point")
    else:
        assoc = association(dataset, action["field"], action.get("association"))
    line = vtk.vtkLineSource()
    line.SetPoint1(*start)
    line.SetPoint2(*end)
    line.SetResolution(int(resolution))
    probe = vtk.vtkProbeFilter()
    probe.SetInputConnection(line.GetOutputPort())
    probe.SetSourceData(dataset)
    probe.Update()
    sampled = probe.GetOutput()
    attrs = sampled.GetPointData() if assoc == "point" else sampled.GetPointData()
    values = attrs.GetArray(action["field"])
    valid = attrs.GetArray("vtkValidPointMask")
    coords = vtk_to_numpy(sampled.GetPoints().GetData())
    if values is None:
        scalar = None
        mask = np.zeros(len(coords), dtype=bool)
    else:
        scalar = _component(vtk_to_numpy(values), action)
        mask = vtk_to_numpy(valid).astype(bool) if valid is not None else np.zeros(len(coords), dtype=bool)
    distance = np.linalg.norm(coords - start, axis=1)
    return {"distance": distance, "coordinates": coords, "values": scalar, "valid": mask}


def save_line_samples(samples: dict[str, np.ndarray | None], field: str, output: Path, label: str = "") -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    coords, distance = samples["coordinates"], samples["distance"]
    values, mask = samples["values"], samples["valid"]
    if values is None:
        raise RequestError(f"No partition contained samples for field {field!r} on the requested line.")
    csv_path = output / f"line{label}_{_safe(field)}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["distance", "x", "y", "z", field, "valid"])
        writer.writerows(zip(distance, coords[:, 0], coords[:, 1], coords[:, 2], values, mask))
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(distance[mask], values[mask])
    ax.set(xlabel="Distance along line", ylabel=field, title=f"{field} along line")
    ax.grid(True, alpha=0.25)
    png_path = output / f"line{label}_{_safe(field)}.png"
    fig.tight_layout()
    fig.savefig(png_path, dpi=160)
    plt.close(fig)
    return png_path


def slice_contour(dataset: object, action: dict[str, Any], output: Path, label: str = "") -> Path:
    return save_slice_samples([sample_slice(dataset, action)], action, output, label)


def sample_slice(dataset: object, action: dict[str, Any]) -> dict[str, np.ndarray]:
    import vtk
    from vtk.util.numpy_support import vtk_to_numpy

    origin, normal = np.asarray(action["origin"], float), np.asarray(action["normal"], float)
    if origin.shape != (3,) or normal.shape != (3,) or np.linalg.norm(normal) == 0:
        raise RequestError("Slice origin and nonzero normal must each have three coordinates.")
    has_field = (dataset.GetPointData().GetArray(action["field"]) is not None or
                 dataset.GetCellData().GetArray(action["field"]) is not None)
    if not has_field and dataset.GetNumberOfPoints() == 0 and dataset.GetNumberOfCells() == 0:
        return {"xy": np.empty((0, 2)), "values": np.empty(0), "triangles": np.empty((0, 3), dtype=int)}
    assoc = association(dataset, action["field"], action.get("association"))
    plane = vtk.vtkPlane()
    plane.SetOrigin(*origin)
    plane.SetNormal(*(normal / np.linalg.norm(normal)))
    cutter = vtk.vtkCutter()
    cutter.SetCutFunction(plane)
    cutter.SetInputData(dataset)
    cutter.Update()
    triangle_filter = vtk.vtkTriangleFilter()
    triangle_filter.SetInputConnection(cutter.GetOutputPort())
    triangle_filter.Update()
    sliced = triangle_filter.GetOutput()
    if sliced.GetNumberOfCells() == 0 or sliced.GetNumberOfPoints() < 3 or sliced.GetPolys().GetNumberOfCells() == 0:
        return {"xy": np.empty((0, 2)), "values": np.empty(0), "triangles": np.empty((0, 3), dtype=int)}
    if assoc == "cell":
        to_point = vtk.vtkCellDataToPointData()
        to_point.SetInputData(sliced)
        to_point.Update()
        sliced = to_point.GetOutput()
    array = sliced.GetPointData().GetArray(action["field"])
    if array is None:
        raise RequestError(f"The requested slice does not contain field {action['field']!r}.")
    points = vtk_to_numpy(sliced.GetPoints().GetData())
    values = _component(vtk_to_numpy(array), action)
    direction = normal / np.linalg.norm(normal)
    trial = np.array([1.0, 0.0, 0.0]) if abs(direction[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = np.cross(direction, trial)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(direction, e1)
    relative = points - origin
    xy = np.column_stack((relative @ e1, relative @ e2))
    triangle_cells = vtk_to_numpy(sliced.GetPolys().GetData()).reshape(-1, 4)[:, 1:]
    return {"xy": xy, "values": values, "triangles": triangle_cells}


def save_slice_samples(groups: list[dict[str, np.ndarray]], action: dict[str, Any], output: Path,
                       label: str = "") -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.tri as mtri

    coordinates, field_values, triangle_groups = [], [], []
    offset = 0
    for group in groups:
        if not len(group["xy"]) or not len(group["triangles"]):
            continue
        coordinates.append(group["xy"])
        field_values.append(group["values"])
        triangle_groups.append(group["triangles"] + offset)
        offset += len(group["xy"])
    if not coordinates:
        raise RequestError(f"The requested slice has too few samples for {action['field']!r}.")
    xy = np.concatenate(coordinates)
    values = np.concatenate(field_values)
    triangles = np.concatenate(triangle_groups)
    fig, ax = plt.subplots(figsize=(7, 6))
    triangulation = mtri.Triangulation(xy[:, 0], xy[:, 1], triangles=triangles)
    kwargs = {"levels": action.get("levels", 20)}
    scale = action.get("scale")
    if scale and len(scale) == 2:
        kwargs.update(vmin=scale[0], vmax=scale[1])
    contour = ax.tricontourf(triangulation, values, **kwargs)
    fig.colorbar(contour, ax=ax, label=action["field"])
    ax.set(aspect="equal", xlabel="Slice coordinate 1", ylabel="Slice coordinate 2", title=action["field"])
    path = output / f"slice{label}_{_safe(action['field'])}.png"
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _safe(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in value)
