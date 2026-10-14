# 08: Add custom Python calculations as kernel variables

**What to build:** An analyst can register a custom Python calculation and use its output as a named variable in later statistics and visualizations.

**Blocked by:** #03 Process a large case across MPI with bounded memory.

**Status:** ready-for-agent

**Completion:** partial

- [x] Users can register functions from a Python file and reuse them across analysis sessions.
- [x] A function can return point data, cell data, or a global result.
- [ ] The kernel handles partitioning and supported global reductions for registered functions across MPI ranks.
- [x] The returned variable is available to later plots and statistics.
- [x] A requested derived field is saved as a VTK dataset when possible.

## Acceptance evidence

- `test_composed_temporal_workflow_covers_derived_line_slice_threshold_streamline_and_average` checks point data from a registered function reused by a later line plot.
- `test_custom_cell_variable_is_saved_and_reused_by_a_later_plot` verifies file registration survives into a second analysis request, a cell field is plotted, and the derived VTK file contains expected values.
- `test_vtm_custom_global_results_combine_all_blocks` verifies a global sum over multiple VTM blocks.
- Cross-rank custom reductions remain unverified because the opt-in MPI integration test was skipped; this criterion remains open with ticket #03.
