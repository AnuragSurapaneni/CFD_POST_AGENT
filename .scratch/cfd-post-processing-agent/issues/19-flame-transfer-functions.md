# 19: Post-process linear and nonlinear flame transfer functions

**What to build:** Analyze flame response signals using normalized heat-release response and incoming turbulent velocity signals. Support linear flame transfer functions (FTFs) and amplitude-dependent flame describing functions (FDFs); this ticket does not include combustor-wide stability or mode analysis.

**Blocked by:** #04 Calculate time-weighted means and RMS; #11 Run .pvtu, .vtk, and .vtm cases across MPI ranks; #17 Integrate point and cell variables over the volume.

**Status:** ready-for-agent

- [ ] Compute volume-integrated heat release at each physical timestamp from a selected point or cell heat-release-rate field.
- [ ] Use incoming velocity from a user-selected inlet plane, with area-averaged normal velocity as the default, or accept a user-defined inlet-velocity signal or averaging function.
- [ ] Compute and document the normalized response `H(f) = (Q'(f) / mean(Q)) / (U'(f) / mean(U))` and report gain and phase.
- [ ] Support harmonic/lock-in analysis at selected forcing frequencies and a broadband linear FTF estimator; include a signal-quality measure for broadband estimates.
- [ ] Preserve actual timestamps for harmonic analysis. Require uniform sampling for broadband estimation and report a clear error for uneven samples rather than silently resampling.
- [ ] For FDF analysis, accept multiple runs labeled by forcing frequency and measured or specified velocity-fluctuation amplitude; report fundamental gain and phase by frequency and amplitude, with generated harmonics available as optional diagnostics.
- [ ] Provide CSV data and gain/phase plots with the selected field, velocity reference, normalization, time range, sampling method, frequency, and amplitude metadata.
- [ ] Combine distributed heat-release and velocity contributions correctly across MPI ranks, excluding ghost overlap, and verify FTF/FDF results against small reference signals with known gain and phase.
- [ ] Keep nonlinear FDF outputs distinct from linear FTF outputs; do not report acoustic eigenmodes, growth rates, or stability predictions.

## References

- [Kim et al., spatially distributed flame transfer functions](https://www.sciencedirect.com/science/article/pii/S0010218010001203)
- [Palies et al., scaling of flame describing functions](https://doi.org/10.1007/s10494-023-00458-7)

