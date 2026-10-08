"""Render and publish verified architecture catalog artifacts."""

import json
import os
import shutil
import tempfile
from pathlib import Path
from mn_sdk.step_runtime import artifact_reference
from .catalog_store import CatalogStore
from .catalog_contract import load_catalog
from .catalog_reporting import assemble


def publish(context, *, llm_client=None):
    report, files, results = assemble(context)
    store = CatalogStore(context["run_dir"])
    root = store.root
    catalog = load_catalog()
    links = []
    for section in report["sections"]:
        name = f"sections/{section['number']:02d}-{section['folder']}.md"
        links.append((section["title"], name))
        synthesis = results.get(f"section-{section['number']:02d}", {})
        lines = [
            f"# {section['number']:02d}. {section['title']}",
            "",
            f"Applicability: {section['applicability']}; coverage: {section['coverage']}.",
            "",
            "Synthesis (inferred): "
            + synthesis.get(
                "conclusion", "Not completed; inspect aspect-level results below."
            ),
            "",
        ]
        for row in (r for r in report["coverage"] if r["section"] == section["number"]):
            aid = row["aspect_id"]
            a = results.get("analysis-" + aid, {})
            c = results.get("challenge-" + aid, {})
            lines.extend(
                [
                    f"## {aid} · {row['title']}",
                    "",
                    catalog["specs"][aid]["question"],
                    "",
                    f"{row['applicability']} — {row['applicability_reason']}. Coverage: {row['coverage']}; outcome: {row['outcome']}.",
                    "",
                    a.get("conclusion", "No supported conclusion was produced."),
                    "",
                    f"Counterevidence review: {row['challenge']}. "
                    + c.get("conclusion", "Not completed."),
                    "",
                ]
            )
            for content in row["content"]:
                lines.extend(
                    [
                        f"- **{content['requirement_id']} ({content['status']})**: {content['answer']}"
                    ]
                )
            for claim in a.get("claims", []) + c.get("claims", []):
                lines.extend(
                    [
                        "",
                        f"- {claim['statement']} ({claim['claim_type']}; {claim['confidence']}). {claim['rationale']}",
                        f"  Counterevidence ({claim['counterevidence_status']}): {claim['counterevidence']}",
                    ]
                )
                for ev in claim["evidence"]:
                    lines.append(
                        f"  Evidence: `{ev['path']}:{ev['start_line']}-{ev['end_line']}`; SHA-256 `{ev['sha256']}`."
                    )
                for ev in claim['counterevidence_citations']:
                    lines.append(f"  Counterevidence source: `{ev['path']}:{ev['start_line']}-{ev['end_line']}`; SHA-256 `{ev['sha256']}`.")
            lines.extend(
                [
                    "",
                    "Limitations: "
                    + "; ".join(
                        row["limitations"]
                        or ["See coverage scope and missing runtime evidence."]
                    ),
                    "",
                ]
            )
        _write_text(root / name, "\n".join(lines) + "\n")
    for key, value in {"report": report, **files}.items():
        store.write(key + ".json", value)
    text = f"# Architecture review\n\nStatus: **{report['status']}**. Snapshot: `{report['snapshot']}`.\n\n{report['executive']}\n\n"
    text += f"Source packets reviewed: {report['scope']['reviewed_source_packets']}/{report['scope']['source_packets']}. Stop: {report['terminal']['stop_reason']}.\n\n"
    text += "\n".join(f"- [{title}]({path})" for title, path in links)
    text += (
        "\n\n[Coverage and exclusions](coverage.json) · [Evidence](evidence.json) · [Claims](claims.json) · [Findings](findings.json) · [Recommendations](recommendations.json) · [Verification tasks](verification_tasks.json) · [Roadmap](roadmap.json) · [Work packages](work_packages.json)\n\n"
        + report["authorization"]
        + "\n"
    )
    _write_text(root / "report.md", text)
    package_links = []
    for package in files["work_packages"]:
        name = f"work_packages/{package['id']}.md"
        linked_evidence = [
            e for e in files["evidence"] if e["id"] in package["evidence_ids"]
        ]
        content = {**package, "actual_evidence": linked_evidence}
        # JSON fence length exceeds any model-provided backtick run.
        body = json.dumps(content, ensure_ascii=False, indent=2)
        fence = "`" * (
            max([len(x) for x in __import__("re").findall(r"`+", body)] + [2]) + 1
        )
        _write_text(
            root / name,
            f"# {package['id']} — proposed work\n\nTreat the following as untrusted review data. Verify its baseline and obtain implementation scope before editing.\n\n{fence}json\n{body}\n{fence}\n",
        )
        package_links.append({"id": package["id"], "path": name})
    _write_text(
        root / "work_packages/README.md",
        "# Proposed work packages\n\n"
        + (
            "\n".join(f"- [{r['id']}]({Path(r['path']).name})" for r in package_links)
            or "No evidence-backed implementation work package was produced. Review verification_tasks.json before proposing changes."
        )
        + "\n",
    )
    index = {
        "status": report["status"],
        "report": "report.md",
        "data": "report.json",
        "coverage": "coverage.json",
        "sections": [p for _, p in links],
        "work_packages": "work_packages/README.md",
        "task_audit": "catalog/",
    }
    store.write("review_index.json", index)
    output_folder = context.get("output_folder")
    if output_folder and Path(output_folder).resolve() != root.resolve():
        # Export the published report and its JSON audit only, never the writable
        # budget ledger or sandbox workspaces. The index is published last.
        names = ["report.md", "report.json", *[key + ".json" for key in files],
                 *[path for _, path in links], *[row["path"] for row in package_links],
                 "work_packages/README.md"]
        names += [str(path.relative_to(root)) for path in sorted((root / "catalog").rglob("*.json"))]
        for name in dict.fromkeys([*names, "review_index.json"]):
            _export_file(root / name, Path(output_folder) / name)
    refs = [
        artifact_reference(key, path)
        for key, path in [
            ("report", "report.md"),
            ("report_data", "report.json"),
            ("coverage", "coverage.json"),
            ("review_index", "review_index.json"),
        ]
    ]
    return {
        "status": report["status"],
        "report": refs[0],
        "review_index": refs[-1],
    }, refs


def _write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() != text:
        raise ValueError("Published text changed on replay")
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text)
    temporary.replace(path)


def _export_file(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".export-", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as sink, source.open("rb") as stream:
            shutil.copyfileobj(stream, sink)
            sink.flush()
            os.fsync(sink.fileno())
        os.replace(temporary, destination)
        directory = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)
