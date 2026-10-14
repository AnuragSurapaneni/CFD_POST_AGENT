# 09: Generate Slurm scripts for parallel workflows

**What to build:** An HPC user can configure cluster defaults and receive a Python script and Slurm script for a parallel analysis, then submit the Slurm job themselves.

**Blocked by:** #01 Run a local line-plot workflow from an agreed request; #03 Process a large case across MPI with bounded memory.

**Status:** ready-for-agent

**Completion:** verified

- [x] The user can save stable cluster settings and override them per job.
- [x] The generated Slurm script reflects node count, CPUs per node, and configured cluster settings.
- [x] The generated Python script runs the agreed workflow and writes to the selected output folder.
- [x] The agent does not submit the Slurm job automatically.

## Acceptance evidence

- `test_saved_cluster_profile_is_overridden_by_per_job_settings` checks saved defaults and per-job precedence.
- `test_slurm_script_uses_user_resources_and_does_not_submit` checks requested resources, generated Python request path/output, and that no `sbatch` submission is triggered.
