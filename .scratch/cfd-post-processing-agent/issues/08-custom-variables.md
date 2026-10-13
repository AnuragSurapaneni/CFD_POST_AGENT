# 08: Add custom Python calculations as kernel variables

**What to build:** An analyst can register a custom Python calculation and use its output as a named variable in later statistics and visualizations.

**Blocked by:** #03 Process a large case across MPI with bounded memory.

**Status:** ready-for-agent

- [ ] Users can register functions from a notebook or Python file and reuse them across sessions.
- [ ] A function can return point data, cell data, or a global result.
- [ ] The kernel handles partitioning and supported global reductions for registered functions.
- [ ] The returned variable is available to later plots and statistics.
- [ ] A requested derived field is saved in the input VTK format when possible.
