from blueprint_modernization_support import run_payload_script


def test_procurement_report_publication_preserves_complete_run_sources(tmp_path):
    result = run_payload_script(
        "purchasing_manager",
        f"""
import hashlib
import json
from pathlib import Path
from domain.conversation_sources import publish_outputs

root = Path({str(tmp_path)!r})
first = '# Procurement report\\n\\n## Review gates\\nNo purchase has been approved.\\n'
second = '# Procurement report\\n\\n## Review gates\\nA written quote remains missing.\\n'
report = root / 'purchasing_manager_report.md'
report.write_text(first)
(root / 'purchasing_manager.json').write_text('{{"private_quote": "not a subject"}}')
(root / 'events.jsonl').write_text('not a subject')
publish_outputs(root, 'first/run')
sources = root / 'context_sources' / 'outputs'
before = {{str(p.relative_to(sources)): hashlib.sha256(p.read_bytes()).hexdigest()
          for p in sources.rglob('*') if p.is_file()}}
publish_outputs(root, 'first/run')
after = {{str(p.relative_to(sources)): hashlib.sha256(p.read_bytes()).hexdigest()
         for p in sources.rglob('*') if p.is_file()}}
report.write_text(second)
publish_outputs(root, 'second-run')
markdown = sorted(p.read_text() for p in sources.rglob('*.md'))
report.unlink()
report.symlink_to(root / 'purchasing_manager.json')
rejected = False
try:
    publish_outputs(root, 'linked-run')
except ValueError:
    rejected = True
print(json.dumps({{'retry_unchanged': before == after,
                  'complete_bodies': markdown == sorted([first, second]),
                  'run_count': len(list(sources.iterdir())),
                  'linked_report_rejected': rejected}}))
""",
    )
    assert result == {
        "retry_unchanged": True,
        "complete_bodies": True,
        "run_count": 2,
        "linked_report_rejected": True,
    }


def test_report_writer_publishes_the_saved_report_after_outputs_are_written(tmp_path):
    result = run_payload_script(
        "purchasing_manager",
        f"""
import hashlib
import json
import os
from pathlib import Path
from domain.reporting import write_user_outputs

os.environ.pop('MN_JOB_OUTPUT_DIR', None)
root = Path({str(tmp_path)!r})
artifact = {{'run_id': 'saved-report', 'recommended_action': 'wait',
            'risk_flags': ['Written supplier quote required.'],
            'evidence_gaps': ['Current stock is unverified.'],
            'review_boundary': {{'review_required': True,
                                'blocked_actions': ['place orders']}}}}
outputs = write_user_outputs(artifact, {{}}, {{'outputs': {{'folder_path': str(root)}}}}, {{}})
report = (root / 'purchasing_manager_report.md').read_text()
sources = list((root / 'context_sources' / 'outputs').rglob('*.md'))
source = sources[0].read_text()
receipt = json.loads(sources[0].with_name(sources[0].name + '.conversion.json').read_text())
print(json.dumps({{'output_count': len(outputs), 'source_count': len(sources),
                  'contains_report': source.split() == report.split(),
                  'complete_receipt': receipt['complete'],
                  'original_hash_verified': receipt['original_sha256'] == hashlib.sha256((root / 'purchasing_manager_report.md').read_bytes()).hexdigest(),
                  'review_gate_retained': 'Do not: place orders' in source,
                  'evidence_gap_retained': 'Current stock is unverified.' in source}}))
""",
    )
    assert result == {
        "output_count": 8,
        "source_count": 1,
        "contains_report": True,
        "complete_receipt": True,
        "original_hash_verified": True,
        "review_gate_retained": True,
        "evidence_gap_retained": True,
    }
