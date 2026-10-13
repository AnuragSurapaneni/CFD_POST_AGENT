# CFD Post-Processing Agent

This package turns a notebook-built or JSON analysis plan into a reviewed, reproducible job. The kernel reads VTK data and checks point and cell array sizes. Statistics and visualization code live in separate modules. Local execution runs after approval; HPC mode writes a Python request and a Slurm script for the user to submit.

## Install

Use the Python environment available on the workstation or cluster:

```bash
python -m pip install -e .
# Add mpi4py to environments that will run multi-rank jobs:
python -m pip install -e '.[mpi]'
```

VTK, NumPy, and Matplotlib are runtime dependencies. A cluster's MPI-enabled Python stack must also provide mpi4py and a Slurm-compatible MPI launch configuration.

## Notebook workflow

```python
from cfdpost import AnalysisSession

job = AnalysisSession("case.vtk", "post-results", cpus=8)
job.line_plot("pressure", [0.0, 0.0, 0.0], [1.0, 0.0, 0.0])
print(job.review())                 # inspect the ordered actions
job.approve()                       # required before a script can be generated
script = job.write()
# Or, after approval, run locally from the notebook:
# log = job.run()
```

Other methods include `slice_contour`, `threshold`, `streamlines`, `statistic("mean" | "rms", ...)`, `azimuthal_average`, and `derived`. Azimuthal averaging requires an explicit axis, centerline origin, and slice origin/normal. Line and slice operations accept an optional `time` when reading a `.pvd` collection. A temporal `mean` or `rms` action uses the physical timestamps from `.pvd` or an explicit `time_series=[{"time": ..., "file": ...}]` list. `rms` defaults to raw RMS; set `result="fluctuation_rms"` for fluctuation RMS. Temporal integration uses trapezoidal physical-time weights. Spatial summaries record `spatial_weighting`, which accepts `uniform` or `cell_measure` (volume, then area, then length for cells).

For HPC, create the session with `execution="slurm"`, `nodes`, and `cpus_per_node`, plus optional `slurm={"account": ..., "partition": ..., "time": ...}`. To persist stable settings between sessions, call `cfdpost.clusters.save_cluster("cluster-name", {"account": ..., "partition": ..., "modules": [...]})`, then pass `slurm_profile="cluster-name"`; values in the job's `slurm` mapping override that profile. `job.write()` creates `run_analysis.py`, `request.json`, and `submit.slurm`; it never submits the job.

## JSON and command line

`request.json` uses ordered `actions`, for example:

```json
{
  "input": "case.vtk",
  "output": "post-results",
  "cpus": 8,
  "approved": false,
  "actions": [
    {"type": "line_plot", "field": "pressure", "start": [0, 0, 0], "end": [1, 0, 0]}
  ]
}
```

Run `python -m cfdpost prepare request.json` to review the plan and approve interactively. The command writes the generated Python script and, for Slurm requests, a submission script. `python -m cfdpost execute request.json` only runs a request already marked approved. `python -m cfdpost run request.json` reviews, approves, prepares, then runs locally.

Generated jobs save line CSV/PNG, slice PNG, threshold VTK files, streamline VTP/PNG, azimuthal CSV, temporal-statistics CSV/NPZ, request copies, logs, performance metadata, and numerical observations as applicable. Custom functions can be registered from a Python file with `python -m cfdpost register-function NAME FILE FUNCTION`; they return a mapping containing point or cell `values`, or a `global` result. Multi-rank global results declare a reduction (`sum`, `min`, `max`, `mean`, or `identical`) so the kernel can combine rank-local results; a mean returns its local sum and count. `cfdpost.custom.kolmogorov_scales(nu, epsilon)` computes the Kolmogorov length, time, and velocity scales using SI inputs.

## Current boundaries

- MPI distributes `.pvtu` pieces and `.vtm` child datasets across ranks. VTM line samples, slices, and azimuthal profiles are combined into one output; explicit VTK ghost points and cells are removed before analysis.
- Monolithic legacy `.vtk` files remain single-rank inputs. A multi-rank request fails before reading with guidance to partition the dataset as `.pvtu` or as `.vtm` child datasets. This avoids having every MPI rank load the entire legacy file.
- Point and cell tuple counts are checked and inconsistencies stop processing without source repair. The code does not screen scientific data quality.
- Under MPI, line samples and slice contours are combined across rank partitions into one result. Streamline integration still follows each rank's local partition and can stop at partition boundaries; threshold selections remain reusable as rank partition files.
- A threshold selection can be reused by later actions at the same physical time. Thresholded temporal means/RMS are rejected rather than silently using a stale mask.
- Custom calculations can add point/cell fields to the active dataset for following actions in that same loaded snapshot. MPI custom source files must be visible at the same path on all ranks.
- The implementation reads one VTK partition at a time per rank and accumulates temporal statistic arrays for that partition. Memory use should be profiled on representative multi-terabyte cases before production deployment.
- Structured and unstructured legacy `.vtk`, partitioned `.pvtu`, XML multiblock `.vtm`, and `.pvd` time collections are recognized. Other formats are not enabled yet.

## Tests

Run `python -m unittest discover -s tests -v`. Reader distribution and single-rank multi-block acceptance checks run when VTK dependencies are installed. Run the two-rank workflow comparison in an MPI-enabled environment with `CFDPOST_RUN_MPI_TESTS=1`.
