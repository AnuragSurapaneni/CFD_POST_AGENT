# 04: Calculate time-weighted means and RMS

**What to build:** An analyst can request temporal statistics over a fixed-mesh case and receive time-weighted fields and reproducibility details.

**Blocked by:** #03 Process a large case across MPI with bounded memory.

**Status:** ready-for-agent

**Completion:** verified

- [x] Physical timestamps from PVD or explicit time-series metadata are used for temporal weighting; missing physical times are rejected rather than inferred from filenames.
- [x] The workflow provides time-weighted mean, raw RMS, and fluctuation RMS for supported point and cell fields.
- [x] Missing physical time selection for a temporal action is reported before execution.
- [x] The CSV results record the statistic, time range, weighting method, and relevant inputs.

## Acceptance evidence

- `test_time_weighted_statistics_use_physical_timestamps` checks nonuniform timestamps, mean, raw RMS, fluctuation RMS, saved derived fields, and time range.
- `test_vtm_temporal_statistics_use_physical_times_across_all_blocks` checks point and cell statistics on multi-block temporal input.
- `test_temporal_line_plot_requires_physical_time_before_approval` verifies a temporal request without a physical time is rejected before approval.
