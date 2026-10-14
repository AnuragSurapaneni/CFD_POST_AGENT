# 12: Run multi-rank acceptance tests for distributed VTK inputs

**What to build:** Make the supported `.pvtu` and `.vtm` MPI workflows verifiable on an MPI-enabled runner, including rank-local reads, collective outputs, and temporal statistics. The existing `.vtm` end-to-end test is opt-in and the `.pvtu` coverage currently stops at reader rank requests.

**Blocked by:** #11 Run .pvtu, .vtk, and .vtm cases across MPI ranks.

**Status:** ready-for-agent

- [ ] Add a dedicated test command or CI job that requires a working two-rank MPI runtime and fails if MPI tests are skipped.
- [ ] Run an end-to-end `.pvtu` workflow with point and cell fields across two ranks; include line sampling and compare its numeric output to the single-rank result.
- [ ] Run an end-to-end `.vtm` temporal workflow across two ranks; compare line samples and time-weighted mean/RMS results to single-rank outputs within stated tolerances.
- [ ] Cover uneven block assignment, a rank with no local blocks, and ghost-marked overlap without losing or double-counting data.
- [ ] Verify requested rank count, one copy of each aggregate output, and per-rank metrics with a single job summary.
- [ ] Document the command and supported MPI runtime needed to execute the acceptance suite on a developer machine or HPC login/compute environment.

