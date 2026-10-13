"""Notebook-friendly interface for building, reviewing, and approving a job."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import AnalysisRequest, RequestError


class AnalysisSession:
    """Collect actions in order and expose the exact plan before execution.

    Typical notebook use::

        job = AnalysisSession("case.pvtu", "results", cpus=8)
        job.line_plot("Pressure", [0, 0, 0], [1, 0, 0])
        print(job.review())
        job.approve()
        job.write()
    """

    def __init__(self, input: str, output: str, *, cpus: int = 1, execution: str = "local",
                 nodes: int = 1, cpus_per_node: int | None = None, slurm: dict[str, Any] | None = None,
                 slurm_profile: str | None = None,
                 constants: dict[str, dict[str, Any]] | None = None, time_series: list[dict[str, Any]] | None = None) -> None:
        self._data: dict[str, Any] = {
            "input": input,
            "output": output,
            "cpus": cpus,
            "actions": [],
            "approved": False,
            "execution": execution,
            "slurm_profile": slurm_profile,
            "nodes": nodes,
            "cpus_per_node": cpus_per_node,
            "slurm": slurm or {},
            "constants": constants or {},
            "time_series": time_series,
        }

    def add(self, action: dict[str, Any]) -> "AnalysisSession":
        self._data["actions"].append(action)
        self._data["approved"] = False
        return self

    def line_plot(self, field: str, start: list[float], end: list[float], **options: Any) -> "AnalysisSession":
        return self.add({"type": "line_plot", "field": field, "start": start, "end": end, **options})

    def slice_contour(self, field: str, origin: list[float], normal: list[float], **options: Any) -> "AnalysisSession":
        return self.add({"type": "slice_contour", "field": field, "origin": origin, "normal": normal, **options})

    def threshold(self, field: str, value_range: list[float], **options: Any) -> "AnalysisSession":
        return self.add({"type": "threshold", "field": field, "range": value_range, **options})

    def streamlines(self, field: str, seeds: dict[str, Any], **options: Any) -> "AnalysisSession":
        return self.add({"type": "streamlines", "field": field, "seeds": seeds, **options})

    def statistic(self, kind: str, field: str, **options: Any) -> "AnalysisSession":
        if kind not in {"mean", "rms"}:
            raise RequestError("Statistic kind must be 'mean' or 'rms'.")
        return self.add({"type": kind, "field": field, **options})

    def azimuthal_average(self, field: str, axis: list[float], origin: list[float],
                          slice: dict[str, Any], **options: Any) -> "AnalysisSession":
        return self.add({"type": "azimuthal_average", "field": field, "axis": axis, "origin": origin,
                         "slice": slice, **options})

    def derived(self, function: str, **options: Any) -> "AnalysisSession":
        return self.add({"type": "derived", "function": function, **options})

    def register_function(self, name: str, function: Any) -> Path:
        """Persist a Python function defined in this notebook as a reusable kernel variable."""
        from .custom import register_callable

        return register_callable(name, function)

    def request(self, **options: Any) -> "AnalysisSession":
        self._data.update(options)
        self._data["approved"] = False
        return self

    def review(self) -> str:
        req = AnalysisRequest.from_dict(self._data)
        resource_line = (f"Local CPUs: {req.cpus}" if req.execution == "local" else
                         f"Slurm nodes: {req.nodes}; CPUs per node: {req.cpus_per_node}")
        lines = [f"Input: {req.input}", f"Output: {req.output}", f"Execution: {req.execution}", resource_line, "Actions:"]
        lines.extend(f"  {number}. {action['type']}: {action}" for number, action in enumerate(req.actions, 1))
        return "\n".join(lines)

    def approve(self) -> "AnalysisSession":
        AnalysisRequest.from_dict(self._data)
        self._data["approved"] = True
        return self

    def write(self) -> str:
        from .workflow import prepare

        if not self._data.get("approved"):
            raise RequestError("Review the plan and call approve() before preparing a job.")
        return str(prepare(AnalysisRequest.from_dict(self._data)))

    def run(self) -> Path:
        """Prepare and run the approved workflow locally in the current notebook kernel."""
        from .executor import execute
        from .workflow import prepare

        if not self._data.get("approved"):
            raise RequestError("Review the plan and call approve() before running a job.")
        request = AnalysisRequest.from_dict(self._data)
        if request.execution != "local":
            raise RequestError("Slurm plans generate scripts for you to submit; use write() instead of run().")
        prepare(request)
        try:
            return execute(request)
        except Exception as exc:
            output = Path(request.output).expanduser()
            output.mkdir(parents=True, exist_ok=True)
            (output / "run-error.log").write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
            raise
