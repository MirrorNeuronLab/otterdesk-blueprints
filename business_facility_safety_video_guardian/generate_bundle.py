#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "mn-skills" / "blueprint_support_skill" / "src"),
)
from mn_blueprint_support import apply_quick_test, log_status, progress, write_manifest


def build_manifest(args: argparse.Namespace) -> dict:
    slack_enabled = "false" if args.disable_slack else "true"
    if args.quick_test and not args.live_ollama_in_quick_test:
        mock_vlm = "true"
    else:
        mock_vlm = "false"

    return {
        "manifest_version": "1.0",
        "graph_id": "business_facility_safety_video_guardian_v1",
        "job_name": "business_facility_safety_video_guardian",
        "requiredContextEngine": False,
        "daemon": True,
        "entrypoints": ["ingress"],
        "initial_inputs": {
            "ingress": [
                {
                    "scenario": "door_camera_safety_monitor",
                    "description": "Continuously sample a 24/7 door camera or looping demo video and alert Slack when Nemotron 3 detects a person.",
                    "ollama_base_url": args.ollama_base_url,
                    "ollama_model": args.ollama_model,
                    "slack_optional": True,
                }
            ]
        },
        "nodes": [
            {
                "node_id": "ingress",
                "agent_type": "router",
                "type": "map",
                "role": "root_coordinator",
                "config": {"emit_type": "video_monitor_start"},
            },
            {
                "node_id": "door_camera_tick_source",
                "agent_type": "module",
                "type": "stream",
                "role": "door_camera_sampler",
                "config": {
                    "module": "MirrorNeuron.Examples.VideoSafetyDoorMonitor.DoorCameraTickSource",
                    "module_source": "beam_modules/door_camera_tick_source.ex",
                    "interval_ms": args.interval_ms,
                    "camera_id": args.camera_id,
                    "target_node": "person_detector",
                },
            },
            {
                "node_id": "person_detector",
                "agent_type": "executor",
                "type": "stream",
                "role": "nemotron3_video_safety_detector",
                "config": {
                    "runner_module": "MirrorNeuron.Runner.HostLocal",
                    "upload_path": "person_detector",
                    "upload_as": "person_detector",
                    "workdir": "/sandbox/job/person_detector",
                    "command": ["python3", "scripts/analyze_door_camera_frame.py"],
                    "output_message_type": None,
                    "environment": {
                        "OLLAMA_BASE_URL": args.ollama_base_url,
                        "OLLAMA_MODEL": args.ollama_model,
                        "OLLAMA_THINK": "false",
                        "VIDEO_SOURCE_URI": args.video_source_uri,
                        "FRAME_SAMPLE_SECONDS": str(args.frame_sample_seconds),
                        "FRAME_JPEG_MAX_WIDTH": str(args.frame_jpeg_max_width),
                        "PERSON_DETECTION_CONFIDENCE_THRESHOLD": str(args.confidence_threshold),
                        "PERSON_ALERT_COOLDOWN_SECONDS": str(args.alert_cooldown_seconds),
                        "SLACK_ALERT_ENABLED": slack_enabled,
                        "SLACK_DEFAULT_CHANNEL": args.slack_channel,
                        "SLACK_MESSAGE_PREFIX": args.slack_message_prefix,
                        "MOCK_VLM_DETECTION": mock_vlm,
                        "MN_BLUEPRINT_LOG_LEVEL": args.log_level,
                    },
                },
            },
        ],
        "edges": [
            {
                "edge_id": "ingress_to_tick_source",
                "from_node": "ingress",
                "to_node": "door_camera_tick_source",
                "message_type": "video_monitor_start",
            },
            {
                "edge_id": "tick_source_to_person_detector",
                "from_node": "door_camera_tick_source",
                "to_node": "person_detector",
                "message_type": "door_camera_frame_tick",
            },
        ],
        "policies": {"recovery_mode": "cluster_recover", "stream_mode": "live"},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the video safety door monitor daemon bundle.")
    parser.add_argument("--interval-ms", type=int, default=5000)
    parser.add_argument("--camera-id", default="front-door")
    parser.add_argument("--video-source-uri", default="samples/door-demo.mp4")
    parser.add_argument("--frame-sample-seconds", type=float, default=5.0)
    parser.add_argument("--frame-jpeg-max-width", type=int, default=896)
    parser.add_argument("--ollama-base-url", default="http://192.168.4.173:11434")
    parser.add_argument("--ollama-model", default="nemotron3:33b")
    parser.add_argument("--confidence-threshold", type=float, default=0.65)
    parser.add_argument("--alert-cooldown-seconds", type=int, default=60)
    parser.add_argument("--slack-channel", default="#safety")
    parser.add_argument("--slack-message-prefix", default="Door camera safety alert")
    parser.add_argument("--disable-slack", action="store_true")
    parser.add_argument("--live-ollama-in-quick-test", action="store_true")
    parser.add_argument("--log-level", default="info")
    parser.add_argument("--quick-test", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()

    quick_test = apply_quick_test(
        args,
        {
            "interval_ms": 1000,
            "frame_sample_seconds": 1.0,
            "alert_cooldown_seconds": 3,
            "disable_slack": True,
        },
    )
    args.interval_ms = max(args.interval_ms, 250)
    args.frame_sample_seconds = max(args.frame_sample_seconds, 0.25)
    args.frame_jpeg_max_width = max(args.frame_jpeg_max_width, 64)
    args.alert_cooldown_seconds = max(args.alert_cooldown_seconds, 0)

    log_status(
        "business_facility_safety_video_guardian",
        "generating video safety door monitor bundle",
        phase="generate",
        details={
            "quick_test": quick_test,
            "video_source_uri": args.video_source_uri,
            "ollama_model": args.ollama_model,
            "slack_enabled": not args.disable_slack,
        },
    )

    bundle_dir = args.output_dir
    bundle_dir.mkdir(parents=True, exist_ok=True)
    payloads_dir = bundle_dir / "payloads"
    payloads_dir.mkdir(parents=True, exist_ok=True)
    if bundle_dir.resolve() != Path(__file__).resolve().parent:
        shutil.copytree(Path(__file__).resolve().parent / "payloads", payloads_dir, dirs_exist_ok=True)

    write_manifest(
        bundle_dir / "manifest.json",
        build_manifest(args),
        blueprint_id="business_facility_safety_video_guardian",
        quick_test=quick_test,
    )
    print(progress("bundle generated", 1, 1), file=sys.stderr)
    print(bundle_dir)


if __name__ == "__main__":
    main()
