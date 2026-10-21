"""Browser listener resources under the stock monitored-service lifecycle."""
import threading
import time
from services.duck_control_service import prepare_server, write_final_artifact


def start(block, inputs):
    server, listener = prepare_server(block.config, block.store.run_dir)
    block.resources.update(server=server, listener=listener)
    worker = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    block.resources["worker"] = worker
    worker.start()
    deadline = time.monotonic() + 30
    while not server.started:
        block.check()
        if not worker.is_alive() or time.monotonic() >= deadline:
            raise RuntimeError("Microduck listener failed to start")
        time.sleep(0.05)


def health(block, inputs):
    return block.resources["worker"].is_alive() and block.resources["server"].started


def cycle(block, inputs):
    return {"status": "listening"}


def stop(block, inputs):
    resources = block.resources
    try:
        if "server" in resources:
            resources["server"].should_exit = True
        worker = resources.get("worker")
        if worker is not None and worker.ident is not None:
            worker.join(timeout=5)
            if worker.is_alive():
                resources["server"].force_exit = True
                worker.join(timeout=1)
            if worker.is_alive():
                raise RuntimeError("Microduck listener did not stop")
    finally:
        if "listener" in resources:
            resources["listener"].close()


def finalize(block, inputs):
    return {"status": "service_stopped", "artifact": write_final_artifact(block.store.run_dir)}
