# 14: Preserve threshold selections across MPI partitions

**What to build:** Make a threshold selection produced on distributed data reusable by later actions while preserving each selected point or cell's source partition and association.

**Blocked by:** #11 Run .pvtu, .vtk, and .vtm cases across MPI ranks.

**Status:** ready-for-agent

- [ ] Apply the requested threshold independently to each local partition and preserve point-versus-cell association.
- [ ] Make the named selection available to subsequent plots and calculations on every rank without replicating the full selected dataset.
- [ ] Preserve source rank and partition identity so selected pieces can be saved or traced back to their inputs.
- [ ] Write a single manifest for a distributed selection, or one combined artifact, with no filename collisions or duplicate rank-level summaries.
- [ ] Verify a composed threshold-then-analysis workflow matches its single-rank result and correctly handles empty ranks and ghost cells.

