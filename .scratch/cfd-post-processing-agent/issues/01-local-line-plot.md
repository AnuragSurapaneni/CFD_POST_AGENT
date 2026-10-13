# 01: Run a local line-plot workflow from an agreed request

**What to build:** An analyst can request a line plot for a single .vtk case, review and agree to the plan, then run it locally and inspect saved results.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] The analyst can provide a field and line start/end coordinates through the supported chat or notebook workflow; missing choices are requested before execution.
- [ ] The workflow presents its ordered actions for agreement and generates a Python script after approval.
- [ ] The local run uses the user-selected CPU count.
- [ ] The chosen output folder contains a PNG line plot, CSV samples, the generated script, and a run log.
- [ ] A small representative .vtk fixture demonstrates the complete behavior at the end-to-end workflow seam.
