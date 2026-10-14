# 13: Bound memory while assembling distributed slice contours

**What to build:** Render slice contours from distributed partitions without gathering every rank's full slice geometry into rank zero memory. This follow-up covers result assembly and rendering after partitions have been read; it complements the bounded input-processing work in #03.

**Blocked by:** #03 Process a large case across MPI with bounded memory; #11 Run .pvtu, .vtk, and .vtm cases across MPI ranks.

**Status:** ready-for-agent

- [ ] Replace the full-object gather for distributed slice contours with a bounded-memory strategy, such as chunked rasterization or a partitioned intermediate representation.
- [ ] Keep output image dimensions, contour levels, and color scale consistent across ranks and write the final image and metadata once.
- [ ] Ensure shared boundaries and ghost cells do not create visible seams or double-counted contour contributions.
- [ ] Verify serial and multi-rank images agree on a representative fixture, with documented image/numeric tolerances.
- [ ] Measure peak memory on rank zero and worker ranks for increasing mesh sizes; demonstrate that rank-zero memory is bounded by the rendering/output configuration rather than total slice geometry.

