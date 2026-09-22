# ROS AMR Controller capabilities

This Job controls only the bundled warehouse simulation. Motion requires an already-running, healthy ROS service Run.

The bounded controls are:

- read the current simulated robot status;
- navigate autonomously to Zone A, Zone B, or Zone C;
- cancel navigation and send a bounded stop burst;
- apply one watchdog-limited forward, left, or right adjustment pulse.

The conversational response agent never starts or resumes a ROS service Run. It cannot accept arbitrary coordinates, speeds, durations, shell commands, MCP endpoints, or new tools. It reports navigation success only after the correlated ROS operation reports arrival.

Learning is explicit. A human may teach an alias for Zone A, Zone B, or Zone C, add a descriptive capability note, or add a constraint that disables an existing control. A direct prohibition such as “Do not enter Zone C” is stored as an argument-scoped constraint and blocks only navigation to that zone. Learned memory cannot broaden the control envelope. Active learned knowledge is written to `knowledge/learned/active.md` in the stable Job data directory.
