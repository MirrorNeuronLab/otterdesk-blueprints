"""Exercise the shipped Wasmtime embedder against test-owned, run-scoped services."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
from tempfile import TemporaryDirectory
from threading import Thread

from mn_sdk_common.committed_artifacts import CommittedJsonStore, COMMITTED_BYTES_VERSION, COMMITTED_JSON_VERSION

LIMIT = 16 * 1024 * 1024


def invoke_phase(config, payload, environment, *, service=None):
    root = Path(environment["MN_BUNDLE_ROOT"])
    component = root / config["wasm_component"]
    if hashlib.sha256(component.read_bytes()).hexdigest() != component.stem:
        raise ValueError("The staged component differs from its submission digest")
    store = CommittedJsonStore(Path(environment["MN_RUN_DIR"]))
    with TemporaryDirectory(prefix="mn-wit-fixture-") as tmp:
        private = Path(tmp)
        job = private / "job"
        job.mkdir()
        if source := config.get("wasm_inputs"):
            if (root / source).is_dir():
                shutil.copytree(root / source, job / "inputs")
            elif config.get("wasm_optional_inputs"):
                (job / "inputs").mkdir()
        def write(name, value):
            (job / name).write_text(json.dumps(value))
        write("config.json", {**config["wasm_config"], "simulated_model":config.get("environment",{}).get("MN_LLM_PROVIDER")=="fake"})
        write("mirror_neuron_context.json", {"workflow":{"run_id":environment["MN_RUN_ID"]}})
        write("mirror_neuron_input.json", {"step_input":payload})
        path = str(private / "control.sock")
        with socket.socket(socket.AF_UNIX) as listener:
            listener.bind(path)
            listener.listen(1)
            listener.settimeout(10)
            def serve():
                with listener.accept()[0] as conn, conn.makefile("rb") as stream:
                    while head := stream.read(4):
                        (size,) = struct.unpack(">I",head)
                        assert size <= LIMIT
                        request = json.loads(stream.read(size))
                        op = request["service"]+"."+request["operation"]
                        args = request["args"]
                        try:
                            if op not in config["wasm_capabilities"]:
                                raise ValueError("Capability denied")
                            if op == "artifacts.read":
                                file = store.path(args[0])
                                if not file.is_file(): raise ValueError("artifact_missing")
                                data=file.read_bytes()
                                if args[1] and hashlib.sha256(data).hexdigest()!=args[1]:raise ValueError("artifact_integrity_error")
                                value=data.decode()
                            elif op == "artifacts.commit":
                                name,kind,content=args
                                value=store.commit_bytes(name,content.encode(),kind=kind,
                                    version=COMMITTED_JSON_VERSION if kind=="json" else COMMITTED_BYTES_VERSION,mode=0o644).to_dict()
                            elif op == "artifacts.static-report":
                                from mn_sdk_web_ui.report import static_run_report_handle
                                value=static_run_report_handle(store.run_dir,args[0],title=args[2])
                                if value["metadata"]["sha256"]!=args[1]:raise ValueError("Report digest changed")
                            elif op == "artifacts.publish":
                                from mn_sdk.storage.published import record_delivered_outputs
                                record_delivered_outputs(store.run_dir,json.loads(args[0]))
                                value=[]
                            elif service is not None:
                                value=service(op,args)
                            else:
                                raise ValueError("Unbound test service "+op)
                            reply={"ok":value if isinstance(value,str) else json.dumps(value)}
                        except (KeyError, ValueError, RuntimeError) as exc:
                            reply={"error":str(exc)}
                        response=json.dumps(reply).encode()
                        conn.sendall(struct.pack(">I",len(response))+response)
            worker=Thread(target=serve,daemon=True)
            worker.start()
            runner=os.environ.get("MN_WASMTIME_HOST_BIN","mn-wasmtime-runner")
            completed=subprocess.run([shutil.which(runner) or runner,str(component),str(job),path],capture_output=True,timeout=30,env={})
            worker.join(10)
            if completed.returncode:
                raise RuntimeError(completed.stderr.decode() or "WASI command failed")
            return json.loads((job/"output.json").read_bytes())["outputs"]["result"]
