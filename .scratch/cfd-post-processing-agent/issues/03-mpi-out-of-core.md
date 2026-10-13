# 03: Process a large case across MPI with bounded memory

**What to build:** An analyst can run the line-plot workflow over a large case using selected resources, while the system reads and processes partitions without requiring the full case in memory.

**Blocked by:** #02 Read .pvtu and multi-block cases with size validation.

**Status:** ready-for-agent

- [ ] The user can select the node and CPU resources for the run.
- [ ] MPI distributes one case across selected nodes and the workflow returns the requested line plot and samples.
- [ ] Input is read in place unless the execution environment requires staging.
- [ ] Each run records elapsed time, data processed, memory use, and node count.
- [ ] A bounded-memory representative run verifies the behavior without requiring a multi-terabyte test fixture.
