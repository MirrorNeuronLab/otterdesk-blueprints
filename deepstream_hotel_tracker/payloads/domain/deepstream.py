"""Run NVIDIA's calibrated, four-source DeepStream pipeline inside the worker."""

import configparser
import ctypes
import os
import signal
import subprocess
import threading
from collections import deque
from contextlib import contextmanager
from pathlib import Path

import yaml

from .layout import CAMERAS, FPS, RESOLUTION


DEEPSTREAM_LIB = "/opt/nvidia/deepstream/deepstream/lib"
MODEL = Path("/opt/hotel")
ENGINE = MODEL / "peoplenet.onnx_b4_gpu0_fp16.engine"
ASSETS = Path(__file__).parent
SENSORS = tuple(f"Camera{number}" for number in range(1, len(CAMERAS) + 1))
MQTT_PORT = 1883
METADATA_TOPIC = "hotel/tracks"


def require_gpu():
    """Check the memory CUDA exposes, including the shared pool on GB10."""
    try:
        cuda = ctypes.CDLL("libcuda.so.1")
        device = ctypes.c_int()
        memory = ctypes.c_size_t()
        ready = (
            cuda.cuInit(0) == 0
            and cuda.cuDeviceGet(ctypes.byref(device), 0) == 0
            and cuda.cuDeviceTotalMem_v2(ctypes.byref(memory), device) == 0
        )
    except OSError as error:
        raise RuntimeError("DeepStream needs access to an NVIDIA GPU through Docker.") from error
    if not ready or memory.value < 48 * 1024**3:
        raise RuntimeError("DeepStream needs an NVIDIA CUDA GPU with at least 48 GiB of GPU-accessible memory.")


def _write_ini(path, sections):
    config = configparser.ConfigParser(interpolation=None)
    config.read_dict(sections)
    with path.open("w") as stream:
        config.write(stream, space_around_delimiters=False)


def _prepare_detector_config(work):
    detector = {
        "gpu-id": 0,
        "offsets": "123.675;116.28;103.53",
        "net-scale-factor": 0.0173520735728,
        "labelfile-path": MODEL / "detector_labels.txt",
        "onnx-file": MODEL / "peoplenet.onnx",
        "model-engine-file": ENGINE,
        "batch-size": len(SENSORS),
        "network-mode": 2,
        "num-detected-classes": 4,
        "filter-out-class-ids": "0;2;3",
        "interval": 0,
        "gie-unique-id": 1,
        "output-blob-names": "pred_boxes;pred_logits",
        "infer-dims": "3;544;960",
        "cluster-mode": 4,
        "parse-bbox-func-name": "NvDsInferParseCustomDDETRTAO",
        "custom-lib-path": MODEL / "detector_parser.so",
    }
    _write_ini(work / "detector.ini", {
        "property": detector,
        "class-attrs-all": {"pre-cluster-threshold": 0.3, "topk": 20},
    })


def prepare(work, feeds, camera_models):
    width, height = RESOLUTION
    batch_size = len(SENSORS)
    if len(feeds) != batch_size or len(camera_models) != batch_size:
        raise ValueError("DeepStream needs one calibration per live Atrium camera.")

    models = []
    for index, calibration in enumerate(camera_models):
        path = work / f"camera-{index}.yml"
        path.write_text(yaml.safe_dump(calibration, sort_keys=False))
        models.append(path)
    tracker = (ASSETS / "tracker.yml").read_text().replace(
        "__CAMERA_MODELS__", "\n".join(f"    - {path}" for path in models),
    ).replace("./peers.yml", str(work / "peers.yml")).replace("./mqtt.ini", str(work / "peer-mqtt.ini"))
    (work / "tracker.yml").write_text(tracker)

    topics = [f"127.0.0.1:{MQTT_PORT};/trck/cam{index}" for index in range(1, batch_size + 1)]
    (work / "peers.yml").write_text(yaml.safe_dump({
        "pubBrokerTopicStr": topics,
        "subPeerBrokerTopicStrs": [[peer for peer in topics if peer != own] for own in topics],
    }))
    (work / "mosquitto.conf").write_text(
        f"listener {MQTT_PORT} 127.0.0.1\nallow_anonymous true\npersistence false\nlog_type error\n"
    )
    _write_ini(work / "peer-mqtt.ini", {"message-broker": {"set-threaded": 0}})
    _write_ini(work / "metadata-mqtt.ini", {"message-broker": {"set-threaded": 1}})
    _write_ini(work / "sensors.ini", {
        f"sensor{index}": {"enable": 1, "type": "Camera", "id": sensor}
        for index, sensor in enumerate(SENSORS)
    })
    _write_ini(work / "deepstream.ini", {
        "application": {"enable-perf-measurement": 1, "perf-measurement-interval-sec": 5},
        **{
            f"source{index}": {
                "enable": 1, "type": 4, "uri": feed, "latency": 180, "select-rtp-protocol": 4, "gpu-id": 0,
            }
            for index, feed in enumerate(feeds)
        },
        "streammux": {
            "width": width, "height": height, "batch-size": batch_size,
            "batched-push-timeout": 1_000_000 // FPS, "live-source": 1, "gpu-id": 0,
            "attach-sys-ts-as-ntp": 1,
        },
        "primary-gie": {"enable": 1, "gpu-id": 0, "batch-size": batch_size, "config-file": "detector.ini"},
        "tracker": {
            "enable": 1, "gpu-id": 0, "tracker-width": width, "tracker-height": height,
            "ll-lib-file": f"{DEEPSTREAM_LIB}/libnvds_nvmultiobjecttracker.so",
            "ll-config-file": "tracker.yml",
        },
        "osd": {"enable": 0},
        "tiled-display": {"enable": 0},
        "sink0": {"enable": 1, "type": 1, "sync": 0, "qos": 0},
        "sink1": {
            "enable": 1, "type": 6, "topic": METADATA_TOPIC,
            "msg-conv-config": "sensors.ini",
            "msg-conv-payload-type": 2,
            "msg-conv-msg2p-new-api": 0,
            "msg-conv-frame-interval": 1,
            "msg-conv-msg2p-lib": f"{DEEPSTREAM_LIB}/libnvds_msgconv_mega.so",
            "msg-broker-proto-lib": f"{DEEPSTREAM_LIB}/libnvds_mqtt_proto.so",
            "msg-broker-config": "metadata-mqtt.ini",
            "msg-broker-conn-str": f"127.0.0.1;{MQTT_PORT}",
        },
        "tests": {"file-loop": 0},
    })


@contextmanager
def process(command, *, work, env=None, pass_fds=()):
    child = subprocess.Popen(
        command, cwd=work, env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True, pass_fds=pass_fds,
    )
    tail = deque(maxlen=4)

    def drain():
        for chunk in iter(lambda: child.stdout.read1(4096), b""):
            tail.append(chunk)

    reader = threading.Thread(target=drain, name="hotel-process-output", daemon=True)
    reader.start()
    try:
        yield child, lambda: b"".join(tail.copy()).decode(errors="replace")[-3000:].strip()
    finally:
        if child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
        reader.join(timeout=2)
        child.stdout.close()


def _nvidia_process(work, *arguments):
    env = dict(os.environ, GST_REGISTRY=str(work / "gst-registry.bin"), GST_DEBUG_NO_COLOR="1")
    # Initialize NVIDIA's CUDA forward-compatibility environment even when the
    # runtime invokes this step via docker exec, which skips the image entrypoint.
    command = ["stdbuf", "-oL", "-eL", "/opt/nvidia/nvidia_entrypoint.sh", *arguments]
    return process(command, work=work, env=env)


def start_pipeline(work):
    return _nvidia_process(work, "deepstream-test5-app", "-c", "deepstream.ini")


def detector_ready():
    return ENGINE.is_file() and ENGINE.with_suffix(".ready").is_file()


def prepare_detector(work, check):
    """Prepare the engine once in the shared Job worker container."""
    _prepare_detector_config(work)
    if detector_ready():
        return
    # A cancelled build can leave an incomplete engine in the worker.
    ready = ENGINE.with_suffix(".ready")
    ready.unlink(missing_ok=True)
    ENGINE.unlink(missing_ok=True)
    width, height = RESOLUTION
    command = [
        "gst-launch-1.0", "-q",
        "nvstreammux", "name=mux", f"width={width}", f"height={height}", f"batch-size={len(CAMERAS)}",
        "!", "nvinfer", f"config-file-path={work / 'detector.ini'}", "!", "fakesink", "sync=false",
    ]
    for index in range(len(CAMERAS)):
        command += [
            "videotestsrc", "num-buffers=1", "pattern=black",
            "!", f"video/x-raw,format=NV12,width={width},height={height}",
            "!", "nvvideoconvert", "!", "video/x-raw(memory:NVMM),format=NV12", "!", f"mux.sink_{index}",
        ]
    with _nvidia_process(work, *command) as (child, tail):
        while child.poll() is None:
            check()
            try:
                child.wait(timeout=.5)
            except subprocess.TimeoutExpired:
                continue
        if child.returncode != 0 or not ENGINE.is_file():
            raise RuntimeError(f"Couldn't prepare the PeopleNet detector.\n{tail()}")
    ready.touch()
