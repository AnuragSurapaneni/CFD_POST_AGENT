# 16: Decide a safe MPI strategy for monolithic legacy .vtk files

**What to build:** Determine whether monolithic legacy `.vtk` files can be distributed across MPI ranks without every rank reading the full case or one rank becoming an unbounded-memory bottleneck. Record the recommendation and supported conversion path in an ADR before changing the current explicit multi-rank refusal.

**Blocked by:** #11 Run .pvtu, .vtk, and .vtm cases across MPI ranks.

**Status:** ready-for-agent

- [ ] Evaluate VTK reader and format options for partitioning legacy `.vtk` data, including conversion to `.pvtu` or `.vtm` and any safe in-job strategy.
- [ ] For each viable option, document memory use, I/O cost, preservation of point/cell fields and ghost metadata, and behavior for temporal inputs.
- [ ] Recommend either a safe multi-rank implementation or retaining the current clear refusal with a supported conversion workflow.
- [ ] Record the decision and rationale in `docs/adr/`; if support is recommended, define a follow-up implementation ticket with measurable acceptance criteria.
- [ ] Keep unsafe replicated full-case reads out of the accepted design.

