# 10: Summarize findings with supporting evidence

**What to build:** After an analysis completes, the analyst can review concise observations about patterns or outliers, each linked to the statistics and visualizations that support it.

**Blocked by:** #04 Calculate time-weighted means and RMS; #05 Analyze slices with contours and reusable thresholds; #06 Generate streamlines from chosen seeds; #07 Compute azimuthal averages on slices; #08 Add custom Python calculations as kernel variables.

**Status:** ready-for-agent

**Completion:** verified

- [x] The summary reports observations grounded in outputs from the completed workflow.
- [x] Each observation identifies the supporting statistic, variable, time selection, or visualization.
- [x] The wording presents observations for analyst evaluation rather than asserting definitive scientific conclusions.

## Acceptance evidence

- `test_composed_temporal_workflow_covers_derived_line_slice_threshold_streamline_and_average` checks that observations name the variable/statistic and physical time range, link the supporting CSV, and are framed for analyst evaluation.
