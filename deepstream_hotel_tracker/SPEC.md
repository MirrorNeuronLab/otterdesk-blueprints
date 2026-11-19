# Hotel 3D tracker specification

## Outcome

Run the bundled OpenUSD Atrium stage on DGX Spark in NVIDIA Isaac Sim.
Preserve the reception desk, lounges and main entrance. Place the west and east
exits beside reception on the wall across from the main entrance. Generate
new guest trips in real time. Guests queue in front of reception for at least
30 seconds before departing. Vary arrival and reception timings and serve the
line in order. Render the moving AgiBot G2 and guests from four calibrated
cameras at the same simulation time.

## Execution

- Require Linux, Docker with the NVIDIA Container Toolkit, and one CUDA GPU
  with at least 49,152 MiB of GPU-accessible memory. Check the CUDA-visible GPU
  before startup.
- Run NVIDIA Isaac Sim, DeepStream and PeopleNet Transformer in one GPU worker.
  Use the published NVIDIA reference runtime images and pinned USD dependencies.
  Read each camera's projection from the running USD stage. RTSP streams and
  MQTT metadata stay on the worker's loopback interface. The workspace is
  served by the Job Web UI proxy.
- Check the lobby setup and prepare guest detection before starting the live
  service. Report simulation startup and camera tracking checks as they happen.
  Begin monitoring after the renderer and DeepStream produce live frames and
  metadata. Pause and stop retire the workspace and stop the owned processes.
  Keep the run's cumulative counts on resume. New runs start with empty totals.
  Fail the service if rendering, inference or required metadata stops.

## Counts and evidence

- Use NVIDIA Multi-View 3D Tracking with a 1.7 m person model and calibrated
  camera positions and projection matrices in meters.
- Count a directional crossing when a tracked trajectory reaches opposite
  sides of a door threshold, inside the opening span. Require observations
  close together in time and space and a band around the threshold to reduce
  jitter. Use a designated camera at each doorway to avoid summing duplicate
  views. The counts use detector and tracker metadata from the rendered frames.
- Present live camera views, observed guest positions in switchable overhead
  and 3D floor plans, entry and exit totals for the run and for each door, and
  recent crossing evidence. The overhead view shows recent camera-derived guest
  and robot trails in their marker colors and breaks trails across long gaps
  or abrupt jumps. The 3D view shows guests as colored sticks with
  numeric track IDs and elapsed time since first observed inside. It uses a
  separate shape for the AgiBot when an optical tag is detected in the live
  camera frames. Report changing totals in Job activity. Persist a bounded
  snapshot in `people_counts.json`.
- Treat results as estimates. Occlusions, missed detections and identity changes
  can affect the result. The totals count traversals, including return trips.
