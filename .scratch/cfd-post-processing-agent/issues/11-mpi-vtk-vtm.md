# 11: Run .pvtu, .vtk, and .vtm cases across MPI ranks

**What to build:** Extend the MPI execution path so one analysis can process `.pvtu`, `.vtk`, and `.vtm` inputs across the user-selected ranks. The reader distributes work according to each format's structure, and statistics and visualization consume the same distributed kernel data without depending on each other.

**Blocked by:** #02 Read .pvtu and multi-block cases with size validation; #03 Process a large case across MPI with bounded memory; #09 Generate Slurm scripts for parallel workflows.

**Status:** ready-for-agent

- [ ] The agreed workflow accepts `.pvtu` and `.vtm` inputs in single-rank and multi-rank runs, and `.vtk` in single-rank runs, including temporal cases with physical timestamps. Monolithic legacy `.vtk` multi-rank runs fail clearly because the format has no rank-addressable pieces.
- [ ] The reader distributes datasets or blocks across ranks using a format-aware strategy; it does not silently load a full large case independently on every rank.
- [ ] Point and cell fields retain their associations and pass structural size validation after distribution. Invalid tuple counts produce a clear error before analysis.
- [ ] Global statistics and sampled or plotted outputs combine rank-local contributions without losing or double-counting mesh data, including shared boundaries and ghost cells where present.
- [ ] Statistics and visualization can run independently on the distributed kernel interface; requesting either module does not require running the other.
- [ ] Each rank-distributed format has a representative multi-rank acceptance fixture with point and cell fields. One-rank and multi-rank results agree within documented numerical tolerances; the unsupported monolithic `.vtk` layout has a clear-failure fixture.
- [ ] A format or dataset layout that cannot be distributed safely fails with a clear explanation instead of silently falling back to replicated full-case reads.
- [ ] The generated Python and Slurm scripts use the requested MPI rank count, and job outputs and performance measurements are written once without rank-level duplication.

## Implementation notes

The current implementation distributes `.pvtu` pieces and `.vtm` child datasets, removes supported ghost cells before analysis, and refuses monolithic legacy `.vtk` under MPI rather than replicating the full dataset on each rank. The two-rank end-to-end `.vtm` comparison is opt-in with `CFDPOST_RUN_MPI_TESTS=1`; it has not been run on this machine because the local MPI runtime cannot open its communication sockets. Reader-level rank-assignment fixtures run without launching MPI.
