# 03: Process a large case across MPI with bounded memory

**What to build:** An analyst can run the line-plot workflow over a large case using selected resources, while the system reads and processes partitions without requiring the full case in memory.

**Blocked by:** #02 Read .pvtu and multi-block cases with size validation.

**Status:** ready-for-agent

**Completion:** partial

- [x] The user can select the node and CPU resources for the run.
- [ ] MPI distributes one case across selected nodes and the workflow returns the requested line plot and samples.
- [x] Input is read in place unless the execution environment requires staging.
- [x] Each run records elapsed time, input bytes, memory use, and requested/observed node count.
- [ ] A bounded-memory representative run verifies the behavior without requiring a multi-terabyte test fixture.

## Acceptance evidence

- `test_slurm_script_uses_user_resources_and_does_not_submit` and `test_approved_vtk_line_workflow_writes_csv_png_script_and_log` cover resource selection and telemetry.
- `test_pvtu_line_workflow_reads_piece_and_writes_results` checks successful processing leaves its input manifest unchanged.
- `test_user_temporal_pvtu_fixture_supports_serial_line_slice_and_statistics` confirms the supplied temporal `.pvtu` data works through the serial workflow for line, slice, mean, and raw RMS.
- `test_vtm_reader_assigns_blocks_to_distinct_rank_requests`, `test_vtm_reader_preserves_uneven_and_empty_rank_assignments`, and `test_pvtu_reader_distributes_piece_requests_across_ranks` cover rank assignment at the reader seam.
- `test_vtm_workflow_matches_single_rank_outputs_across_mpi_ranks` and `test_user_pvtu_temporal_workflow_matches_single_rank_outputs` are opt-in end-to-end MPI comparisons. The latter uses the temporal dataset in `data/vtk/` and compares a two-rank `.pvtu` line plot, slice, and point statistics with serial output. Its launch was attempted with `CFDPOST_RUN_MPI_TESTS=1`, but the local MPI runtime failed to bind a socket (`Operation not permitted`) before either rank started. No bounded-memory MPI run has been verified; those criteria remain open.
