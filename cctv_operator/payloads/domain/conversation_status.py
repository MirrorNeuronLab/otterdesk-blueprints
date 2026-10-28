"""Readable Chat summaries of observed camera and analysis state."""


def operator_status_summary(state):
    metrics = state.get("metrics") or {}
    pipeline = state.get("pipeline") or {}
    person = pipeline.get("person_events") or {}
    captions = pipeline.get("captions") or {}
    timestamp = metrics.get("last analyzed")
    finding = metrics.get("latest finding")
    has_analysis = bool(finding) and timestamp not in (None, "", "waiting")
    # The dashboard metric is a short preview; retain the authored activity
    # account when the operator asks about the latest completed sample.
    understanding = (state.get("understanding") or {}).get("scene_understanding")
    if has_analysis and isinstance(understanding, str) and understanding.strip():
        finding = understanding.strip()[:1800]
    paragraphs = ([f"Latest analyzed sample at {timestamp}:\n\n{finding}"]
                  if has_analysis and finding else ["I don't have a completed scene analysis yet."])
    if has_analysis and (state.get("understanding") or {}).get("source_profile") == "bundled_demo":
        paragraphs.append("Recorded demo playback; capture times describe playback, not a live site event.")
    preview = metrics.get("preview")
    camera = {
        "live": "Video is arriving. Scene analysis has separate health.",
        "starting": "The video connection is starting.",
        "connecting": "Connecting to the camera.",
        "reconnecting": "Reconnecting to the camera; fresh video is not confirmed yet.",
        "unavailable": "Video is unavailable.",
        "disabled": "The preview is disabled; check analysis health separately.",
    }.get(preview, "No current video connection status is available.")
    details = [f"- Camera: {camera}"]
    if person.get("summary"):
        details.append(f"- Person detection: {person['summary']}")
    if captions.get("summary"):
        details.append(f"- Scene analysis: {captions['summary']}")
    paragraphs.append("\n".join(details))
    warning = state.get("warning")
    if warning:
        paragraphs.append(str(warning))
    needs_review = (metrics.get("status") in {"Analysis error", "Analysis delayed"}
                    or person.get("person_detector") == "failed"
                    or captions.get("inflight_status") == "stalled"
                    or person.get("captions") == "failed")
    if needs_review:
        paragraphs.append("Check scene-analysis status and any error details in the progress panel. Missing analysis does not mean the scene is clear.")
    elif preview in {"reconnecting", "unavailable"}:
        paragraphs.append("Check that the NVIDIA computer can reach the approved stream. Keep its address and credentials in the secure Video stream URL field.")
    elif not has_analysis:
        paragraphs.append("Follow startup in the progress panel. Once observations are saved, ask “Summarize the video”.")
    else:
        paragraphs.append("Review the evidence frame before acting. This is a sampled observation, not continuous coverage.")
    return "\n\n".join(paragraphs)


def monitoring_command_summary(state, *, clear=False, instruction="", analysis_ready=False, finding=None):
    if state != "completed":
        return ("Your monitoring goal change is queued. It has not been confirmed as applied; "
                "the next analysis will use the new goal only after it is applied.")
    applied = ("The configured monitoring goal has been restored." if clear else
               f"The monitoring goal is now: {instruction}")
    if analysis_ready and finding:
        return f"{applied}\n\nLatest analysis for this goal:\n\n{finding}\n\nReview its evidence frame before acting."
    return (f"{applied}\n\nA scene analysis for this goal is not available yet. "
            "Check monitoring status for the next eligible sample; an earlier finding does not confirm the new goal.")
