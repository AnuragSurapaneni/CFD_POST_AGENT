# 02: Read .pvtu and multi-block cases with size validation

**What to build:** The existing line-plot workflow can read the initial .pvtu and multi-block inputs, including point and cell fields, and report structural size mismatches before plotting.

**Blocked by:** #01 Run a local line-plot workflow from an agreed request.

**Status:** ready-for-agent

- [ ] The line-plot workflow accepts supported .pvtu and multi-block cases alongside .vtk input.
- [ ] Point-field tuple counts are checked against mesh point counts; cell-field tuple counts are checked against mesh cell counts.
- [ ] A mismatch stops the run with a clear diagnostic and does not alter source data.
- [ ] Both valid and mismatched fixtures are demonstrated through the end-to-end workflow.
