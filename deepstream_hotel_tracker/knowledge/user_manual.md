# Hotel 3D tracker

NVIDIA Isaac Sim runs the live OpenUSD lobby on a DGX Spark. New guests enter
through the main entrance, queue at reception for at least 30 seconds before
heading out, and leave through the exits on either side of the desk. Four
calibrated cameras show the same running scene. Pause or stop the co-worker
to stop the simulation.

Open **Hotel lobby live** to see how many people entered and left during the
current run, the breakdown for each door and recent crossings with timestamps.
The floor plan shows guest positions estimated by NVIDIA DeepStream. Choose
**2D** for the overhead map or **3D** for colored sticks labeled with each
track number and its observed time in the lobby. The AgiBot has a separate
marker when a live camera reads its optical tag.

The co-worker observes guests in the camera images and counts a passage when
it follows a track across a doorway. Counts represent observed passages and
can be affected by occlusion or missed detections. Read the latest dashboard
or the saved `people_counts.json` snapshot before reporting numbers.

See the [conversation guide](conversation_guide.md) for guidance on reporting
live and saved counts.
