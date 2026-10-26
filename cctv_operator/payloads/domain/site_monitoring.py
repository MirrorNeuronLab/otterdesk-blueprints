"""Facility review policy: frame-bound observations, never an autonomous safety verdict."""
import math

from .goal_events import goal_event

RULES = {
    "group_presence": {"title": "A group of people is visible", "severity": "low", "test": "At least two real people are visible together in the same selected frame. Notify on first observation even if they are already present at monitoring startup, stationary, or wearing helmets. Do not require a hazard or proof of arrival; say a group is visible unless sampled before-and-after frames establish that it appeared.", "review": "Review the group and its visible activity in the sampled camera view."},
    "blocked_route": {"title": "Visible travel-path obstruction", "severity": "high", "test": "An object visibly obstructs the designated travel path; perspective or clearance uncertainty is possible, not confirmed.", "review": "Ask the duty operator to verify the path on the live camera and inspect the area if appropriate."},
    "vehicle_proximity": {"title": "Person near moving industrial equipment", "severity": "high", "test": "Person and industrial vehicle approach or cross the same visible area across multiple frames; no invented distance, speed or collision certainty.", "review": "Have the site operator review the sampled motion and separation; follow the site's approved safety procedure."},
    "uncovered_head": {"title": "Clearly visible uncovered head", "severity": "medium", "test": "A clearly visible uncovered head, with a not_worn helmet observation on that exact frame. PPE applicability is a site-policy question, not established by the camera.", "review": "Confirm whether this is a designated PPE area and review the original view before taking any action."},
    "person_on_floor": {"title": "Person appears down on the floor", "severity": "high", "test": "A visible person is lying or down on the floor. Do not diagnose injury, infer a fall from one frame, or infer intent.", "review": "Ask the duty operator to check the current view and follow the site's welfare-check procedure."},
    "possible_spill": {"title": "Possible spill or floor hazard", "severity": "medium", "test": "A visible floor patch or object may affect a walking path. Reflections and unknown surface condition remain uncertain; video cannot confirm slipperiness.", "review": "Ask housekeeping or the duty operator to inspect the area and confirm the surface condition."},
}
PROFILES = {
    "factory": {"goal": "Notify when a group of two or more people is visible together, or for visible travel-path obstructions, a person near moving industrial equipment, or a clearly visible uncovered head; distinguish observations from possible risks.", "rules": ["group_presence", "blocked_route", "vehicle_proximity", "uncovered_head"]},
    "hotel": {"goal": "Watch approved public/common areas and notify when a group of two or more people is visible together, or for visible travel-path obstructions, a person appearing down on the floor, or possible spills; distinguish observations from possible risks.", "rules": ["group_presence", "blocked_route", "person_on_floor", "possible_spill"]},
    "custom": {"goal": "", "rules": []},
}


def _finding_priority(finding):
    return ({"high": 0, "medium": 1, "low": 2}[finding["severity"]], -finding["confidence"], finding["rule_id"])


def context(config):
    settings = config.get("site") or {}
    profile = settings.get("profile", "custom")
    if profile not in PROFILES:
        raise ValueError("site.profile must be factory, hotel or custom")
    rule_ids = settings.get("rule_ids", PROFILES[profile]["rules"])
    if (not isinstance(rule_ids, list) or any(not isinstance(i, str) for i in rule_ids) or len(rule_ids) > 8
            or (profile != "custom" and not rule_ids) or len(set(rule_ids)) != len(rule_ids) or not set(rule_ids) <= set(PROFILES[profile]["rules"])):
        raise ValueError("site.rule_ids must be unique rules belonging to the selected profile")
    zones = settings.get("zones", [])
    if not isinstance(zones, list) or len(zones) > 12:
        raise ValueError("site.zones supports at most twelve named full-view rectangles")
    seen = set()
    for zone in zones:
        if not isinstance(zone, dict) or set(zone) != {"id", "name", "bounds"}:
            raise ValueError("Each site zone needs id, name and normalized bounds")
        if any(not isinstance(zone[k], str) or not 0 < len(zone[k].strip()) <= 100 for k in ("id", "name")) or zone["id"] in seen:
            raise ValueError("Site zone IDs/names must be bounded and IDs unique")
        seen.add(zone["id"])
        bounds = zone["bounds"]
        if (not isinstance(bounds, list) or len(bounds) != 4 or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in bounds)
                or not bounds[0] < bounds[2] or not bounds[1] < bounds[3]):
            raise ValueError("Zone bounds must be normalized x1,y1,x2,y2 with positive area")
    owner = settings.get("review_owner", "Unassigned")
    if not isinstance(owner, str) or not 0 < len(owner.strip()) <= 100:
        raise ValueError("site.review_owner must be a bounded operator-supplied name or role")
    return {"profile": profile, "rules": [{"id": key, **RULES[key]} for key in rule_ids], "zones": zones,
            "review_owner": owner, "profile_goal": PROFILES[profile]["goal"],
            "qualification": "Operator-configured areas and rules. Rectangles guide interpretation; they are not privacy masks or calibrated world coordinates. No identity, injury diagnosis, intent, legal compliance, safe-clearance certification or automatic physical action."}


def admission(batch, config):
    gate = batch.get("candidate_gate") or {}
    if gate.get("detector") == "RF-DETR" and gate.get("condition") == "person" and gate.get("confirmed") is True:
        return "person_gated_cosmos"
    interval = float((config.get("sampling") or {}).get("scene_audit_seconds", 0))
    if interval > 0 and gate.get("condition") == "scene_audit" and gate.get("detector") == "scheduled_scene_review" and batch.get("trigger") == "scene_audit":
        return "periodic_scene_audit"
    raise ValueError("Cosmos analysis requires a confirmed RF-DETR person gate or configured periodic scene audit")


def _frames(indices, batch):
    rows = batch["selected_frames"]
    if (not isinstance(indices, list) or not 1 <= len(indices) <= 12
            or any(type(i) is not int or not 1 <= i <= len(rows) for i in indices) or len(set(indices)) != len(indices)):
        raise ValueError("Site observations and predictions require valid selected evidence_frames")
    return [{"frame": i, "timestamp": rows[i - 1]["timestamp"], "path": rows[i - 1]["path"]} for i in sorted(indices)]


def enrich(detection, batch, config, goal, attention):
    site = context(config)
    raw = detection.get("site_findings", [])
    if not isinstance(raw, list) or len(raw) > 8:
        raise ValueError("site_findings must be a bounded list")
    rules = {r["id"]: r for r in site["rules"]}
    findings, seen = [], set()
    for item in raw:
        if not isinstance(item, dict) or item.get("rule_id") not in rules or item["rule_id"] in seen:
            raise ValueError("Site findings must name each configured rule at most once")
        if set(item) != {"rule_id", "status", "confidence", "visible_evidence", "evidence_frames"}:
            raise ValueError("Site findings must follow the declared bounded field contract")
        seen.add(item["rule_id"])
        if item.get("status") not in {"observed", "possible", "not_observed"}:
            raise ValueError("Site finding requires observed, possible or not_observed status")
        text, confidence = item.get("visible_evidence"), item.get("confidence")
        if not isinstance(text, str) or not 0 < len(text.strip()) <= 800 or type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("Site finding needs bounded visible evidence and finite confidence")
        refs = _frames(item.get("evidence_frames"), batch)
        if item["rule_id"] == "uncovered_head" and item["status"] == "observed":
            clear = {h["evidence_frame"] for h in detection.get("helmet_observations", []) if h["helmet_status"] == "not_worn" and h["head_visible"] is True}
            if not clear.intersection(item["evidence_frames"]):
                raise ValueError("An uncovered-head observation needs same-frame visible-head evidence")
        if item["rule_id"] == "vehicle_proximity" and item["status"] == "observed" and len(refs) < 2:
            raise ValueError("Observed approach requires at least two sampled frames")
        rule = rules[item["rule_id"]]
        findings.append({**item, "evidence_refs": refs, "severity": rule["severity"], "title": rule["title"],
            "recommended_review": rule["review"], "review_owner": site["review_owner"], "review_state": "unreviewed_visual_inference",
            "qualification": "Sampled visual interpretation, not a confirmed incident or compliance determination"})
    for prediction in detection.get("risk_predictions", []):
        if site["profile"] != "custom":
            prediction["evidence_refs"] = _frames(prediction.get("evidence_frames"), batch)
            prediction["review_owner"] = site["review_owner"]
            prediction["confidence_basis"] = "Model self-report; not a calibrated probability"
    # The profile's multi-rule goal must have a frame-bound observed basis.
    # An explicitly steered custom goal retains its existing independent checks.
    if site["profile"] != "custom" and not attention and goal == site["profile_goal"]:
        observed = [f for f in findings if f["status"] == "observed"]
        detection["detected_target"] = bool(observed)
        detection["detected"] = bool(observed)
        detection["detection_count"] = len(observed)
        if observed:
            chosen = min(observed, key=_finding_priority)
            indices = sorted(chosen["evidence_frames"])
            detection.update(confidence=chosen["confidence"], risk_level=chosen["severity"], detection_report=chosen["visible_evidence"],
                goal_event={"start_frame": indices[0], "end_frame": indices[-1], "evidence_frame": indices[-1]})
        else:
            detection["goal_event"] = None
    detection.update(site_findings=findings, site_context=site,
        site_coverage={"examined_rule_ids": sorted(seen), "unexamined_rule_ids": sorted(set(rules) - seen),
                       "definition": "Model examined these rules in this bounded sample; not continuous coverage or proof of absence"})
    return detection


def notice_state(detection, batch, config, policy, state, goal, attention):
    """Distinct facility rules rearm independently; uncertain/missing views do not clear them."""
    import time
    site = context(config)
    if site["profile"] == "custom" or attention or goal != site["profile_goal"]:
        return state
    active = set(state.get("active_site_rules", []))
    for finding in detection["site_findings"]:
        if finding["status"] == "not_observed" and finding["confidence"] >= policy["min_confidence"]:
            active.discard(finding["rule_id"])
    state["active_site_rules"] = sorted(active)
    clocks = state.get("site_notice_clocks", {})
    now = time.time()
    candidates = [f for f in detection["site_findings"] if f["status"] == "observed" and f["rule_id"] not in active
        and f["confidence"] >= policy["min_confidence"] and now - clocks.get(f["rule_id"], 0) >= policy["cooldown_seconds"]]
    detection["site_notice_rule_ids"] = []
    if not candidates:
        return {**state, "notified_goal": goal}
    chosen = min(candidates, key=_finding_priority)
    # Only the finding actually reported is consumed. Other new findings remain
    # eligible for their own notice, including a group alongside a hazard.
    detection["site_notice_rule_ids"] = [chosen["rule_id"]]
    # Bind this notice to its chosen newly observable rule's already validated frame.
    indices = sorted(chosen["evidence_frames"])
    raw = {"detected_target": True, "goal_event": {"start_frame": indices[0], "end_frame": indices[-1], "evidence_frame": indices[-1]}}
    detection.update(confidence=chosen["confidence"], risk_level=chosen["severity"],
                     detection_report=chosen["visible_evidence"], goal_event=goal_event(raw, batch))
    detection["observed_at"] = detection["goal_event"]["observed_at"]
    return {**state, "notified_goal": None, "last_alert_wall_ts": 0}


def record_notice(detection, state, timestamp):
    identifiers = detection.get("site_notice_rule_ids", [])
    if identifiers:
        state["active_site_rules"] = sorted(set(state.get("active_site_rules", [])) | set(identifiers))
        state["site_notice_clocks"] = {**state.get("site_notice_clocks", {}), **dict.fromkeys(identifiers, timestamp)}
