# 05: Analyze slices with contours and reusable thresholds

**What to build:** An analyst can inspect a scalar field on an arbitrary slice, save a contour image, and reuse a threshold selection in later operations.

**Blocked by:** #03 Process a large case across MPI with bounded memory.

**Status:** ready-for-agent

**Completion:** verified

- [x] A slice is defined by an origin and orientation.
- [x] The analyst selects a scalar field; missing or ambiguous field associations produce an actionable request for clarification.
- [x] The workflow saves a filled 2D contour image and supports shared scales for comparisons or automatic scales per image.
- [x] A requested threshold selects values within its range and can be reused by later plots and calculations.

## Acceptance evidence

- `test_composed_temporal_workflow_covers_derived_line_slice_threshold_streamline_and_average` saves arbitrary slices at two physical times with a shared explicit scale, reuses a threshold selection in a later line plot, and writes contour images.
- `test_vtm_single_rank_line_plots_combine_all_blocks_once` exercises automatic per-image contour scaling.
- `test_incomplete_line_and_streamline_requests_are_rejected_before_execution` and `test_ambiguous_slice_field_requires_explicit_association` cover missing and ambiguous field choices.
