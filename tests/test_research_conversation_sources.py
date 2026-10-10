from blueprint_modernization_support import run_payload_script


def test_research_brief_publication_is_complete_idempotent_and_run_scoped(tmp_path):
    result = run_payload_script(
        "research_assistant",
        f"""
import hashlib
import json
from pathlib import Path
from domain.conversation_sources import publish_outputs

root = Path({str(tmp_path)!r})
first = '# Research brief\\n\\n## Evidence gaps\\nNo matched trial has been run.\\n'
second = '# Research brief\\n\\n## Evidence gaps\\nIndependent replication remains missing.\\n'
report = root / 'research_brief.md'
report.write_text(first)
(root / 'research_packet.json').write_text('{{"private_ledger": "not a subject"}}')
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
report.symlink_to(root / 'research_packet.json')
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
