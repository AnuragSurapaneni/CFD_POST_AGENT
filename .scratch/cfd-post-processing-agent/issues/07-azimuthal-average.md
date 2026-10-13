# 07: Compute azimuthal averages on slices

**What to build:** An analyst can calculate a radial profile by azimuthally averaging a selected field on an arbitrary slice and inspect the angular coverage used.

**Blocked by:** #04 Calculate time-weighted means and RMS; #05 Analyze slices with contours and reusable thresholds.

**Status:** ready-for-agent

- [ ] The analyst specifies the averaging axis and slice geometry.
- [ ] The analyst can choose radial bin count or spacing and receives a radial profile.
- [ ] The result reports available angular coverage.
- [ ] A partial sector is not treated as a full circumference without explicit user direction.
- [ ] The result uses the selected timestamp or temporal statistic and records that choice.
