Status: ready-for-agent

# CFD Post-Processing Agent

## Problem Statement

CFD analysts need to explore multi-terabyte, time-dependent simulation data and combine statistical calculations with visual analysis. Performing these operations manually is slow, difficult to reproduce, and can hide patterns that are not apparent from individual plots or summary values. The tool must process large structured and unstructured datasets in parallel while keeping the analysis understandable and under the analyst's control.

## Solution

Build an interactive post-processing agent that accepts analysis instructions through chat or a notebook. It turns each request into an ordered, inspectable workflow, asks for missing or ambiguous inputs, and waits for the analyst to agree before running it.

The agent generates Python analysis scripts. For local execution, it runs the script using the CPU count chosen by the user. For HPC execution, it also generates a Slurm script using the user's selected resources and saved cluster settings; the user submits that job.

A shared data kernel reads and checks CFD data, then exposes a common interface to independent statistics and plotting modules. The system supports MPI processing across selected nodes, data larger than RAM, registered user Python functions, and reproducible per-job outputs.

## User Stories

1. As a CFD analyst, I want to describe an analysis in chat or a notebook, so that I can work from the scientific question rather than manually wiring processing steps.
2. As a CFD analyst, I want to review the ordered actions and their parameters before execution, so that I can catch an incorrect interpretation before an expensive job runs.
3. As a CFD analyst, I want the agent to ask when a required field, time, streamline seed, or other parameter is ambiguous, so that it does not silently choose an unintended analysis.
4. As a CFD analyst, I want the agent to preserve my requested operation order, so that composed workflows produce the analysis I described.
5. As a CFD analyst, I want to load VTK .vtk and .pvtu data first, so that I can use the formats in my current workflow.
6. As a CFD analyst, I want the reader to handle structured and unstructured data, multi-block cases, and the scalar and vector fields in each case, so that I can analyze representative CFD datasets.
7. As a CFD analyst, I want to process temporal data on a fixed mesh using physical timestamps, so that temporal calculations reflect the actual time intervals.
8. As a CFD analyst, I want unambiguous timestamps read from the data and filenames used only when their time mapping is clear, so that time-dependent results are not based on guessed times.
9. As a CFD analyst, I want point fields checked against mesh point counts and cell fields checked against mesh cell counts, so that inconsistent array sizes are caught before analysis.
10. As a CFD analyst, I want size mismatches reported clearly and left unrepaired, so that the system does not guess how to alter scientific data.
11. As a CFD analyst, I want the kernel to check structural consistency without judging scientific data quality, so that post-processing does not silently discard or alter values based on quality assumptions.
12. As a CFD analyst, I want cases larger than available RAM processed in partitions, so that multi-terabyte datasets can be analyzed.
13. As a CFD analyst, I want MPI to distribute one large case across the selected nodes and process time steps in chunks, so that the whole case can use cluster resources.
14. As an HPC user, I want independent cases to be runnable as separate jobs, so that multiple analyses can use available resources.
15. As a user running locally, I want to choose the CPU count and have the agreed Python workflow run, so that I can use local compute without manually preparing a job.
16. As an HPC user, I want the agent to generate a Python script and a Slurm submission script, so that I can review and submit the job on the cluster myself.
17. As an HPC user, I want to set node count and CPUs per node, reuse stable cluster settings, and override settings per job, so that generated Slurm scripts fit my environment and workload.
18. As a CFD analyst, I want the job to read data from its existing location and write results separately, so that large input datasets do not need to be copied unless the cluster requires staging.
19. As a CFD analyst, I want to plot a selected variable along a line defined by start and end coordinates, so that I can inspect flow behavior at a location of interest.
20. As a CFD analyst, I want line sampling resolution estimated from the mesh with an option to override it, so that plots have a useful default while allowing precise control.
21. As a CFD analyst, I want to create slices using an origin and orientation, so that I can inspect arbitrary planes through the data.
22. As a CFD analyst, I want to specify the axis for azimuthal averages and compute averages over radial bins on selected slices, so that I can study circumferential flow behavior.
23. As a CFD analyst, I want azimuthal results to report available angular coverage and ask before treating a partial sector as a full circumference, so that sector data is not misrepresented.
24. As a CFD analyst, I want a filled contour plot of a selected scalar field on a requested slice, so that I can inspect spatial distributions in saved images.
25. As a CFD analyst, I want contour levels to use either a shared scale for comparisons or an automatic scale per image, so that I can choose between direct comparison and detail within each result.
26. As a CFD analyst, I want streamlines generated from a selected vector field and seeds I specify as points, a line, or a plane, so that the visualization reflects the flow region I want to investigate.
27. As a CFD analyst, I want thresholds to select values within a requested range and make that selection reusable, so that I can apply the same region to plots and calculations.
28. As a CFD analyst, I want time-dependent plots to ask for a timestamp or statistic when my request omits one, so that the agent does not silently pick a time interpretation.
29. As a CFD analyst, I want temporal means and RMS calculations weighted by physical time, so that unevenly spaced snapshots contribute according to their intervals.
30. As a CFD analyst, I want both raw RMS and fluctuation RMS, so that I can distinguish total signal magnitude from variation around the mean.
31. As a CFD analyst, I want spatial weighting methods to be explicit and recorded, so that I can interpret global results and reproduce them.
32. As a CFD analyst, I want missing physical constants requested with units and recorded with the job, so that calculations such as Kolmogorov scales use known inputs.
33. As a CFD analyst, I want to add custom Python functions from notebooks or Python files and keep them available across sessions, so that project-specific calculations become reusable kernel variables.
34. As a CFD analyst, I want custom functions to return point data, cell data, or global results, so that I can calculate both fields and summaries.
35. As a CFD analyst, I want the kernel to handle partitioning and global reductions for custom functions, so that user calculations can participate in MPI workflows without each function reimplementing job coordination.
36. As a CFD analyst, I want derived variables available to later statistics and plots, so that a calculation can feed into the rest of an analysis workflow.
37. As a CFD analyst, I want concise observations about patterns and outliers linked to supporting statistics and visualizations, so that I can evaluate conclusions that may not be obvious from raw outputs.
38. As a CFD analyst, I want each job to save PNG images, CSV statistics, generated scripts, logs, and requested derived fields in a chosen output folder, so that I can inspect and reproduce the analysis.
39. As a CFD analyst, I want saved derived fields to use the input VTK format when possible, so that I can continue using them in my existing workflow.
40. As a CFD analyst, I want runs to record elapsed time, data processed, memory use, and node count, so that I can establish performance baselines without assuming a speed target.

## Implementation Decisions

- Treat the system as a post-processing tool. It does not run or modify CFD simulations.
- Provide chat and notebook interaction. Convert instructions into an inspectable ordered workflow and require user agreement before execution.
- Generate a Python script for every agreed workflow. Run locally after agreement; for HPC, generate a Slurm script for user submission and do not submit it automatically.
- Let users set local CPU count. For Slurm, let users set node count and CPUs per node. Reuse saved cluster settings and allow per-job overrides.
- Prioritize .vtk and .pvtu input, including structured and unstructured datasets, multi-block organization, scalar and vector fields, and temporal data on a fixed mesh. Extend to other common structured and unstructured formats after the first formats.
- Use explicit physical timestamps where available. Infer timestamps from filenames only if the mapping is unambiguous. If a plot request has no time selection, ask whether the user wants a timestamp or a temporal statistic.
- Make the kernel responsible for reading data and checking array sizes. Validate point arrays against mesh points and cell arrays against mesh cells. Stop with a clear report on size mismatches; do not attempt automatic repair or scientific-quality screening.
- Keep statistics and plotting as independent modules that consume a shared kernel data interface. Neither module depends on the other.
- Process datasets larger than RAM in partitions. Use MPI across selected nodes for a single large case, process temporal data in chunks, and allow independent cases to run as separate jobs. Read inputs in place unless cluster staging is required.
- Weight temporal means and RMS by physical time. Provide raw RMS and fluctuation RMS as distinct results. Make spatial weighting explicit and record it with the result.
- Treat `t=0` as the initial condition, not a temporal sample for temporal statistics; keep it available for analyses that explicitly request that snapshot. In the supplied fixture, `t=0` contains only the mesh, and temporal statistics use the populated snapshots at `t=0.0005` and `t=0.001`.
- Define line plots by start and end coordinates. Estimate sampling resolution from the mesh by default and permit an override.
- Define slices by origin and orientation. Require an explicit averaging axis for azimuthal calculations. Use radial bins with user-selectable count or spacing; report angular coverage and ask before interpreting a partial sector as a complete circumference.
- Start contour visualization with filled 2D contours on requested slices. Require a selected scalar field. Support shared contour scales for comparisons and automatic scales per image.
- Require streamline seeds as points, a line, or a plane. Ask if seeds or the vector field are missing or ambiguous.
- Thresholds select values within the requested range and produce a reusable selection for later operations.
- Preserve the user-requested action order. Ask for missing inputs rather than silently changing the workflow.
- Allow user-defined Python functions from notebooks or Python files. Register them across sessions as kernel variables. Functions may return point data, cell data, or global results; the kernel manages partitioning and global reductions.
- Request missing physical constants, record units, and include them with the job inputs.
- Write each job's outputs to a user-chosen folder. Save PNG images, CSV statistics, generated scripts, logs, performance measurements, and derived fields only when requested. Use the input VTK format for derived fields when possible.
- Assume jobs complete; restart and checkpoint recovery are not required. Record performance measurements but do not impose an initial throughput target.
- Provide concise observations tied to the supporting results so analysts can evaluate them rather than treating generated interpretations as definitive scientific conclusions.

## Testing Decisions

- Use one black-box end-to-end acceptance seam: from an agreed analysis request through the generated Python and Slurm scripts to produced local statistics and visualizations.
- Good tests verify externally visible behavior with representative small fixtures, not internal class structure or implementation details. Fixtures should include point and cell fields, temporal data with physical timestamps, and the supported dataset organization.
- For the supplied temporal fixture, verify that `t=0` is treated as the initial condition and excluded from the temporal mean and RMS window; the explicit statistical window is `t=0.0005` through `t=0.001`.
- Exercise the reader and consistency checks through the workflow boundary, including a valid dataset and a mismatched point or cell array that must produce a clear failure report without repair.
- Exercise a composed workflow containing a line plot, a slice, a threshold, a derived variable, time-weighted statistics, and a contour or streamline output. Check numerical results, generated files, and recorded parameters.
- Check that ambiguous time selections and missing streamline seeds result in a user question before execution.
- Check that local execution uses the selected CPU count and produces the expected outputs. Check that the Slurm script reflects selected nodes, CPUs per node, and saved cluster settings; automated acceptance tests do not submit jobs to a live cluster.
- Prior art: none is present in the workspace; this is a new project with no existing code or test suite.

## Out of Scope

- Running, changing, or generating CFD simulations.
- Assessing scientific data quality or automatically repairing malformed field values.
- Moving or changing mesh topology over time in the initial scope.
- Automatically submitting Slurm jobs on the user's behalf.
- Restarting interrupted jobs or maintaining checkpoints; jobs are assumed to complete.
- A fixed throughput guarantee before measurements establish a performance baseline.

## Further Notes

- The project workspace had no existing application code, glossary, ADRs, or tests when this spec was drafted. The end-to-end workflow boundary is the single proposed testing seam confirmed by the user.
- This spec prioritizes .vtk and .pvtu; broader support for common structured and unstructured formats can follow.
