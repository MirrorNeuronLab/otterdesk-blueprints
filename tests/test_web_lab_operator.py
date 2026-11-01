"""Blueprint-only gates; models/UI transport are injected, PLR trackers are real."""

import asyncio
import copy
import importlib
import json
from pathlib import Path

import pytest

from mn_sdk.blueprints import compile_blueprint, read_blueprint

ROOT = Path(__file__).resolve().parents[1] / 'web_lab_operator'


@pytest.fixture
def domain(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'payloads'))
    return lambda name: importlib.import_module('domain.' + name)


@pytest.fixture
def plan():
    return json.loads((ROOT / 'examples/expected_plan.json').read_text())


def decision(step, source='', kind='execute'):
    return {'step_id': step['id'], 'decision': kind, 'source': source,
            'reason': 'Observed the current tracker state before selecting this action.'}


def test_canonical_package_compiles_to_stock_blocks(domain):
    package = read_blueprint(ROOT)
    compiled = compile_blueprint(package).manifest
    assert [step['id'] for step in compiled['workflow']['steps']] == [
        'capture_lab_procedure', 'plan_lab_procedure', 'simulate_lab_procedure', 'publish_lab_review']
    workers = [node for node in compiled['agents']['nodes']
               if node.get('config', {}).get('environment', {}).get('MN_WORKFLOW_STEP_HANDLER')]
    assert len(workers) == 4
    assert all(node['config']['environment']['MN_WORKFLOW_STEP_HANDLER'] == 'mn_sdk.integrations.block_worker'
               for node in workers)
    assert {item['uses'] for item in package.extension('mn.blocks')['steps'].values()} == {
        'mn.blocks.domain_operation@1', 'mn.blocks.structured_assessment@1'}
    assert not (ROOT / 'payloads/runtime').exists()
    assert not (ROOT / 'payloads/agents').exists()
    for item in package.extension('mn.blocks')['steps'].values():
        for reference in item.get('hooks', {}).values():
            module, name = reference.split(':')
            assert callable(getattr(importlib.import_module(module), name))
    assert package.extension('mn.mcp')['tools'] == {}
    assert package.extension('mn.response') == {'enabled': True}


def test_ready_plan_preserves_every_numbered_instruction(domain, plan):
    protocol = domain('protocol')
    markdown = (ROOT / 'examples/procedure.md').read_text()
    assert protocol.validate_plan(plan, markdown) == plan
    plan['steps'].pop()
    with pytest.raises(ValueError, match='Every numbered'):
        protocol.validate_plan(plan, markdown)


@pytest.mark.parametrize('change', [
    lambda p: p['steps'][0].update(kind='execute_python'),
    lambda p: p['steps'][0].update(backend='STARBackend'),
    lambda p: p['steps'][0].update(volume_ul=float('nan')),
    lambda p: p['steps'][0].update(volume_ul=float('inf')),
    lambda p: p['steps'][0].update(source='source/A13'),
    lambda p: p['steps'][0].update(destination='http://robot/A1'),
    lambda p: p['steps'].reverse(),
    lambda p: p['steps'][1].update(cycles=True),
    lambda p: p['steps'][2].update(seconds=31),
    lambda p: p['goals'][0].update(tolerance_ul=360),
    lambda p: p['assumptions'].append('Assume 200 uL in the reserve.'),
    lambda p: p['liquids'].append(copy.deepcopy(p['liquids'][0])),
])
def test_untrusted_plan_cannot_expand_execution(domain, plan, change):
    change(plan)
    with pytest.raises(ValueError):
        domain('protocol').validate_plan(plan)


def test_unsupported_markdown_can_be_reviewed_without_placeholder_steps(domain):
    plan = {'status': 'needs_review', 'summary': 'A heater is outside this simulator.',
            'assumptions': [], 'unresolved': ['Heating is unsupported.'],
            'plates': [], 'liquids': [], 'steps': [], 'goals': []}
    assert domain('protocol').validate_plan(plan, '1. Heat the sample.') == plan


def test_source_shortage_adapts_within_declared_same_liquid_sources(domain, plan):
    protocol = domain('protocol')
    state = protocol.initial_state(plan)
    step = plan['steps'][0]
    assert protocol.candidates(step, state) == ['source/A2']
    selected = protocol.action_for(step, state, decision(step, 'source/A2', 'adapt'))
    assert selected['source'] == 'source/A2'
    assert selected['volume_ul'] == step['volume_ul']
    assert selected['destination'] == step['destination']
    state['wells']['source/A2']['liquids'] = ['other reagent']
    assert protocol.candidates(step, state) == []
    with pytest.raises(ValueError, match='another liquid'):
        protocol.action_for(step, state, decision(step, 'source/A2', 'adapt'))


@pytest.mark.parametrize('violation', ['overflow', 'tips', 'undeclared', 'unnecessary_adaptation', 'changed_amount'])
def test_action_policy_rejects_unsafe_adjustments(domain, plan, violation):
    protocol = domain('protocol')
    state, step = protocol.initial_state(plan), plan['steps'][0]
    selected = decision(step, 'source/A2', 'adapt')
    if violation == 'overflow':
        state['wells']['destination/A1']['volume_ul'] = 300
    elif violation == 'tips':
        state['tips_remaining'] = 0
    elif violation == 'undeclared':
        selected['source'] = 'source/A3'
    elif violation == 'unnecessary_adaptation':
        state['wells']['source/A1']['volume_ul'] = 200
    else:
        selected['volume_ul'] = 20
    with pytest.raises(ValueError):
        protocol.action_for(step, state, selected)


def test_real_chatterbox_tracks_transfer_mix_and_tip_consumption(domain, plan):
    lab_module = domain('lab')
    protocol = domain('protocol')

    async def exercise():
        lab = lab_module.SimulatedLab(plan)
        assert type(lab.lh.backend).__name__ == 'LiquidHandlerChatterboxBackend'
        await lab.setup()
        try:
            for step in plan['steps']:
                choose = decision(step, 'source/A2', 'adapt') if step['kind'] == 'transfer' else decision(step)
                action = protocol.action_for(step, lab.observe(), choose)
                assert (await lab.perform(action, lambda: None, lambda: asyncio.sleep(0)))['passed']
            state = lab.observe()
            assert state['tips_remaining'] == 94
            assert all(goal['met'] for goal in protocol.goal_results(plan, state))
        finally:
            await lab.stop()
    asyncio.run(exercise())


def test_transfer_above_tip_capacity_splits_without_inventing_volume(domain, plan):
    plan['liquids'][1]['volume_ul'] = 350
    step = plan['steps'][0]
    step['volume_ul'] = 350
    async def exercise():
        lab = domain('lab').SimulatedLab(plan)
        await lab.setup()
        try:
            action = domain('protocol').action_for(step, lab.observe(), decision(step, 'source/A2', 'adapt'))
            await lab.perform(action, lambda: None, lambda: asyncio.sleep(0))
            state = lab.observe()
            assert state['wells']['destination/A1']['volume_ul'] == 350
            assert state['wells']['source/A2']['volume_ul'] == 0
            assert state['tips_remaining'] == 94
        finally:
            await lab.stop()
    asyncio.run(exercise())


@pytest.fixture
def simulated_io(domain, monkeypatch, tmp_path, plan):
    module = domain('simulation')
    visualizer = domain('visualizer')
    calls = {'model': 0, 'closed': 0, 'claimed': 0}
    job = tmp_path / 'jobs/job-a'
    job.mkdir(parents=True)
    monkeypatch.setenv('MN_JOB_ID', 'job-a')
    monkeypatch.setenv('MN_JOB_DATA_DIR', str(job))

    class Monitor:
        def __init__(self, resource, projection):
            self.projection = projection
        async def start(self, host, port):
            return 18000
        async def close(self):
            calls['closed'] += 1

    def claim(directory, **options):
        calls['claimed'] += 1
        (directory / 'web_ui.json').write_text(json.dumps({'metadata': {'readiness': {'ready': True}}}))

    def model(*args, **kwargs):
        calls['model'] += 1
        prompt = json.loads(args[3]['messages'][1]['content'])
        step = prompt['step']
        value = (decision(step, prompt['allowed_sources'][0],
                          'execute' if prompt['allowed_sources'][0] == step['source'] else 'adapt')
                 if step['kind'] == 'transfer' and prompt['allowed_sources'] else decision(step))
        return {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(value)}}]}

    monkeypatch.setattr(visualizer, 'LabVisualizer', Monitor)
    monkeypatch.setattr(module, 'claim_web_ui', claim)
    monkeypatch.setattr(module, 'mark_web_ui_status', lambda *a, **k: calls.update(final_status=k['status']))
    monkeypatch.setattr('mn_sdk.integrations.block_model_request.runtime_model_json_request', model)
    monkeypatch.setattr('mn_sdk.integrations.block_assessment.assessor',
                        lambda *a, **k: lambda request: copy.deepcopy(plan))
    return calls


def test_compiled_handlers_execute_publish_and_replay_without_more_model_calls(domain, simulated_io, tmp_path):
    from block_workflow_fixture import run_sample
    options = {'inputs': {'procedure_markdown': (ROOT / 'examples/procedure.md').read_text(), 'procedure_file': ''},
               'config': {'inputs': {'payload': {'procedure_file': ''}}, 'simulation': {'action_delay_seconds': 0}},
               'runs_root': tmp_path / 'runs', 'run_id': 'lab-run'}
    result = run_sample('web_lab_operator', **options)
    final = result['final_artifact']
    assert final['status'] == 'completed'
    assert final['steps_completed'] == 4 and final['adaptations'] == 1
    assert all(goal['met'] for goal in final['goals'])
    assert simulated_io == {'model': 4, 'closed': 1, 'claimed': 1, 'final_status': 'stopped'}
    root = tmp_path / 'runs/lab-run'
    assert json.loads((root / 'web_ui.json').read_text())['adapter'] == 'static_html'
    assert 'replay-data' in (root / 'web/index.html').read_text()
    assert len(json.loads((root / 'trace.json').read_text())['events']) == 4
    assert run_sample('web_lab_operator', **options)['final_artifact'] == final
    assert simulated_io['model'] == 4 and simulated_io['closed'] == 1


def test_checkpoint_tampering_fails_cached_simulation(domain, simulated_io, tmp_path):
    from block_workflow_fixture import run_sample
    options = {'inputs': {'procedure_markdown': (ROOT / 'examples/procedure.md').read_text(), 'procedure_file': ''},
               'config': {'inputs': {'payload': {'procedure_file': ''}}, 'simulation': {'action_delay_seconds': 0}},
               'runs_root': tmp_path / 'runs', 'run_id': 'lab-tamper'}
    run_sample('web_lab_operator', **options)
    path = tmp_path / 'runs/lab-tamper/trace.json'
    path.write_text('{}')
    with pytest.raises(Exception, match='integrity|size|digest|changed|mismatch'):
        run_sample('web_lab_operator', **options)
    assert simulated_io['model'] == 4


def test_default_markdown_file_is_staged_and_captured_by_sdk(domain, tmp_path):
    from block_workflow_fixture import run_sample
    result = run_sample('web_lab_operator', runs_root=tmp_path / 'runs', run_id='lab-file',
                        through_step='capture_lab_procedure')
    assert result['markdown'] == (ROOT / 'examples/procedure.md').read_text()
    assert (tmp_path / 'runs/lab-file/procedure.md').read_text() == result['markdown']


@pytest.mark.parametrize('condition', ['unsupported', 'failed_check', 'failed_goal', 'invalid_decision'])
def test_review_outcomes_cannot_be_reported_as_success(domain, simulated_io, tmp_path, plan, monkeypatch, condition):
    from block_workflow_fixture import run_sample
    if condition == 'unsupported':
        plan.update(status='needs_review', unresolved=['A requested heater is unsupported.'],
                    plates=[], liquids=[], steps=[], goals=[])
    elif condition == 'failed_check':
        plan['steps'][-1].update(minimum_ul=110, maximum_ul=120)
    elif condition == 'failed_goal':
        plan['goals'][0]['volume_ul'] = 99
    else:
        monkeypatch.setattr(domain('simulation'), 'choose', lambda *a: {'execute_python': 'print("unsafe")'})
    result = run_sample('web_lab_operator',
        inputs={'procedure_markdown': (ROOT / 'examples/procedure.md').read_text(), 'procedure_file': ''},
        config={'inputs': {'payload': {'procedure_file': ''}}, 'simulation': {'action_delay_seconds': 0}},
        runs_root=tmp_path / 'runs', run_id='lab-review')
    final = result['final_artifact']
    assert final['status'] == 'needs_review'
    assert final['simulation_only'] is True
    if condition == 'unsupported':
        assert final['steps_completed'] == 0 and simulated_io['claimed'] == 0
    elif condition == 'failed_check':
        assert final['steps_completed'] == 3 and 'volume check' in final['reason']
    elif condition == 'failed_goal':
        assert final['steps_completed'] == 4 and not final['goals'][0]['met']
    else:
        assert final['steps_completed'] == 0
        state = json.loads((tmp_path / 'runs/lab-review/simulation.json').read_text())['state']
        assert state['wells']['destination/A1']['volume_ul'] == 0


def test_cancellation_cleans_up_and_resume_reconstructs_confirmed_actions(domain, simulated_io, tmp_path, monkeypatch):
    from block_workflow_fixture import run_sample
    from mn_blueprint_blocks.contracts import BlockError
    module = domain('simulation')
    original, interrupt = module.choose, [True]
    def choose(block, step, observed, previous):
        if step['kind'] == 'mix' and interrupt[0]:
            raise BlockError('cancelled', 'Synthetic pause between confirmed steps')
        return original(block, step, observed, previous)
    monkeypatch.setattr(module, 'choose', choose)
    options = {'inputs': {'procedure_markdown': (ROOT / 'examples/procedure.md').read_text(), 'procedure_file': ''},
               'config': {'inputs': {'payload': {'procedure_file': ''}}, 'simulation': {'action_delay_seconds': 0}},
               'runs_root': tmp_path / 'runs', 'run_id': 'lab-resume'}
    with pytest.raises(BlockError, match='Synthetic pause'):
        run_sample('web_lab_operator', **options)
    assert simulated_io['model'] == 1 and simulated_io['closed'] == 1
    assert simulated_io['final_status'] == 'cancelled'
    interrupt[0] = False
    final = run_sample('web_lab_operator', **options)['final_artifact']
    assert final['status'] == 'completed' and final['steps_completed'] == 4
    assert simulated_io['model'] == 4 and simulated_io['closed'] == 2
    assert final['goals'][0]['observed_ul'] == 100


def test_optional_replay_failure_preserves_required_report(domain, simulated_io, tmp_path, monkeypatch):
    from block_workflow_fixture import run_sample
    def unavailable(*args):
        raise OSError('synthetic presentation failure')
    monkeypatch.setattr(domain('presentation'), 'render', unavailable)
    result = run_sample('web_lab_operator',
        inputs={'procedure_markdown': (ROOT / 'examples/procedure.md').read_text(), 'procedure_file': ''},
        config={'inputs': {'payload': {'procedure_file': ''}}, 'simulation': {'action_delay_seconds': 0}},
        runs_root=tmp_path / 'runs', run_id='lab-no-page')
    assert result['final_artifact']['status'] == 'completed'
    assert (tmp_path / 'runs/lab-no-page/report.md').is_file()
    assert not (tmp_path / 'runs/lab-no-page/web/index.html').exists()


def test_missing_required_live_ui_fails_and_cleans_up(domain, simulated_io, monkeypatch, tmp_path):
    from block_workflow_fixture import run_sample
    def fail(*args, **kwargs):
        raise OSError('synthetic listener failure')
    monkeypatch.setattr(domain('simulation'), 'claim_web_ui', fail)
    with pytest.raises(OSError, match='listener'):
        run_sample('web_lab_operator',
            inputs={'procedure_markdown': (ROOT / 'examples/procedure.md').read_text(), 'procedure_file': ''},
            config={'inputs': {'payload': {'procedure_file': ''}}},
            runs_root=tmp_path / 'runs', run_id='lab-bad-ui')
    assert simulated_io['closed'] == 1
    assert simulated_io['model'] == 0
    assert json.loads((tmp_path / 'runs/lab-bad-ui/interrupted-simulation.json').read_text())['status'] == 'failed'


def test_replay_escapes_untrusted_text_and_needs_no_live_listener(domain, plan):
    state = domain('protocol').initial_state(plan)
    page = domain('presentation').render({
        'summary': '</script><img src=x onerror=alert(1)>', 'status': 'needs_review',
        'goals': [], 'limitations': ['Synthetic qualification.']}, {'initial': state, 'events': []})
    assert '</script><img' not in page
    assert '\\u003c/script\\u003e' in page
    assert '<script src=' not in page
    assert 'innerHTML' not in page


def test_live_visualizer_uses_local_assets_and_same_origin_websocket(domain, tmp_path):
    import pylabrobot.visualizer.visualizer as native
    module = domain('visualizer')
    manifest = json.loads((ROOT / 'payloads/docker_worker/visualizer-assets.json').read_text())
    (tmp_path / 'assets.json').write_text(json.dumps(manifest))
    native_root = Path(native.__file__).parent
    page, mime = module.visualizer_asset('', native_root, tmp_path)
    assert mime.startswith('text/html') and b'https://' not in page
    code, _ = module.visualizer_asset('vis.js', native_root, tmp_path)
    assert module.WS_CONSTRUCTOR.encode() not in code
    assert module.LOCAL_CONSTRUCTOR.encode() in code
    with pytest.raises(FileNotFoundError):
        module.visualizer_asset('../../manifest.json', native_root, tmp_path)


def test_viewer_disconnect_does_not_break_state_notifications(domain, plan):
    from websockets.exceptions import ConnectionClosedOK
    from websockets.frames import Close
    closed = ConnectionClosedOK(Close(1000, ''), Close(1000, ''), True)
    class DisconnectedViewer:
        async def send(self, value):
            raise closed
    async def exercise():
        lab = domain('lab').SimulatedLab(plan)
        viewer = domain('visualizer').LabVisualizer(lab.lh, lambda: {})
        viewer._websocket = DisconnectedViewer()
        assert await viewer.send_command('state_updated', {}, wait_for_response=False) is None
        assert not viewer.has_connection()
        viewer._websocket = DisconnectedViewer()
        with pytest.raises(ConnectionClosedOK):
            await viewer.send_command('state_updated', {}, wait_for_response=True)
    asyncio.run(exercise())
