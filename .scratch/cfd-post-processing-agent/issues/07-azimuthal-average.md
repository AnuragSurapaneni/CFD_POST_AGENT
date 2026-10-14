# 07: Compute azimuthal averages on slices

**What to build:** An analyst can calculate a radial profile by azimuthally averaging a selected field on an arbitrary slice and inspect the angular coverage used.

**Blocked by:** #04 Calculate time-weighted means and RMS; #05 Analyze slices with contours and reusable thresholds.

**Status:** ready-for-agent

**Completion:** verified

- [x] The analyst specifies the averaging axis and slice geometry.
- [x] The analyst can choose radial bin count or spacing and receives a radial profile.
- [x] The result reports available angular coverage.
- [x] A partial sector is not treated as a full circumference without explicit user direction.
- [x] The result uses the selected physical timestamp and records that choice in its CSV output.

## Acceptance evidence

- `test_composed_temporal_workflow_covers_derived_line_slice_threshold_streamline_and_average` checks a selected time, radial bins, time metadata, and angular coverage in the profile CSV.
- `test_partial_azimuthal_sector_requires_explicit_acceptance` verifies the partial-sector error and succeeds only after explicit acceptance.
