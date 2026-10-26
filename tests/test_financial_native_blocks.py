"""Native financial handoffs, evidence integrity and review-only publication."""
import importlib
import shutil
from pathlib import Path

import pytest
from mn_blueprint_blocks.context import BlockContext
from mn_blueprint_blocks.contracts import BlockError
from mn_sdk.blueprints import read_blueprint, resolve_config
from mn_sdk.blueprint_support import DeterministicFallbackLLM
from mn_sdk_common.committed_artifacts import CommittedJsonStore, CommittedArtifactIntegrityError

ROOT = Path(__file__).resolve().parents[1] / 'financial_advisor'


@pytest.fixture
def finance(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'payloads'))
    monkeypatch.setenv('MN_JOB_OUTPUT_DIR', str(tmp_path / 'output'))
    folder = tmp_path / 'documents'
    shutil.copytree(ROOT / 'examples/sample_inputs', folder)
    config = resolve_config(read_blueprint(ROOT), {'execution': {'quick_test': True},
        'document_sources': {'folder_path': str(folder)}}).data
    model = DeterministicFallbackLLM('synthetic-finance')
    block = BlockContext(store=CommittedJsonStore(tmp_path / 'run'), invocation_id='financial-native',
        revision='v4-test', run_id='run-1', job_id='job-1', config=config, resources={'llm': model})
    modules = {name: importlib.import_module('domain.' + name) for name in
        ['intake', 'cash_flow', 'tax', 'portfolio', 'research', 'advice', 'reporting']}
    inventory = modules['intake'].step_financial_folder_watcher(block, {'request': {'document_folder': str(folder)}})
    return block, modules, inventory, folder, model


def audited(finance):
    block, modules, result, _, _ = finance
    for module, role, port in [
        ('intake', 'financial_document_reader', 'result'),
        ('intake', 'bank_statement_extractor', 'previous'),
        ('cash_flow', 'cash_flow_normalizer', 'result'),
        ('cash_flow', 'cash_flow_llm_analyst', 'result'),
        ('tax', 'tax_document_router', 'previous'),
        ('tax', 'tax_form_ocr_capturer', 'result'),
        ('tax', 'tax_workpaper_preparer', 'result'),
        ('tax', 'tax_llm_reviewer', 'result'),
        ('portfolio', 'portfolio_context_loader', 'previous'),
        ('portfolio', 'portfolio_market_data_loader', 'result'),
        ('portfolio', 'portfolio_risk_engine', 'result'),
        ('portfolio', 'portfolio_llm_reviewer', 'result'),
        ('research', 'public_finance_researcher', 'previous'),
        ('advice', 'advisor_evidence_reconciler', 'previous'),
        ('advice', 'advisor_review_auditor', 'result')]:
        result = getattr(modules[module], 'step_' + role)(block, {port: result})
    return result


def test_financial_reader_uses_captured_sources_after_input_changes(finance):
    block, modules, inventory, folder, _ = finance
    original = {path.name: path.read_bytes() for path in folder.rglob('*.txt')}
    for path in folder.rglob('*.txt'):
        path.write_text('Source changed after financial intake.')
    result = modules['intake'].step_financial_document_reader(block, {'result': inventory})
    documents = block.store.read(result['state'])['workflow']['financial_document_reader']['documents']
    assert any(document['kind'] == 'bank_statement' for document in documents)
    assert all(document['text'] != 'Source changed after financial intake.' for document in documents)
    assert original


def test_tampered_financial_source_fails_before_ocr(finance, monkeypatch):
    block, modules, inventory, _, _ = finance
    state = block.store.read(inventory['state'])
    reference = state['workflow']['financial_folder_watcher']['files'][0]['artifact']
    block.store.path(reference['path']).write_bytes(b'changed')
    monkeypatch.setattr(modules['intake'], 'build_ocr_runtime', lambda *a: pytest.fail('Changed evidence reached OCR'))
    with pytest.raises(CommittedArtifactIntegrityError):
        modules['intake'].step_financial_document_reader(block, {'result': inventory})


def test_financial_report_replays_without_model_work_and_preserves_math(finance, monkeypatch):
    block, modules, _, _, model = finance
    review = audited(finance)
    first = modules['reporting'].step_financial_advice_reporter(block, {'previous': review})
    assert model.calls == 7
    monkeypatch.setattr(model, 'generate_json', lambda **kw: pytest.fail('Publication repeated completed model work'))
    assert modules['reporting'].step_financial_advice_reporter(block, {'previous': review}) == first
    final = block.store.read_path('final_artifact.json')
    assert final['household_finance_summary']['preliminary_net_cash_flow'] == 2394.8599999999997
    assert final['tax_review_packet']['workpapers']['draft_income_total'] == 88528.44
    assert final['portfolio_risk_review']['total_value'] == 186000
    assert final['review_only'] is True and 'make_trade' in final['blocked_actions']
    assert final['llm_usage']['calls'] == 7 and len(final['model_profiles_used']) == 17
    assert not block.store.path('run.json').exists()


def test_failed_financial_publication_reuses_review(finance, monkeypatch):
    block, modules, _, _, model = finance
    review = audited(finance)
    commit = block.store.commit_bytes
    def interrupted(path, content, **options):
        if str(path) == 'financial_advisor_report.md':
            raise OSError('report publication interrupted')
        return commit(path, content, **options)
    with monkeypatch.context() as patch:
        patch.setattr(block.store, 'commit_bytes', interrupted)
        with pytest.raises(OSError):
            modules['reporting'].step_financial_advice_reporter(block, {'previous': review})
    assert block.store.path('final_artifact.json').is_file()
    assert not block.store.path('financial_advisor_report.md').exists()
    assert model.calls == 7
    modules['reporting'].step_financial_advice_reporter(block, {'previous': review})
    assert model.calls == 7


def test_financial_publication_requires_completed_audit(finance):
    block, modules, inventory, _, model = finance
    with pytest.raises(ValueError, match='completed review audit'):
        modules['reporting'].step_financial_advice_reporter(block, {'previous': inventory})
    assert model.calls == 0 and not block.store.path('final_artifact.json').exists()


def test_financial_cached_review_rejects_tampering(finance):
    block, modules, _, _, model = finance
    review = audited(finance)
    modules['reporting'].step_financial_advice_reporter(block, {'previous': review})
    block.store.path('financial/reviews/financial_advice_reporter.json').write_text('{}')
    with pytest.raises(CommittedArtifactIntegrityError):
        modules['reporting'].step_financial_advice_reporter(block, {'previous': review})
    assert model.calls == 7


def test_financial_state_rejects_changed_configuration_before_model(finance):
    block, modules, inventory, _, model = finance
    block.config['execution']['quick_test'] = False
    with pytest.raises(ValueError, match='different configuration'):
        modules['intake'].step_financial_document_reader(block, {'result': inventory})
    assert model.calls == 0


def test_financial_review_honors_cancellation_after_model_returns(finance):
    block, modules, inventory, _, _ = finance
    docs = modules['intake'].step_financial_document_reader(block, {'result': inventory})
    bank = modules['intake'].step_bank_statement_extractor(block, {'previous': docs})
    cash = modules['cash_flow'].step_cash_flow_normalizer(block, {'result': bank})
    class Cancelling(DeterministicFallbackLLM):
        def generate_json(self, *, system_prompt, user_prompt, fallback):
            result = super().generate_json(system_prompt=system_prompt, user_prompt=user_prompt, fallback=fallback)
            block.cancelled = lambda: True
            return result
    model = Cancelling('synthetic-cancel')
    block.resources['llm'] = model
    with pytest.raises(BlockError) as raised:
        modules['cash_flow'].step_cash_flow_llm_analyst(block, {'result': cash})
    assert raised.value.code == 'cancelled' and model.calls == 1
    assert not block.store.path('financial/cash_flow_llm_analyst.json').exists()


def test_interrupted_financial_review_does_not_repeat_unknown_model_work(finance):
    block, modules, inventory, _, _ = finance
    docs = modules['intake'].step_financial_document_reader(block, {'result': inventory})
    bank = modules['intake'].step_bank_statement_extractor(block, {'previous': docs})
    cash = modules['cash_flow'].step_cash_flow_normalizer(block, {'result': bank})
    class Interrupted(DeterministicFallbackLLM):
        def generate_json(self, **kwargs):
            self.calls += 1
            raise KeyboardInterrupt('worker interrupted during model request')
    model = Interrupted('synthetic-interruption')
    block.resources['llm'] = model
    with pytest.raises(KeyboardInterrupt):
        modules['cash_flow'].step_cash_flow_llm_analyst(block, {'result': cash})
    with pytest.raises(BlockError) as raised:
        modules['cash_flow'].step_cash_flow_llm_analyst(block, {'result': cash})
    assert raised.value.code == 'outcome_unknown' and model.calls == 1
    assert not block.store.path('financial/cash_flow_llm_analyst.json').exists()


def cash_flow_ready(finance):
    block, modules, inventory, _, _ = finance
    docs = modules['intake'].step_financial_document_reader(block, {'result': inventory})
    bank = modules['intake'].step_bank_statement_extractor(block, {'previous': docs})
    return modules['cash_flow'].step_cash_flow_normalizer(block, {'result': bank})


def restarted(block, model):
    from dataclasses import replace
    return replace(block, store=CommittedJsonStore(block.store.run_dir),
        cancelled=lambda: False, resources={'llm': model})


@pytest.mark.parametrize('interruption', ['cancelled', 'review_write', 'receipt_write'])
def test_observed_financial_review_recovers_with_usage_after_restart(finance, monkeypatch, interruption):
    block, modules, _, _, _ = finance
    cash = cash_flow_ready(finance)

    class Observed(DeterministicFallbackLLM):
        def generate_json(self, *, system_prompt, user_prompt, fallback):
            response = super().generate_json(system_prompt=system_prompt,
                user_prompt=user_prompt, fallback=fallback)
            self.input_tokens, self.output_tokens, self.total_tokens = 120, 30, 150
            if interruption == 'cancelled':
                block.cancelled = lambda: True
            return response

    model = Observed('synthetic-observed')
    block.resources['llm'] = model
    commit = block.store.commit
    target = ('financial/reviews/cash_flow_llm_analyst.json' if interruption == 'review_write'
        else 'financial/reviews/cash_flow_llm_analyst-receipt.json')

    def interrupt_write(path, *args, **kwargs):
        if str(path) == target:
            raise OSError('synthetic review publication interruption')
        return commit(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        if interruption != 'cancelled':
            patch.setattr(block.store, 'commit', interrupt_write)
        with pytest.raises(BlockError if interruption == 'cancelled' else OSError):
            modules['cash_flow'].step_cash_flow_llm_analyst(block, {'result': cash})
    assert model.calls == 1

    replacement = DeterministicFallbackLLM('synthetic-replacement')
    fresh = restarted(block, replacement)
    result = modules['cash_flow'].step_cash_flow_llm_analyst(fresh, {'result': cash})
    usage = fresh.store.read(result['state'])['llm_usage']
    assert usage['calls'] == 1 and usage['total_tokens'] == 150
    assert replacement.calls == 0
    assert not list(block.store.run_dir.glob('financial/reviews/*-started.json'))


@pytest.mark.parametrize('failure_phase', ['initialization', 'request'])
def test_rejected_live_financial_model_replays_original_error(finance, monkeypatch, failure_phase):
    block, modules, _, _, _ = finance
    cash = cash_flow_ready(finance)
    services = importlib.import_module('domain.review_services')
    monkeypatch.setattr(services, 'live_llm_requested', lambda *_: True)

    class Rejected(DeterministicFallbackLLM):
        def generate_json(self, **kwargs):
            self.calls += 1
            raise RuntimeError('Runtime model preparation failed: HTTP Error 404: Not Found')

    model = Rejected('synthetic-rejected')
    block.resources['llm'] = model
    initializations = []
    if failure_phase == 'initialization':
        def initialize(*args):
            initializations.append(True)
            raise RuntimeError('Runtime model preparation failed: HTTP Error 404: Not Found')
        monkeypatch.setattr(services, 'build_llm_client', initialize)
    for context in (block, restarted(block, model)):
        with pytest.raises(RuntimeError, match='HTTP Error 404: Not Found') as error:
            modules['cash_flow'].step_cash_flow_llm_analyst(context, {'result': cash})
        assert not isinstance(error.value, BlockError)
    assert len(initializations) == (1 if failure_phase == 'initialization' else 0)
    assert model.calls == (0 if failure_phase == 'initialization' else 1)
    assert not block.store.path('financial/cash_flow_llm_analyst.json').exists()


def test_live_financial_review_rejects_fallback_on_replay(finance, monkeypatch):
    block, modules, _, _, model = finance
    cash = cash_flow_ready(finance)
    services = importlib.import_module('domain.review_services')
    monkeypatch.setattr(services, 'live_llm_requested', lambda *_: True)
    for context in (block, restarted(block, model)):
        with pytest.raises(RuntimeError, match='Required live LLM call'):
            modules['cash_flow'].step_cash_flow_llm_analyst(context, {'result': cash})
    assert model.calls == 1
    assert not block.store.path('financial/cash_flow_llm_analyst.json').exists()
