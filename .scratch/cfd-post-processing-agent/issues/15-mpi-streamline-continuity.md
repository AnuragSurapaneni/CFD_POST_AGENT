# 15: Trace streamlines continuously across MPI partitions

**What to build:** Make a streamline seeded on partitioned data follow the vector field across partition boundaries and produce one coherent visualization for the requested action.

**Blocked by:** #11 Run .pvtu, .vtk, and .vtm cases across MPI ranks.

**Status:** ready-for-agent

- [ ] Define how seeds are assigned when they lie on or near partition boundaries, and ensure each seed is traced once.
- [ ] Continue integration across rank boundaries without truncating or duplicating a streamline; account for ghost cells where present.
- [ ] Save one coherent image and either a combined streamline dataset or a manifest describing its partitioned output.
- [ ] Match single-rank streamline paths on a representative fixture with paths crossing at least one partition boundary.
- [ ] Verify empty ranks and uneven partitions participate safely without duplicated output files.

