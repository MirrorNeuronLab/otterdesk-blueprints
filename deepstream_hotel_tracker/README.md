# Hotel 3D tracker

Watch The Atrium in NVIDIA Isaac Sim. The two exits flank the reception desk
across from the main entrance. New guest trips continue while the co-worker
is running, even when its workspace is closed. Guests join a changing line
at reception and spend at least 30 seconds queuing and checking in before
heading for an exit. An AgiBot G2 travels through the east aisle.

## Start the simulation

Use a Linux DGX Spark with Docker, NVIDIA Container Toolkit and at least
**48 GiB** of NVIDIA GPU-accessible memory. The GB10's unified memory counts
toward this requirement. The first start prepares the Isaac Sim 6.2 and
DeepStream 9.1 runtimes, downloads the pinned NVIDIA props and character, and
builds the PeopleNet Transformer TensorRT engine for the GPU.

Hire or refresh **Hotel 3D tracker** in OtterDesk, select **Live hotel simulation**
and choose a Spark execution PC. Run progress checks the lobby setup, prepares
guest detection, starts the simulation, and checks the live cameras and tracking.
Monitoring begins when the co-worker receives live frames and tracking data.
Open **Hotel lobby live** when it is ready.
The sample supplies all four cameras. A separate real-camera deployment needs
a camera configuration and a 3D scan of the space.
Pause or stop the co-worker to stop simulation and tracking. Resume keeps the
observed totals for that run and starts fresh guest trips.

From a catalog checkout, run the co-worker on a compatible execution node.

    mn blueprint run ./deepstream_hotel_tracker --detached --follow-seconds 0

## Review guest traffic

Use **Save crossing report** to download a snapshot of the synthetic lobby. Shutdown saves `report.html` beside `people_counts.json`. The review shows per-door totals, the latest tracking timestamp and up to 16 recent crossings.

The dashboard shows the four live views, current track locations on the floor
plan, cumulative **People entered** and **People left**, and recent crossings
with their door and time. Use **2D** for the overhead floor plan with fading
16-second movement trails for guests and the AgiBot. Use **3D** for colored
sticks with each guest's track number and time observed inside. An
AgiBot marker appears when a camera reads the robot's optical tag. Counts are
available for the main entrance, west exit and east exit individually. A
completed crossing counts in its observed direction, so a person can
contribute more than one crossing.

Isaac Sim renders four synchronized cameras from the bundled
[OpenUSD stage](payloads/isaac/assets/hotel_reception.usda). DeepStream reads
four local RTSP streams and estimates 3D tracks from the camera pixels and
the stage's calibration. The co-worker counts those tracks across the
calibrated door thresholds in either direction.
Missed detections, occlusion and changes in track IDs can affect the totals
and how much of a visit is timed.
The latest count snapshot is saved in `people_counts.json` in the Job's run
store and the configured output folder, which defaults to
`~/Downloads/deepstream-hotel-tracker`.

The [recorded example](examples/sample_inputs/README.md) documents the
original Atrium layout. See [asset attribution](LICENSE.md) and
[NVIDIA's Multi-View 3D Tracking documentation](https://docs.nvidia.com/metropolis/deepstream/9.1/text/DS_MV3DT.html).
