# 09: Generate Slurm scripts for parallel workflows

**What to build:** An HPC user can configure cluster defaults and receive a Python script and Slurm script for a parallel analysis, then submit the Slurm job themselves.

**Blocked by:** #01 Run a local line-plot workflow from an agreed request; #03 Process a large case across MPI with bounded memory.

**Status:** ready-for-agent

- [ ] The user can save stable cluster settings and override them per job.
- [ ] The generated Slurm script reflects node count, CPUs per node, and configured cluster settings.
- [ ] The generated Python script runs the agreed workflow and writes to the selected output folder.
- [ ] The agent does not submit the Slurm job automatically.
