"""Compose a saved review from synthetic camera observations."""

from .layout import DOORS


def render(snapshot):
    from mn_web_report_skill import render_report_html

    stamp = snapshot["observed_at"]
    recent = snapshot["recent_crossings"]
    entered, left = snapshot["entered"], snapshot["left"]
    labels = {door.id: door.label for door in DOORS}
    assessment = (f"The tracker counted {entered} entries and {left} exits. Last tracking observation {stamp}."
                  if stamp else "No tracking observation was recorded. Guest traffic could not be assessed.")
    evidence = []
    if stamp:
        evidence.append({"type": "table", "columns": ["Simulated door", "Entries", "Exits"], "rows": [
            [label, snapshot["doors"][key]["entered"], snapshot["doors"][key]["left"]] for key, label in labels.items()]})
    if recent:
        evidence.append({"type": "table", "columns": ["Observation time", "Door", "Direction"], "rows": [
            [event["observed_at"], labels[event["door"]], event["direction"]] for event in recent]})
    else:
        evidence.append({"type": "paragraph", "text": "The recent event list contains no recorded crossings."})
    return render_report_html({"title": "Hotel crossing report", "identity": "Synthetic lobby · " + snapshot["status"],
        "sections": [
            {"id": "assessment", "title": "Assessment", "blocks": [{"type": "paragraph", "text": assessment}]},
            {"id": "evidence", "title": "Crossing evidence", "blocks": evidence},
            {"id": "coverage", "title": "Coverage", "blocks": [{"type": "paragraph", "text":
                f"The event list shows {len(recent)} of {entered + left} recorded door crossings. "
                "One guest can cross several times. Compare the direction, door and observation time with people_counts.json. "
                "Occlusion and tracking errors can affect the counts."}]},
        ]})
