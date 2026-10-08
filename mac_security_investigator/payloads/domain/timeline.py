"""Inert SVG projections of supported evidence; no speculative causal arrows."""
from datetime import datetime, timezone
import html

from mn_temporal_graph_skill.temporal import timestamp


def project(history, revision, records_limit):
    items = []
    for scan in history.scans(revision):
        items.append({"kind": "acquisition", "lane": "Scan acquisition", "label": scan["scan_id"],
                      "time": scan["acquisition"], "known_from_revision": scan["revision"]})
    records = history.assertions(revision)
    for record in records[:records_limit]:
        items.append({"kind": record["kind"], "lane": record["scope"] + " · " + record["entity"],
                      "label": record["kind"] + " · " + record["capability"], "time": record["time"],
                      "known_from_revision": record["known_from_revision"], "evidence_refs": record["evidence_refs"],
                      "claim_class": record["claim_class"], "uncertain": bool(record.get("conflicts"))})
    return {"items": items, "complete": len(records) <= records_limit,
            "qualification": "Occurrence/state time and separate scan markers; gaps do not imply continuous observation."}


def render(timeline):
    esc = lambda value: html.escape(str(value), quote=True)
    items = timeline["items"]
    known = [timestamp(v) for i in items for v in i["time"].values() if v is not None]
    if not known:
        return "<p>Timeline bounds are unknown.</p>"
    low, high = min(known), max(known)
    lanes = list(dict.fromkeys(i["lane"] for i in items))
    scale = lambda t: 190 + 680 * (t - low) / max(1, high - low)
    height = 70 + 55 * len(lanes)
    parts = [f"<svg role='img' aria-label='Evidence timeline with separate scan acquisition markers' viewBox='0 0 920 {height}' style='width:100%;height:auto'>"]
    for i, lane in enumerate(lanes):
        y = 50 + 55 * i
        label = lane if len(lane) < 24 else lane[:21] + "…"
        parts += [f"<text x='0' y='{y+4}' font-size='12'><title>{esc(lane)}</title>{esc(label)}</text>",
                  f"<line x1='190' x2='870' y1='{y}' y2='{y}' stroke='#d5dfe2'/>" ]
    for item in items:
        a, b = (timestamp(item["time"][k]) for k in ("earliest", "latest"))
        if a is None or b is None:
            continue
        x, end = scale(a), scale(b)
        y = 50 + 55 * lanes.index(item["lane"])
        title = esc(f"{item['label']} | {item['time']['earliest']} — {item['time']['latest']} | first known revision {item['known_from_revision']}")
        color = "#547782" if item["kind"] == "acquisition" else "#98652b" if item["kind"] == "event" else "#256a62"
        if item["kind"] == "acquisition":
            parts.append(f"<line x1='{x:.2f}' x2='{x:.2f}' y1='25' y2='{height-35}' stroke='{color}' stroke-dasharray='3 5'><title>{title}</title></line>")
        if a != b:
            parts.append(f"<rect x='{x:.2f}' y='{y-9}' width='{max(2,end-x):.2f}' height='18' fill='{color}' opacity='.25'><title>{title}</title></rect>")
        shape = f"<rect x='{x-4:.2f}' y='{y-4}' width='8' height='8'" if item["kind"] == "state" else f"<circle cx='{x:.2f}' cy='{y}' r='4'"
        parts.append(shape + f" fill='{color}'><title>{title}</title></" + ("rect>" if item["kind"] == "state" else "circle>"))
    for t, x in ((low, 190), (high, 870)):
        parts.append(f"<text x='{x}' y='{height-8}' text-anchor='middle' font-size='11'>{datetime.fromtimestamp(t, timezone.utc).strftime('%b %d %H:%M UTC')}</text>")
    parts.append("</svg><p>Squares: observed state. Circles: event records. Dashed lines: scan acquisition. Bands: time uncertainty. Unobserved intervals remain unknown.</p>")
    return "".join(parts)
