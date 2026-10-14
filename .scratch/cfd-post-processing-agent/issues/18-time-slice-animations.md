# 18: Generate time-dependent slice and volume animations

**What to build:** Generate an MP4 animation with ffmpeg from physical-time snapshots, supporting both 2D slice contours and 3D volume rendering.

**Blocked by:** #04 Calculate time-weighted means and RMS; #05 Analyze slices with contours and reusable thresholds; #11 Run .pvtu, .vtk, and .vtm cases across MPI ranks.

**Status:** ready-for-agent

- [ ] Use all physical timestamps in the requested interval and preserve elapsed-time spacing between frames; show the physical timestamp on each frame.
- [ ] Support a user-selected scalar field on an arbitrary 2D slice and in a 3D volume rendering.
- [ ] Use one color scale across the animation unless the user requests otherwise.
- [ ] Fit the camera once around the selected slice or volume bounds, center it there, and keep its position and orientation fixed across frames.
- [ ] Invoke ffmpeg to write one MP4 for the agreed action and avoid duplicate per-rank videos in MPI runs.
- [ ] Fail clearly when ffmpeg is unavailable or timestamps cannot be represented by the requested animation method; do not silently reorder or retime frames.
- [ ] Verify output ordering, timestamp labels, frame durations for unevenly spaced snapshots, consistent color limits and camera, and serial versus multi-rank frame content on representative 2D and 3D fixtures.

