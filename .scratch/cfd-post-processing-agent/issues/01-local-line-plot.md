# 01: Run a local line-plot workflow from an agreed request

**What to build:** An analyst can request a line plot for a single .vtk case, review and agree to the plan, then run it locally and inspect saved results.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

**Completion:** verified

- [x] The analyst can provide a field and line start/end coordinates through the supported notebook workflow; incomplete requests produce an actionable prompt before execution.
- [x] The workflow presents its ordered actions for agreement and generates a Python script after approval.
- [x] The local run uses the user-selected CPU count.
- [x] The chosen output folder contains a PNG line plot, CSV samples, the generated script, and a run log.
- [x] A small representative .vtk fixture demonstrates the complete behavior at the end-to-end workflow seam.

## Acceptance evidence

- `test_notebook_session_requires_approval_then_writes_python_script` verifies review, approval, ordered request content, and generated Python.
- `test_incomplete_line_and_streamline_requests_are_rejected_before_execution` verifies missing line coordinates and fields are requested before execution.
- `test_approved_vtk_line_workflow_writes_csv_png_script_and_log` runs an approved `.vtk` request and checks plots, CSV, script, log, CPU selection, and run metrics.
