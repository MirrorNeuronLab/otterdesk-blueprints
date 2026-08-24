# MirrorNeuron service entrypoint

`start_service.sh` is the source-controlled launcher used by the external
MirrorNeuron blueprint at `/Users/homer/Projects/ros-blueprint` on the controller
Mac. The blueprint uploads this launcher and the existing `web_control/` and
`web_ui/` sources to the selected worker.

The job is deliberately declared as `type: service` and requests an NVIDIA CUDA
GPU without naming a node. MirrorNeuron therefore keeps orchestration on the Mac
and places the DockerWorker on the eligible Spark node.

Build the image on Spark after source changes:

```bash
docker compose build overlay
```

Do not run `mn` from Spark for this workflow. Validate, start, pause, resume, and
replace the service from the controller checkout.
