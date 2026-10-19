"""Rule-specific views on the shared offline report template."""
from pathlib import Path

from mn_web_report_skill import render_document


def render(report, capture):
    if report["snapshot_id"] != capture["snapshot_id"]:
        raise ValueError("Report and captured source identities differ")
    assets = Path(__file__).with_name("workspace_assets")
    return render_document(
        title="Code verification", identity="Captured software",
        content_html='<main id="content" tabindex="-1"></main><p id="notice" role="status" aria-live="polite"></p>',
        script=(assets / "workspace.js").read_text(),
        style=(assets / "workspace.css").read_text(),
        data={"report": report, "sources": capture["sources"]},
        description=(f"Partial extraction: {len(report.get('coverage', {}).get('extraction_gaps', []))} unresolved "
                     "source sections. Listed rules only; missing requirements are not assessed. "
                     if report.get('coverage', {}).get('extraction_gaps') else '')
                    + "Static source review · Repository code and tests were not executed.",
    )
