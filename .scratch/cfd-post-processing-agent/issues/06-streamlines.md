# 06: Generate streamlines from chosen seeds

**What to build:** An analyst can add a streamline visualization using a selected vector field and explicit seed geometry, then save the result with the workflow outputs.

**Blocked by:** #03 Process a large case across MPI with bounded memory.

**Status:** ready-for-agent

**Completion:** verified

- [x] The analyst can select a vector field and seed points, a line, or a plane.
- [x] Missing or ambiguous vector fields and seeds produce actionable validation errors so the analyst can clarify the request.
- [x] The workflow saves a PNG streamline visualization.
- [x] A representative unstructured case exercises this behavior through the agreed workflow seam.

## Acceptance evidence

- `test_composed_temporal_workflow_covers_derived_line_slice_threshold_streamline_and_average` runs point, line, and plane seeds over an unstructured tetrahedral mesh and checks all three PNG outputs.
- `test_incomplete_line_and_streamline_requests_are_rejected_before_execution` checks missing streamline seeds.
- `test_ambiguous_streamline_field_requires_explicit_association` checks that a point/cell ambiguity requires an explicit association.
