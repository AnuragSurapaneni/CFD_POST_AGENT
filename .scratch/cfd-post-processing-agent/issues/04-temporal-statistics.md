# 04: Calculate time-weighted means and RMS

**What to build:** An analyst can request temporal statistics over a fixed-mesh case and receive time-weighted fields and reproducibility details.

**Blocked by:** #03 Process a large case across MPI with bounded memory.

**Status:** ready-for-agent

- [ ] Physical timestamps are used for temporal weighting; filename inference is used only when unambiguous.
- [ ] The workflow provides time-weighted mean, raw RMS, and fluctuation RMS for supported point and cell fields.
- [ ] Ambiguous time selection is clarified before execution.
- [ ] The CSV results record the statistic, time range, weighting method, and relevant inputs.
