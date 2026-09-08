"""Check frozen evidence before publishing the review and follow-up tasks."""
import hashlib
import json
import re
from pathlib import Path
from mn_sdk.step_runtime import artifact_reference
from .events import audit_scope, emit
from .investigator import validate_assessment
from .prompts import render_prompts
from .rendering import render_markdown


def _slug(value):
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:80] or "architecture-finding"


def _prompt_documents(report, prompt_markdown):
    """Split the canonical prompt pack into the familiar one-task-per-file view."""
    documents = []
    findings = report.get("findings", [])
    for index, finding in enumerate(findings, 1):
        marker = f'<a id="prompt-{_slug(finding["id"])}"></a>'
        start = prompt_markdown.find(marker)
        if start < 0:
            continue
        next_markers = [
            prompt_markdown.find(
                f'<a id="prompt-{_slug(candidate["id"])}"></a>', start + len(marker)
            )
            for candidate in findings[index:]
        ]
        ends = [position for position in next_markers if position >= 0]
        end = min(ends) if ends else len(prompt_markdown)
        module = str(finding.get("hypothesis", {}).get("module") or finding["id"])
        filename = f'{index:02d}-{_slug(finding["id"] + "-" + module)}.md'
        documents.append(
            {
                "finding_id": finding["id"],
                "module": module,
                "verdict": (
                    finding.get("review") or finding.get("assessment") or {}
                ).get("verdict", "unassessed"),
                "path": f"prompts/{filename}",
                "content": prompt_markdown[start:end].rstrip() + "\n",
            }
        )
    return documents


def _prompt_index(documents):
    lines = [
        "# Copy-ready architecture prompts",
        "",
        "Choose one task, verify its cited evidence against the current checkout, and paste it into Codex or another coding agent.",
        "",
    ]
    lines.extend(
        f'- [{item["finding_id"]} · {item["module"]}]({Path(item["path"]).name}) — recorded verdict: {item["verdict"]}'
        for item in documents
    )
    if not documents:
        lines.append("No finding-specific prompt was produced; inspect `../improvement_prompts.md` for investigation triage guidance.")
    return "\n".join(lines) + "\n"


def _write_publication_bundle(directory, outputs, prompt_documents):
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in outputs.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    prompt_dir = directory / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    (prompt_dir / "README.md").write_text(
        _prompt_index(prompt_documents), encoding="utf-8"
    )
    for document in prompt_documents:
        (directory / document["path"]).write_text(
            document["content"], encoding="utf-8"
        )


def verify_evidence(report, run_dir):
    snapshot = json.loads((run_dir / 'snapshot.json').read_text())
    if report['snapshot'] != snapshot['id']:
        raise ValueError('Report snapshot differs from captured input')
    directory = run_dir / 'evidence/snapshots' / snapshot['id']
    sources = json.loads((directory / 'sources.json').read_text())
    if set(sources) != set(snapshot['sources']):
        raise ValueError('Source snapshot inventory mismatch')
    for path, source in sources.items():
        if hashlib.sha256(source['text'].encode()).hexdigest() != snapshot['sources'][path] or source['sha256'] != snapshot['sources'][path]:
            raise ValueError('Source snapshot hash mismatch')
    for evidence in report['evidence'].values():
        if evidence['kind'] == 'observed_history':
            # The collector retains the exact anchored log and hash in its records.
            records = list((directory / 'layers/records').glob('*.json'))
            if not any(hashlib.sha256(json.loads(p.read_text())['details'].get('raw_log', '').encode()).hexdigest() == evidence['sha256'] for p in records):
                raise ValueError('History evidence has no matching anchored log')
            continue
        source = sources.get(evidence['path'])
        if source is None or source['sha256'] != evidence['sha256']:
            raise ValueError('Evidence source hash mismatch')
        text = source['text']
        span = text[evidence['start_offset']:evidence['end_offset']] if 'start_offset' in evidence else ''.join(text.splitlines(keepends=True)[evidence['line_start']-1:evidence['line_end']])
        if span != evidence['text']:
            raise ValueError('Evidence span differs from frozen source')
    if 'decisions' in report:
        from .evidence_validation import verify_packets
        verify_packets(report)
    for finding in report['findings']:
        if finding['status'] == 'assessed':
            validate_assessment(finding['assessment'], finding['packet'])
    for decision in report.get('decisions', []):
        validate_assessment(decision, decision['packet'])
    if report.get('decision'):
        validate_assessment(report['decision'], report['decision']['packet'])


def publish_review(context, *, llm_client=None):
    run_dir = Path(context['run_dir'])
    report = json.loads((run_dir / 'investigation.json').read_text())
    if report['status'] not in {'review_draft', 'partial'}:
        raise ValueError('Cannot publish an unsuccessful investigation as a review')
    verify_evidence(report, run_dir)
    report_markdown = render_markdown(report)
    prompt_markdown = render_prompts(report)
    report_json = json.dumps(report, indent=2)
    prompt_documents = _prompt_documents(report, prompt_markdown)
    prompt_index = [
        {key: item[key] for key in ("finding_id", "module", "verdict", "path")}
        for item in prompt_documents
    ]
    outputs = {
        'report.md': report_markdown,
        'suggestive_prompts.md': prompt_markdown,
        'knowledge.json': json.dumps(report['knowledge'], indent=2),
        'report.json': report_json,
        # Familiar presentation names retained from the previous advisor output.
        'architecture_report.md': report_markdown,
        'architecture_assessment.json': report_json,
        'improvement_prompts.md': prompt_markdown,
        'improvement_prompts.json': json.dumps(prompt_index, indent=2),
    }
    with audit_scope(run_dir):
        _write_publication_bundle(run_dir, outputs, prompt_documents)
        for name in outputs:
            emit('artifact.write.completed', path=name, bytes=(run_dir/name).stat().st_size)
        for document in prompt_documents:
            emit('artifact.write.completed', path=document['path'], bytes=(run_dir/document['path']).stat().st_size)
        index = {'status': report['status'], 'snapshot': report['snapshot'],
                 'report': 'report.md', 'prompts': 'suggestive_prompts.md',
                 'data': 'report.json', 'evidence': 'evidence/', 'events': 'events.log',
                 'presentation': {'report': 'architecture_report.md',
                                  'prompts': 'improvement_prompts.md',
                                  'prompt_index': 'prompts/README.md'}}
        (run_dir / 'review_index.json').write_text(json.dumps(index, indent=2), encoding='utf-8')
        output_folder = context.get('output_folder')
        if output_folder and Path(output_folder).resolve() != run_dir.resolve():
            output_folder = Path(output_folder)
            _write_publication_bundle(output_folder, outputs, prompt_documents)
            (output_folder / 'review_index.json').write_text(
                json.dumps(index, indent=2), encoding='utf-8'
            )
    refs = [artifact_reference(name, path) for name, path in [('report','report.md'),
            ('suggestive_prompts','suggestive_prompts.md'), ('knowledge','knowledge.json'),
            ('report_data','report.json'), ('review_index','review_index.json')]]
    return {'status': report['status'], 'report': refs[0], 'review_index': refs[-1]}, refs
