"""Publish every rule, its admitted citations, and explicit static-review limits."""
from collections import Counter
from urllib.parse import quote
import re
import json
from hashlib import sha256

from mn_sdk.agent_events import report_activity
from mn_sdk_common.publication import ArtifactWrite
from mn_sdk.integrations.block_publication_files import publish_artifact_bundle, publish_files

from .artifacts import read, save
from .publication import deliver_reports
from .configuration import BLUEPRINT_ID
from .rule_review import require_approved_rules


def cell(value):
    value = str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', ' ')
    return re.sub(r'([\\`*\[\]|])', r'\\\1', value)


def publish(block, inputs):
    report_activity("Writing the rules report", owner_blueprint=BLUEPRINT_ID,
                    step_id=block.step_id, run_dir=block.store.run_dir)
    capture = block.store.read(inputs["previous"]["capture"])
    verification = block.store.read(inputs["previous"]["verification"])
    rules = read(block, "rules.json")
    if not (capture['snapshot_id'] == rules['snapshot_id'] == verification['snapshot_id']):
        raise ValueError('Report inputs have different source identities.')
    results = {r['rule_id']: r for r in verification['results']}
    if len(results) != len(verification['results']) or set(results) != {r['id'] for r in rules['rules']}:
        raise ValueError('Every rule must have exactly one verification result.')
    approval = require_approved_rules(block, rules)
    if verification.get('rules_review') != approval:
        raise ValueError('Verification does not match the approved rules.')
    counts = dict(Counter(r['status'] for r in results.values()))
    gaps = rules.get('extraction_gaps', [])
    coverage_note = (f'Partial extraction: {len(gaps)} source sections remain unresolved. '
                     'Missing requirements have not been assessed.' if gaps else
                     'Extraction covered the selected document packets.')
    if not rules['rules']:
        coverage_note += ' No software rules were identified. This report establishes no conformance result.'
    lines = ['# Software rules report', '',
             'Static AI review of a captured source folder. Repository code and tests were not executed. '
             'Pass means the inspected implementation supports the rule within this scope; it is not runtime proof. '
             'Confidence is an uncalibrated AI assessment, capped at 0.85 for static judgments. '
             'Unknown requires more evidence or human review.', '',
             f"Capture: `{capture['snapshot_id']}`. Rules: {len(results)}. "
             f"Pass: {counts.get('pass', 0)}. Fail: {counts.get('fail', 0)}. Unknown: {counts.get('unknown', 0)}.", '',
             'The supervisor approved these exact rules before verification started.', '',
             coverage_note, '',
             '| Rule | Pass or not | Evidence with reference | Confidence (0–1) |',
             '| --- | --- | --- | --- |']
    for rule in rules['rules']:
        result = results[rule['id']]
        references = []
        for evidence in result['evidence']:
            path = evidence['path']
            references.append(f"[{cell(path)}:{evidence['start_line']}–{evidence['end_line']}]"
                              f"(source/{quote(path, safe='/')}#L{evidence['start_line']}) "
                              f"SHA-256 `{evidence['sha256']}`: {cell(evidence['quote'])}")
        lines.append(f"| {cell(rule['id'] + ': ' + rule['statement'])} | {result['status'].capitalize()} | "
                     f"{'; '.join(references) or 'No admissible implementation evidence.'} "
                     f"{cell(result['explanation'])} | {result['confidence']:.2f} |")
    lines += ['', '## Rule origins', '']
    for rule in rules['rules']:
        origin = rule['source']
        lines.append(f"- {cell(rule['id'])}: {cell(rule['origin'])}, "
                     f"{cell(origin['path'])}:{origin['start_line']}–{origin['end_line']}.")
    lines += ['', '## Coverage and limitations', '',
              f"Captured {len(capture['sources'])} UTF-8 files. Excluded {len(capture['omitted'])} entries. "
              'Excluded folders represent whole subtrees. See capture.json and static-analysis.json for the complete inventory and parser gaps.',
              'Missing literal hits, documentation claims, test source, and unresolved call edges do not prove compliance or violation. '
              'Generated rules are candidates for supervisor review; complete extraction is not a guarantee that AI found every requirement.']
    selection = rules.get('documentation_selection', {})
    excluded_documents = selection.get('excluded_documents', [])
    if selection:
        lines += ['', f"Rule document scope: {cell(selection['scope'])}. "
                  f"Selected {len(selection['selected_documents'])} documents; "
                  f"excluded {len(excluded_documents)} generated reports from rule extraction."]
        lines += [f"- {cell(item['path'])}: {cell(item['reason'])}." for item in excluded_documents]
    if gaps:
        lines += ['', '## Unresolved extraction coverage', '',
                  'This report covers the approved candidate rules only. Requirements in the following '
                  'source sections remain unresolved; this is not a complete conformance assessment.', '',
                  '| Source section | Status | Reason |', '| --- | --- | --- |']
        lines += [f"| {cell(gap['path'])}:{gap['start_line']}–{gap['end_line']} | Unknown | {cell(gap['reason'])} |"
                  for gap in gaps]
    final = {'schema_version': 'mn.software_rules.report.v1', 'snapshot_id': capture['snapshot_id'],
             'rules': rules['rules'], 'results': verification['results'], 'summary': counts,
             'source_execution': False, 'report': 'report.md', 'rules_markdown': 'rules.md',
             'rules_review': approval,
             'assessment_status': 'needs_review' if not rules['rules'] or gaps or counts.get('unknown') else 'complete',
             'coverage': {'documents': rules['extraction_coverage'], 'omitted': capture['omitted'],
                          'extraction_status': rules.get('extraction_status', 'complete'), 'extraction_gaps': gaps,
                          'documentation_selection': selection}}
    # Captured evidence is committed individually; large repositories do not
    # consume the publication bundle's limit of 128 top-level report artifacts.
    for path, content in capture["sources"].items():
        block.check()
        block.store.commit_bytes("source/" + path, content.encode("utf-8"), kind="captured_source")
    encoded = json.dumps(final, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")
    revision = sha256(encoded).hexdigest()

    def page():
        try:
            from .workspace_web import render
            return render(final, capture).encode("utf-8")
        except Exception as error:
            save(block, "presentation-status.json", {"status": "unavailable", "error_type": type(error).__name__})
            raise

    def handle():
        from mn_sdk_web_ui import static_run_report_handle
        if not block.store.path("web/index.html").is_file():
            raise ValueError("Optional report page is unavailable.")
        return json.dumps(static_run_report_handle(block.store.run_dir, "web/index.html",
            title="Code verification", optional=True)).encode("utf-8")

    receipt = publish_artifact_bundle(block, [
        ArtifactWrite("final_artifact", "final_artifact.json", encoded, kind="json", authoritative=True),
        ArtifactWrite("result", "result.json", encoded, kind="json", authoritative=True),
        ArtifactWrite("report", "report.md", ("\n".join(lines) + "\n").encode("utf-8"), kind="markdown"),
        ArtifactWrite("rules_markdown", "rules.md", block.store.path("rules.md").read_bytes(), kind="markdown", mode=0o644),
        ArtifactWrite("web_report", "web/index.html", page, kind="html", required=False, revision=revision),
        ArtifactWrite("web_ui", "web_ui.json", handle, kind="json", required=False, revision=revision, mode=0o644),
    ], receipt_path=block.root + "/publication.json")
    if receipt["warnings"] and not block.store.path("presentation-status.json").exists():
        save(block, "presentation-status.json", {"status": "unavailable",
            "failed_artifact_ids": [warning["artifact_id"] for warning in receipt["warnings"]]})
    deliver_reports(block, complete=True)
    try:
        deliver_reports(block, presentation=True)
    except Exception as error:
        save(block, "presentation-status.json", {"status": "unavailable", "error_type": type(error).__name__})
        report_activity("The Markdown report is ready. The optional web view could not be delivered.",
                        kind="action", owner_blueprint=BLUEPRINT_ID, run_dir=block.store.run_dir)
    # The native worker exports only declared published files across the worker
    # boundary. Include the page and handle, as well as the authoritative report.
    published_files = publish_files(block, [
        ArtifactWrite(item['id'], item['reference']['path'], block.store.read_bytes(item['reference']),
            kind=item['reference']['kind'], required=item['required'])
        for item in receipt['artifacts']
    ], name='rules_report')
    return {"rules": len(results), "summary": counts, "report": "report.md",
            "artifacts": receipt["artifacts"], "warnings": receipt["warnings"],
            "published_files": published_files}
