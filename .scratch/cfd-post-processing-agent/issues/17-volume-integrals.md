# 17: Integrate point and cell variables over the volume

**What to build:** Add a spatial volume-integral action that returns a global value for each physical timestep, using the full domain by default and supporting an optional named threshold region.

**Blocked by:** #02 Read .pvtu and multi-block cases with size validation; #03 Process a large case across MPI with bounded memory; #11 Run .pvtu, .vtk, and .vtm cases across MPI ranks.

**Status:** ready-for-agent

- [ ] Integrate cell-associated values using physical cell volumes and point-associated values using cell interpolation and quadrature; integrate vector components independently.
- [ ] Use the full mesh by default and allow an existing threshold selection to define an optional region of integration.
- [ ] Integrate registered derived point and cell variables as well as fields read from the input.
- [ ] For temporal data, write one global integral per physical timestamp; record field, association, region, and units when supplied.
- [ ] Combine rank-local contributions with MPI reductions and avoid counting ghost cells or shared partition boundaries more than once.
- [ ] Report unsupported cell types or invalid field tuple counts clearly without changing the source data.
- [ ] Verify scalar and vector integrals for point and cell fields on structured and unstructured fixtures, including a threshold region and a multi-rank comparison to the serial result.

