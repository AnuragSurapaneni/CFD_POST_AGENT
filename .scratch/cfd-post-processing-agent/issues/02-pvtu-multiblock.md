# 02: Read .pvtu and multi-block cases with size validation

**What to build:** The existing line-plot workflow can read the initial .pvtu and multi-block inputs, including point and cell fields, and report structural size mismatches before plotting.

**Blocked by:** #01 Run a local line-plot workflow from an agreed request.

**Status:** ready-for-agent

**Completion:** verified

- [x] The line-plot workflow accepts supported .pvtu and multi-block cases alongside .vtk input.
- [x] Point-field tuple counts are checked against mesh point counts; cell-field tuple counts are checked against mesh cell counts.
- [x] A mismatch stops the run with a clear diagnostic and does not alter source data.
- [x] Both valid and mismatched fixtures are demonstrated through the end-to-end workflow.

## Acceptance evidence

- `test_pvtu_line_workflow_reads_piece_and_writes_results` exercises valid point and cell fields through `.pvtu`.
- `test_vtm_single_rank_line_plots_combine_all_blocks_once` exercises multi-block input.
- `test_array_size_mismatch_stops_before_plotting_and_keeps_source` and `test_cell_array_size_mismatch_stops_before_plotting_and_keeps_source` verify point and cell tuple failures, diagnostics, and unchanged input files.
