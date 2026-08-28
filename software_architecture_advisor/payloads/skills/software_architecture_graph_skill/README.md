# Software Architecture Graph Skill

A standard-library-only, blueprint-owned skill for safe source inventories,
static import graphs, dependency metrics, and architecture evidence. It is
intended for `software_architecture_advisor` only.

The skill reads a staged source folder. It does not execute files, install
packages, invoke Git, write to the source folder, or use the network.
