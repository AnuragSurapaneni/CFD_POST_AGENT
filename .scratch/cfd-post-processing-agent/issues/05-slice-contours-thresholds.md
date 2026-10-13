# 05: Analyze slices with contours and reusable thresholds

**What to build:** An analyst can inspect a scalar field on an arbitrary slice, save a contour image, and reuse a threshold selection in later operations.

**Blocked by:** #03 Process a large case across MPI with bounded memory.

**Status:** ready-for-agent

- [ ] A slice is defined by an origin and orientation.
- [ ] The analyst selects a scalar field; missing or ambiguous field choices are clarified.
- [ ] The workflow saves a filled 2D contour image and supports shared scales for comparisons or automatic scales per image.
- [ ] A requested threshold selects values within its range and can be reused by later plots and calculations.
