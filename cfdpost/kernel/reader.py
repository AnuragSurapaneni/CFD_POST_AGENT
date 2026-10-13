"""VTK readers with rank-aware input for partitioned and multiblock data."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from ..models import RequestError


@dataclass
class Snapshot:
    time: float | None
    path: Path


def snapshots(input_path: str, explicit: list[dict] | None = None) -> list[Snapshot]:
    if explicit:
        result = [Snapshot(float(item["time"]), Path(item["file"]).expanduser().resolve()) for item in explicit]
        return sorted(result, key=lambda item: item.time if item.time is not None else 0.0)
    path = Path(input_path).expanduser().resolve()
    if path.suffix.lower() != ".pvd":
        return [Snapshot(None, path)]
    root = ET.parse(path).getroot()
    collection = root.find(".//Collection")
    if collection is None:
        raise RequestError(f"No time collection found in {path}")
    result = []
    for item in collection.findall("DataSet"):
        time_value, filename = item.get("timestep"), item.get("file")
        if time_value is None or filename is None:
            raise RequestError(f"PVD entries require timestep and file attributes: {path}")
        result.append(Snapshot(float(time_value), (path.parent / filename).resolve()))
    if not result:
        raise RequestError(f"No snapshots listed in {path}")
    return sorted(result, key=lambda item: item.time or 0.0)


def pvtu_pieces(path: Path) -> list[Path]:
    root = ET.parse(path).getroot()
    pieces = [piece.get("Source") for piece in root.findall(".//Piece")]
    if not pieces or any(piece is None for piece in pieces):
        raise RequestError(f"No valid Piece Source entries found in {path}")
    return [(path.parent / piece).resolve() for piece in pieces]


def referenced_files(path: Path) -> list[Path]:
    """List an input manifest and all of its referenced VTK files."""
    return _referenced_files(path.resolve(), set())


def _referenced_files(path: Path, visited: set[Path]) -> list[Path]:
    if path in visited:
        return []
    visited.add(path)
    result = [path]
    ext = path.suffix.lower()
    if ext not in {".pvd", ".pvtu", ".vtm"}:
        return result
    root = ET.parse(path).getroot()
    if ext == ".pvtu":
        children = [node.get("Source") for node in root.findall(".//Piece")]
    else:
        children = [node.get("file") for node in root.findall(".//DataSet")]
    for child in children:
        if child:
            result.extend(_referenced_files((path.parent / child).resolve(), visited))
    return result


def _vtk():
    try:
        import vtk
    except ImportError as exc:
        raise RequestError("VTK is required to read datasets. Install the project dependencies with `python -m pip install -e .`.") from exc
    return vtk


def _check_reader_error(reader: object, path: Path) -> None:
    error_code = reader.GetErrorCode()
    if error_code:
        raise RequestError(
            f"Structural size mismatch or invalid VTK array data in {path}: "
            f"the VTK reader returned error code {error_code}. Source data was not changed."
        )


def read_snapshot(path: Path, *, rank: int = 0, size: int = 1) -> list[object]:
    vtk = _vtk()
    ext = path.suffix.lower()
    if ext == ".pvtu" and size > 1:
        reader = vtk.vtkXMLPUnstructuredGridReader()
        reader.SetFileName(str(path))
        reader.UpdatePiece(rank, size, 0)
        _check_reader_error(reader, path)
        result = [reader.GetOutput()]
    elif ext == ".vtm":
        reader = vtk.vtkXMLMultiBlockDataReader()
        reader.SetFileName(str(path))
        if size > 1:
            reader.UpdatePiece(rank, size, 0)
        else:
            reader.Update()
        _check_reader_error(reader, path)
        result = list(iter_datasets(reader.GetOutput()))
    elif size > 1 and ext == ".vtk":
        raise RequestError(
            f"MPI cannot safely distribute monolithic legacy .vtk input {path.name}: its reader loads the complete dataset "
            "on one process and does not provide rank-addressable pieces. Convert it to .pvtu or a .vtm with "
            "partitioned child datasets before a multi-rank run."
        )
    elif size > 1:
        raise RequestError(
            f"MPI execution requires rank-addressable pieces; {path.name} is not a supported partitioned input. "
            "Use .pvtu or .vtm with child datasets."
        )
    elif ext == ".pvtu":
        reader = vtk.vtkXMLPUnstructuredGridReader()
        reader.SetFileName(str(path))
        reader.Update()
        _check_reader_error(reader, path)
        result = [reader.GetOutput()]
    elif ext == ".vtk":
        reader = vtk.vtkDataSetReader()
        reader.SetFileName(str(path))
        reader.ReadAllScalarsOn()
        reader.ReadAllVectorsOn()
        reader.ReadAllFieldsOn()
        reader.Update()
        _check_reader_error(reader, path)
        result = [reader.GetOutput()]
    elif ext == ".vtu":
        reader = vtk.vtkXMLUnstructuredGridReader()
        reader.SetFileName(str(path))
        reader.Update()
        _check_reader_error(reader, path)
        result = [reader.GetOutput()]
    else:
        raise RequestError(f"No VTK reader is configured for {path.suffix} input.")
    for index, dataset in enumerate(result):
        validate_dataset(dataset, str(path))
        result[index] = remove_ghosts(dataset, str(path))
    return result


def remove_ghosts(dataset: object, source: str) -> object:
    """Remove explicitly marked overlap before local data reaches reductions."""
    if not any(
        attributes.GetArray("vtkGhostType") is not None
        for attributes in (dataset.GetPointData(), dataset.GetCellData())
    ):
        return dataset

    if not (dataset.IsA("vtkUnstructuredGrid") or dataset.IsA("vtkPolyData")):
        raise RequestError(
            f"Cannot safely remove ghost points or cells from {source}: {dataset.GetClassName()} has vtkGhostType data, "
            "but this dataset type is not supported for ghost removal."
        )
    vtk = _vtk()
    remover = vtk.vtkRemoveGhosts()
    remover.SetInputData(dataset)
    remover.Update()
    cleaned = dataset.NewInstance()
    cleaned.DeepCopy(remover.GetOutput())
    validate_dataset(cleaned, source)
    return cleaned


def iter_datasets(data_object: object) -> Iterator[object]:
    vtk = _vtk()
    if data_object is None:
        return
    if data_object.IsA("vtkDataSet"):
        yield data_object
    elif data_object.IsA("vtkMultiBlockDataSet"):
        iterator = data_object.NewIterator()
        iterator.VisitOnlyLeavesOn()
        iterator.SkipEmptyNodesOn()
        iterator.InitTraversal()
        while not iterator.IsDoneWithTraversal():
            value = iterator.GetCurrentDataObject()
            yield from iter_datasets(value)
            iterator.GoToNextItem()


def validate_dataset(dataset: object, source: str) -> None:
    points, cells = dataset.GetNumberOfPoints(), dataset.GetNumberOfCells()
    for association, attributes, expected in (
        ("point", dataset.GetPointData(), points),
        ("cell", dataset.GetCellData(), cells),
    ):
        for index in range(attributes.GetNumberOfArrays()):
            array = attributes.GetAbstractArray(index)
            actual = array.GetNumberOfTuples()
            if actual != expected:
                name = array.GetName() or f"array_{index}"
                raise RequestError(
                    f"Structural size mismatch in {source}: {association} array {name!r} has "
                    f"{actual} tuples; mesh has {expected} {association}s. Source data was not changed."
                )
