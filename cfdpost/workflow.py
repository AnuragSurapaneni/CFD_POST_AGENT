"""Turn an approved plan into a reproducible job directory."""

from __future__ import annotations

import json
import shlex
from pathlib import Path

from .clusters import load_cluster
from .models import AnalysisRequest, RequestError, validate_input_path


def prepare(request: AnalysisRequest) -> Path:
    request.validate()
    if not request.approved:
        raise RequestError("Only an approved analysis plan can be prepared.")
    source = validate_input_path(request.input)
    out = Path(request.output).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    run_request = request.as_dict()
    run_request["input"] = str(source)
    run_request["output"] = str(out)
    if run_request.get("time_series"):
        for snapshot in run_request["time_series"]:
            snapshot["file"] = str(Path(snapshot["file"]).expanduser().resolve())
    registry = Path(".cfdpost/functions.json").resolve()
    if registry.is_file():
        run_request["custom_registry"] = str(registry)
    (out / "request.json").write_text(json.dumps(run_request, indent=2) + "\n", encoding="utf-8")
    script = out / "run_analysis.py"
    script.write_text(
        "#!/usr/bin/env python3\n\"\"\"Generated from the approved CFD post-processing plan.\"\"\"\n"
        "import subprocess\nimport sys\n\n"
        f"raise SystemExit(subprocess.call([sys.executable, '-m', 'cfdpost', 'execute', {str(out / 'request.json')!r}]))\n",
        encoding="utf-8",
    )
    if request.execution == "slurm":
        (out / "submit.slurm").write_text(_slurm(request, out), encoding="utf-8")
    return script


def _slurm(request: AnalysisRequest, out: Path) -> str:
    options = load_cluster(request.slurm_profile) if request.slurm_profile else {}
    options.update(request.slurm)
    job_name = str(options.get("job_name", "cfdpost"))
    time_limit = str(options.get("time", "01:00:00"))
    account = options.get("account")
    partition = options.get("partition")
    for option_name, option_value in (("job_name", job_name), ("time", time_limit),
                                      ("account", account), ("partition", partition)):
        if option_value is not None and any(character in str(option_value) for character in "\r\n"):
            raise RequestError(f"Slurm {option_name} cannot contain a newline.")
    command = f"srun python -m cfdpost execute {shlex.quote(str(out / 'request.json'))}"
    lines = [
        "#!/bin/bash",
        f"#SBATCH --job-name={job_name}",
        f"#SBATCH --nodes={request.nodes}",
        f"#SBATCH --ntasks={request.nodes}",
        "#SBATCH --ntasks-per-node=1",
        f"#SBATCH --cpus-per-task={int(request.cpus_per_node or request.cpus)}",
        f"#SBATCH --time={time_limit}",
        f"#SBATCH --output={shlex.quote(str(out / 'slurm-%j.out'))}",
    ]
    if account:
        lines.append(f"#SBATCH --account={account}")
    if partition:
        lines.append(f"#SBATCH --partition={partition}")
    lines.extend(["", "set -euo pipefail"])
    for module in options.get("modules", []):
        lines.append(f"module load {shlex.quote(str(module))}")
    lines.extend([command, ""])
    return "\n".join(lines)
