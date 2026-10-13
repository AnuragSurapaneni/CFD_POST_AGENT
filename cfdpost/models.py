"""Public request types and validation for agreed analysis workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET


class RequestError(ValueError):
    """A workflow is incomplete or internally inconsistent."""


@dataclass
class AnalysisRequest:
    input: str
    output: str
    actions: list[dict[str, Any]]
    cpus: int = 1
    approved: bool = False
    execution: str = "local"
    slurm_profile: str | None = None
    nodes: int = 1
    cpus_per_node: int | None = None
    slurm: dict[str, Any] = field(default_factory=dict)
    constants: dict[str, dict[str, Any]] = field(default_factory=dict)
    time_series: list[dict[str, Any]] | None = None
    custom_registry: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AnalysisRequest":
        required = {"input", "output", "actions"}
        missing = sorted(required - value.keys())
        if missing:
            raise RequestError("Missing required request fields: " + ", ".join(missing))
        req = cls(**{key: value[key] for key in cls.__dataclass_fields__ if key in value})
        req.validate()
        return req

    def validate(self) -> None:
        if not isinstance(self.input, str) or not isinstance(self.output, str):
            raise RequestError("Input and output must be filesystem paths.")
        if not self.input.strip():
            raise RequestError("Input path is required.")
        if not self.output.strip():
            raise RequestError("Output directory is required.")
        if "\n" in self.output or "\r" in self.output:
            raise RequestError("Output path cannot contain a newline.")
        if (not isinstance(self.cpus, int) or isinstance(self.cpus, bool) or not isinstance(self.nodes, int)
                or isinstance(self.nodes, bool) or self.cpus < 1 or self.nodes < 1):
            raise RequestError("CPU and node counts must be positive integers.")
        if self.execution not in {"local", "slurm"}:
            raise RequestError("execution must be 'local' or 'slurm'.")
        if self.execution == "slurm" and (not isinstance(self.cpus_per_node, int) or isinstance(self.cpus_per_node, bool)
                                            or self.cpus_per_node < 1):
            raise RequestError("cpus_per_node is required as a positive integer for Slurm execution.")
        if not isinstance(self.slurm, dict):
            raise RequestError("slurm settings must be a mapping.")
        if not self.actions:
            raise RequestError("Add at least one analysis action.")
        validate_input_path(self.input)
        available_times: list[float] | None = None
        timed_input = bool(self.time_series and len(self.time_series) > 1)
        if self.time_series is not None:
            try:
                available_times = [float(item["time"]) for item in self.time_series]
                series_files = [Path(item["file"]).expanduser() for item in self.time_series]
            except (KeyError, TypeError, ValueError) as exc:
                raise RequestError("Each time_series entry needs a numeric physical time and a file path.") from exc
            if any(not math.isfinite(value) for value in available_times):
                raise RequestError("time_series timestamps must be finite physical times.")
            if len(available_times) < 2:
                raise RequestError("time_series needs at least two snapshots; use .pvd metadata when available.")
            if any(b <= a for a, b in zip(available_times, available_times[1:])):
                raise RequestError("time_series timestamps must be strictly increasing.")
            missing_files = [str(path) for path in series_files if not path.is_file()]
            if missing_files:
                raise RequestError("Time series files do not exist: " + ", ".join(missing_files))
        source_path = Path(self.input).expanduser()
        if self.time_series is None and source_path.suffix.lower() == ".pvd" and source_path.is_file():
            try:
                available_times = [float(item.get("timestep")) for item in ET.parse(source_path).findall(".//Collection/DataSet")]
                if any(not math.isfinite(value) for value in available_times):
                    raise RequestError(f"Physical timestamps in {source_path} must be finite.")
                timed_input = len(available_times) > 1
            except ET.ParseError as exc:
                raise RequestError(f"Could not read physical timestamps from {source_path}: {exc}") from exc
            except (TypeError, ValueError) as exc:
                raise RequestError(f"Every PVD entry in {source_path} needs a numeric physical timestep.") from exc
        selection_times: dict[str, float | None] = {}
        for index, action in enumerate(self.actions, start=1):
            if not isinstance(action, dict):
                raise RequestError(f"Action {index} must be a mapping.")
            _validate_action(action, index)
            if action["type"] in {"mean", "rms"} and (available_times is None or len(available_times) < 2):
                raise RequestError(f"Action {index} ({action['type']}) needs at least two physical timestamps.")
            if timed_input and action["type"] not in {"mean", "rms"} and "time" not in action:
                raise RequestError(
                    f"Action {index} ({action['type']}) uses temporal input. Choose a physical 'time' before preparing the job."
                )
            if "time" in action:
                try:
                    requested_time = float(action["time"])
                except (TypeError, ValueError) as exc:
                    raise RequestError(f"Action {index}: time must be a numeric physical timestamp.") from exc
                if not math.isfinite(requested_time):
                    raise RequestError(f"Action {index}: physical time must be finite.")
                if available_times is None:
                    raise RequestError(f"Action {index}: a physical time cannot be selected from a single static input.")
                if requested_time not in available_times:
                    raise RequestError(f"Action {index}: time {requested_time} is unavailable; choose from {available_times}.")
            if "selection" in action:
                selection_name = action["selection"]
                if selection_name not in selection_times:
                    raise RequestError(f"Action {index}: selection {selection_name!r} must be created by an earlier threshold.")
                if action["type"] in {"mean", "rms"}:
                    raise RequestError("Temporal statistics over a threshold selection are not supported yet.")
                action_time = float(action["time"]) if "time" in action else None
                if action_time != selection_times[selection_name]:
                    raise RequestError(f"Action {index}: selection {selection_name!r} is tied to its threshold timestamp.")
            if action["type"] == "threshold":
                selection_times[action.get("name", f"threshold_{index}")] = (
                    float(action["time"]) if "time" in action else None
                )

    def as_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)


def _validate_action(action: dict[str, Any], index: int) -> None:
    kind = action.get("type")
    requirements: dict[str, tuple[str, ...]] = {
        "line_plot": ("field", "start", "end"),
        "slice_contour": ("field", "origin", "normal"),
        "threshold": ("field", "range"),
        "streamlines": ("field", "seeds"),
        "mean": ("field",),
        "rms": ("field",),
        "azimuthal_average": ("field", "axis", "origin", "slice"),
        "derived": ("function",),
    }
    if kind not in requirements:
        raise RequestError(f"Action {index}: unsupported action type {kind!r}.")
    missing = [key for key in requirements[kind] if key not in action]
    if missing:
        raise RequestError(f"Action {index} ({kind}): please provide " + ", ".join(missing) + ".")
    if "field" in action and (not isinstance(action["field"], str) or not action["field"].strip()):
        raise RequestError(f"Action {index}: field must be a non-empty name.")
    if kind == "derived" and (not isinstance(action["function"], str) or not action["function"].strip()):
        raise RequestError(f"Action {index}: function must be a registered name.")
    if kind == "streamlines":
        seeds = action["seeds"]
        if not isinstance(seeds, dict) or seeds.get("type") not in {"points", "line", "plane"}:
            raise RequestError(f"Action {index}: seeds need type 'points', 'line', or 'plane'.")
        if seeds["type"] == "points":
            points = seeds.get("points", [])
            if not points or any(not isinstance(point, (list, tuple)) or len(point) != 3 for point in points):
                raise RequestError(f"Action {index}: point seeds need one or more 3D coordinates.")
        if seeds["type"] == "line" and (len(seeds.get("start", [])) != 3 or len(seeds.get("end", [])) != 3):
            raise RequestError(f"Action {index}: line seeds need 3D start and end coordinates.")
        if seeds["type"] == "plane" and any(len(seeds.get(key, [])) != 3 for key in ("origin", "point1", "point2")):
            raise RequestError(f"Action {index}: plane seeds need 3D origin, point1, and point2 coordinates.")
    if kind == "threshold":
        bounds = action["range"]
        try:
            bounds = [float(value) for value in bounds]
        except (TypeError, ValueError) as exc:
            raise RequestError(f"Action {index}: threshold bounds must be numeric.") from exc
        if len(bounds) != 2 or any(not math.isfinite(value) for value in bounds) or bounds[0] > bounds[1]:
            raise RequestError(f"Action {index}: threshold range must be [minimum, maximum].")
    if kind == "line_plot":
        for key in ("start", "end"):
            if not isinstance(action[key], (list, tuple)) or len(action[key]) != 3:
                raise RequestError(f"Action {index}: line {key} must contain three coordinates.")
            try:
                coordinates = [float(value) for value in action[key]]
            except (TypeError, ValueError) as exc:
                raise RequestError(f"Action {index}: line {key} coordinates must be numeric.") from exc
            if any(not math.isfinite(value) for value in coordinates):
                raise RequestError(f"Action {index}: line coordinates must be finite.")
        if action.get("resolution") is not None:
            try:
                if int(action["resolution"]) < 2:
                    raise RequestError(f"Action {index}: line resolution must be at least 2.")
            except (TypeError, ValueError) as exc:
                raise RequestError(f"Action {index}: line resolution must be an integer.") from exc
    if kind == "slice_contour":
        if not isinstance(action["origin"], (list, tuple)) or not isinstance(action["normal"], (list, tuple)) or len(action["origin"]) != 3 or len(action["normal"]) != 3:
            raise RequestError(f"Action {index}: slice origin and normal must each have three coordinates.")
        try:
            if not all(math.isfinite(float(value)) for value in [*action["origin"], *action["normal"]]):
                raise RequestError(f"Action {index}: slice coordinates must be finite.")
        except (TypeError, ValueError) as exc:
            raise RequestError(f"Action {index}: slice coordinates must be numeric.") from exc
    if kind == "azimuthal_average":
        section = action["slice"]
        if (not isinstance(section, dict) or not isinstance(section.get("origin"), (list, tuple))
                or not isinstance(section.get("normal"), (list, tuple)) or len(section["origin"]) != 3
                or len(section["normal"]) != 3):
            raise RequestError(f"Action {index}: azimuthal averaging needs slice={{'origin': [x,y,z], 'normal': [nx,ny,nz]}}.")
        if not isinstance(action["axis"], (list, tuple)) or not isinstance(action["origin"], (list, tuple)) or len(action["axis"]) != 3 or len(action["origin"]) != 3:
            raise RequestError(f"Action {index}: azimuthal axis and origin must each have three coordinates.")
        coordinates = [*action["axis"], *action["origin"], *section["origin"], *section["normal"]]
        try:
            if any(not math.isfinite(float(value)) for value in coordinates):
                raise RequestError(f"Action {index}: azimuthal coordinates must be finite.")
            if sum(float(value) ** 2 for value in action["axis"]) == 0 or sum(float(value) ** 2 for value in section["normal"]) == 0:
                raise RequestError(f"Action {index}: azimuthal axis and slice normal must be nonzero.")
        except (TypeError, ValueError) as exc:
            raise RequestError(f"Action {index}: azimuthal coordinates must be numeric.") from exc
    if kind == "rms" and action.get("result") not in {None, "raw_rms", "fluctuation_rms"}:
        raise RequestError(f"Action {index}: RMS result must be raw_rms or fluctuation_rms.")
    if kind == "mean" and action.get("result") not in {None, "mean"}:
        raise RequestError(f"Action {index}: mean result must be 'mean'.")
    if kind in {"mean", "rms"} and action.get("spatial_weighting") not in {None, "uniform", "cell_measure"}:
        raise RequestError(f"Action {index}: spatial_weighting must be 'uniform' or 'cell_measure'.")
    if "selection" in action and not isinstance(action["selection"], str):
        raise RequestError(f"Action {index}: selection must name an earlier threshold action.")


def validate_input_path(path: str) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise RequestError(f"Input does not exist: {resolved}")
    if resolved.suffix.lower() not in {".vtk", ".pvtu", ".vtm", ".pvd"}:
        raise RequestError("Supported input extensions are .vtk, .pvtu, .vtm, and .pvd.")
    if resolved.suffix.lower() in {".pvtu", ".vtm", ".pvd"}:
        try:
            root = ET.parse(resolved).getroot()
        except ET.ParseError as exc:
            raise RequestError(f"Could not parse VTK collection file {resolved}: {exc}") from exc
        if resolved.suffix.lower() == ".pvtu":
            relatives = [node.get("Source") for node in root.findall(".//Piece")]
        else:
            relatives = [node.get("file") for node in root.findall(".//DataSet")]
        relatives = [value for value in relatives if value]
        if not relatives:
            raise RequestError(f"No referenced dataset files found in {resolved}.")
        missing = [(resolved.parent / value).resolve() for value in relatives
                   if not (resolved.parent / value).is_file()]
        if missing:
            raise RequestError(f"Referenced VTK piece files do not exist: {', '.join(map(str, missing))}")
    return resolved
