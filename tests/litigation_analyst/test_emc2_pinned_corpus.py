"""Opt-in ingestion of an already downloaded, pinned public corpus. No inference."""
# ruff: noqa: F811 -- Imported pytest fixtures are requested by name.
import json
import os
from pathlib import Path
import runpy
import subprocess

import pytest
from test_litigation_analyst import BLUEPRINT, modules, make_context  # noqa: F401


@pytest.mark.skipif(not os.getenv('MN_TEST_EMC2_ROOT'), reason='Set MN_TEST_EMC2_ROOT to an existing pinned EMC-2 checkout')
def test_pinned_sample_coverage_and_source_linked_labels(modules, tmp_path, monkeypatch):
    root = Path(os.environ['MN_TEST_EMC2_ROOT'])
    from domain.sample_data import EMC2_REVISION
    assert subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'], text=True).strip()==EMC2_REVISION
    monkeypatch.setattr(modules['intake'], 'prepare_emc2', lambda _:root)
    context = make_context(tmp_path)
    modules['intake'].prepare_sources(context)
    evaluate = runpy.run_path(str(BLUEPRINT / 'evaluate_emc2.py'))['evaluate']
    result = evaluate(context['run_dir'], BLUEPRINT / 'examples/emc2_evaluation/expected.json')
    assert result['sample_binding_matches']
    assert all(c['source_binding_valid'] for c in result['label_checks'])
    assert result['excluded_repository_documentation']==['README.md','LICENSE.md','CITATION.MD']
    assert result['duplicate_group_count'] > 0 and result['archives_not_extracted']
    assert result['acceptance']=='pending_attorney_review'
    assert result['citation_check_status']=='no_report_yet'
    from domain.legal_sources import LegalSourceAdapter
    from domain.intake import PreparedCorpus
    units = 0
    for d in PreparedCorpus(context['run_dir'] / 'case', 'case').scan():
        if d.text:
            sections = LegalSourceAdapter().sections(d.text, d.relative_path)
            units += len(sections)
            for s in sections:
                assert d.text.encode()[s.start_byte:s.end_byte].decode()
    result['validated_source_unit_count'] = units
    (tmp_path / 'emc2-ingestion-check.json').write_text(json.dumps(result,indent=2))
    print('EMC2_COVERAGE',json.dumps({k:result[k] for k in ('document_count','readable_count','duplicate_group_count','validated_source_unit_count')}))
