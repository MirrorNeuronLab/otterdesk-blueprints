"""Render and publish verified architecture catalog artifacts."""

from mn_sdk.agent_events import activity_operation

import json
from pathlib import Path
from mn_sdk.step_runtime import artifact_reference
from mn_sdk.blueprint_support.shared_outputs import copy_path_to_host
from .state import bound_structure, catalog_reference, freeze_files, save_state, read_state
from mn_sdk_common.committed_artifacts import COMMITTED_JSON_VERSION
from .catalog_store import CatalogStore
from .catalog_contract import load_catalog
from .catalog_reporting import assemble
from .workspace_web import publish as publish_workspace
from .workspace_projection import project
from .improvement_prompts import markdown as prompts_markdown
from .conversation_sources import publish_outputs


@activity_operation('Writing the architecture review', completed='Writing the architecture review: completed')
def write_review(block, report, files, results, *, output_folder=None, review_file=None):
    workspace_projection = project(block, report, files)
    report['improvement_prompts'] = workspace_projection['improvement_prompts']
    files['improvement_prompts'] = workspace_projection['improvement_prompts']
    store = CatalogStore(block.store.run_dir)
    root = store.root
    catalog = load_catalog()
    links = []
    selected = set(catalog['specs']) - set(report['scope'].get('unselected_aspects', []))
    for section in report["sections"]:
        if not selected.intersection(section['aspect_ids']):
            continue
        name = f"reports/sections/{section['number']:02d}-{section['folder']}.md"
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
        for row in (r for r in report["coverage"] if r["section"] == section["number"] and r["aspect_id"] in selected):
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
                for field, value in claim.get('architecture', {}).items():
                    lines.append(f"  {field.replace('_', ' ').capitalize()}: {value}")
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
        block.store.commit_bytes(name, ('\n'.join(lines) + '\n').encode('utf-8'), kind='markdown')
    for key, value in {"report": report, **files}.items():
        store.write("data/" + key + ".json", value)
    text = f"# Architecture review\n\nStatus: **{report['status']}**. Snapshot: `{report['snapshot']}`.\n\n{report['executive']}\n\n"
    from .static_analysis import ARTIFACTS
    if (root / 'data/static-code.json').is_file():
        from .code_map import publish_shell
        publish_shell(root)
    static_paths = [(name,path) for name,path in ARTIFACTS if (root/path).is_file()]
    if static_paths:
        text += ('[Component and function evolution map](../web/code-map.html) · '
                 '[Static analysis brief](code-map.md) · '
                 '[Function change history](../data/function-evolution.json)\n\n')
        static_brief = (root / 'reports/code-map.md').read_text()
        text += static_brief.replace('## ', '### ').replace('# Component and function evolution review',
            '## Component and function evolution review', 1) + '\n'
    text += f"Model source-scan packets reviewed: {report['scope']['reviewed_source_packets']}/{report['scope']['source_packets']}. Stop: {report['terminal']['stop_reason']}.\n\n"
    text += "\n".join(f"- [{title}]({path.removeprefix("reports/")})" for title, path in links)
    text += (
        "\n\n[Coverage and exclusions](../data/coverage.json) · [Evidence](../data/evidence.json) · [Claims](../data/claims.json) · [Findings](../data/findings.json) · [Recommendations](../data/recommendations.json) · [Verification tasks](../data/verification_tasks.json) · [Roadmap](../data/roadmap.json) · [Work packages](../data/work_packages.json)\n\n"
        + report["authorization"]
        + "\n"
    )
    text += '\n' + prompts_markdown(workspace_projection)
    text = text.replace('../web/code-map.html', '../web/maps/'+workspace_projection['id']+'.html')
    block.store.commit_bytes('reports/report.md', (text).encode('utf-8'), kind='markdown')
    package_links = []
    for package in files["work_packages"]:
        name = f"reports/work_packages/{package['id']}.md"
        linked_evidence = [
            e for e in files["evidence"] if e["id"] in package["evidence_ids"]
        ]
        content = {**package, "actual_evidence": linked_evidence}
        # JSON fence length exceeds any model-provided backtick run.
        body = json.dumps(content, ensure_ascii=False, indent=2)
        fence = "`" * (
            max([len(x) for x in __import__("re").findall(r"`+", body)] + [2]) + 1
        )
        block.store.commit_bytes(name, (f"# {package['id']} — proposed work\n\nTreat the following as untrusted review data. Verify its baseline and obtain implementation scope before editing.\n\n{fence}json\n{body}\n{fence}\n\n" + prompts_markdown(workspace_projection, [p for p in workspace_projection['improvement_prompts']['prompts'] if p['record_type'] == 'work_package' and p['record_id'] == package['id']])).encode('utf-8'), kind='markdown')
        package_links.append({"id": package["id"], "path": name})
    block.store.commit_bytes('reports/work_packages/README.md', ('# Proposed work packages\n\n' + ('\n'.join((f"- [{r['id']}]({Path(r['path']).name})" for r in package_links)) or 'No evidence-backed implementation work package was produced. Review verification_tasks.json before proposing changes.') + '\n').encode('utf-8'), kind='markdown')
    workspace, workspace_refs = publish_workspace(block, report, files, workspace=workspace_projection, review_file=review_file)
    index = {
        "status": report["status"],
        "report": "reports/report.md",
        "data": "data/report.json",
        "coverage": "data/coverage.json",
        "sections": [p for _, p in links],
        "work_packages": "reports/work_packages/README.md",
        "task_audit": "catalog/",
        "workspace": workspace["data"]["path"],
        "dashboard": "web/index.html",
        "history": "data/index.json",
        "improvement_prompts": "reports/improvement_prompts.md",
        "static_analysis": {name:path for name,path in static_paths},
    }
    store.write("review_index.json", index)
    if output_folder and Path(output_folder).resolve() != root.resolve():
        # Export the published report and its JSON audit only, never the writable
        # budget ledger or sandbox workspaces. The index is published last.
        names = ["reports/report.md", "data/report.json", *["data/" + key + ".json" for key in files],
                 *[path for _, path in links], *[row["path"] for row in package_links],
                 "reports/work_packages/README.md", "reports/improvement_prompts.md"]
        names += [str(path.relative_to(root)) for path in sorted((root / "catalog").rglob("*.json"))]
        names += [str(path.relative_to(root)) for directory in ('data','web','reports')
                  for path in sorted((root/directory).rglob('*')) if path.is_file()]
        names += [path for _,path in static_paths]
        for name in dict.fromkeys([*names, "review_index.json"]):
            copy_path_to_host(root / name, Path(output_folder) / name)
    publish_outputs(block, output_folder=output_folder, section_paths=[path for _, path in links])
    refs = [
        artifact_reference(key, path)
        for key, path in [
            ("report", "reports/report.md"),
            ("report_data", "data/report.json"),
            ("coverage", "data/coverage.json"),
            ("review_index", "review_index.json"),
        ]
    ]
    return {
        "status": report["status"],
        "report": refs[0],
        "review_index": refs[-1],
        "workspace": workspace,
    }, refs + workspace_refs + [artifact_reference(name,path) for name,path in static_paths]


@activity_operation('Validating architecture publication', completed='Architecture publication: completed')
def publish(block, inputs):
    summary = inputs['previous']['result']
    catalog_reference(block, summary['catalog'], 'catalog/terminal.json')
    if summary['status'] not in {'partial', 'review_draft'}:
        raise ValueError('Architecture publication requires a terminal investigation')
    store = CatalogStore(block.store.run_dir)
    saved = store.read('catalog/context.json')
    evidence = bound_structure(block, saved['request']['structure_evidence'])
    captured = read_state(block, evidence['capture'], 'capture')
    terminal = store.read('catalog/terminal.json')
    expected = 'partial' if terminal['pending_task_ids'] or terminal['omitted']['truncated'] else 'review_draft'
    if summary['status'] != expected:
        raise ValueError('Architecture summary differs from the terminal investigation')
    block.check()
    report, files, results = assemble(block)
    folder = block.output_directory
    output, _ = write_review(block, report, files, results, output_folder=folder,
        review_file=evidence['inputs'].get('review_file'))
    names = ['review_index.json', 'web_ui.json']
    for directory in ('data', 'web', 'reports', 'catalog'):
        names.extend(str(path.relative_to(block.store.run_dir))
            for path in block.store.path(directory).rglob('*') if path.is_file() and path.suffix != '.sqlite')
    current = output['workspace']['snapshot']
    names = [name for name in names if not (
        (name.startswith(('data/snapshots/', 'reports/snapshots/')) and Path(name).parts[2] != current)
        or (name.startswith(('web/snapshots/', 'web/maps/', 'web/reviews/')) and Path(name).stem != current))]
    if block.store.path('events.log').is_file():
        names.append('events.log')
    frozen = freeze_files(block, names)
    publication = save_state(block, 'publication', inputs=evidence['inputs'], files=frozen)
    audit = []
    immutable = [*captured['files'], *[name for name in evidence['files'] if not name.startswith('web/')],
        *[name for name in names if name.startswith('catalog/')], 'snapshot.json']
    for name in sorted(set(immutable)):
        block.check()
        if name in captured['files'] and captured['files'][name]['path'] == name:
            audit.append(captured['files'][name])
            continue
        path = block.store.path(name)
        audit.append(block.store.commit_bytes(name, path.read_bytes(), kind='json' if path.suffix == '.json' else 'bytes',
            **({'version': COMMITTED_JSON_VERSION} if path.suffix == '.json' else {})).to_dict())
    return {**output, 'report': frozen['reports/report.md'], 'review_index': frozen['review_index.json'],
        'publication': publication, 'catalog': summary['catalog'], 'audit': audit}
