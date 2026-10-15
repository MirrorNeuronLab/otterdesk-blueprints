"""Local protocol harness shared by each blueprint's MCP unit tests."""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from types import SimpleNamespace

from jsonschema import Draft202012Validator
from mn_sdk.blueprints import blueprint_definition, read_blueprint
from mn_sdk_common.mcp import COMMON_TOOLS, RESULT_JSON_SCHEMA, SUPERVISION_PROFILE
from mn_sdk_mcp import JobSupervisor, OperationStore, create_supervision_server

ROOT = Path(__file__).resolve().parents[1]


class BlueprintMcpHarness:
    def __init__(self, blueprint, tmp_path):
        self.package = read_blueprint(ROOT / blueprint)
        self.definition = blueprint_definition(self.package)
        self.declaration = self.definition['mcp']
        self.blueprint_id = self.package.manifest['id']
        self.job_id = 'test-' + self.blueprint_id
        self.job = {'job_id': self.job_id, 'blueprint_id': self.blueprint_id, 'status': 'active'}
        self.runs, self.calls = {}, []
        self.operations = OperationStore(tmp_path / 'mcp.sqlite3')
        self.runtime = SimpleNamespace(get_job=lambda job_id: self.job, get_run=lambda run_id: self.runs[run_id],
                                       pause_run=lambda run_id: self.transition(run_id, 'paused'),
                                       resume_run=lambda run_id: self.transition(run_id, 'running'),
                                       cancel_run=lambda run_id: self.transition(run_id, 'cancelled'))
        self.context = SimpleNamespace(get_profile=lambda job_id: {'mission': self.package.manifest['description']},
                                       get_context=lambda job_id, **kw: {'identity': {'job_id': job_id}, 'evidence': []},
                                       get_run_results=lambda job_id, run_id: {'run_id': run_id, 'results': []})
        self.domain = SimpleNamespace(resolve=lambda run_id, service: {'run_id': run_id}, call=self.domain_call)
        self.supervisor = JobSupervisor(job_id=self.job_id, blueprint_id=self.blueprint_id,
            declaration=self.declaration, runtime=self.runtime, context=self.context, operations=self.operations,
            launch=self.start, poll_launch=lambda operation_id: {}, domain=self.domain)
        self.server = create_supervision_server(self.blueprint_id, self.supervisor)

    def start(self, request_id, metadata):
        self.calls.append(('start_run', request_id))
        self.job['latest_run_id'] = 'execution'
        self.runs['execution'] = {'run_id': 'execution', 'job_id': self.job_id, 'status': 'running'}
        return self.runs['execution']

    def transition(self, run_id, state):
        self.runs[run_id]['status'] = state
        return dict(self.runs[run_id])

    def domain_call(self, config, tool, arguments):
        self.calls.append((tool, arguments))
        if tool == 'get_operation_status':
            return {'state': 'completed', 'summary': 'Observed completion.'}
        if tool.startswith('get_'):
            return {'connected': True, 'ready': True, 'summary': 'Observed local state.'}
        return {'accepted': True, 'state': 'accepted', 'command_id': arguments.get('command_id'), 'operation_id': 'navigation'}

    def call(self, tool, **arguments):
        result = asyncio.run(self.server.call_tool(tool, arguments))
        receipt = result.structured_content
        Draft202012Validator(RESULT_JSON_SCHEMA).validate(receipt)
        assert receipt['job_id'] == self.job_id
        assert receipt['blueprint_id'] == self.blueprint_id
        return receipt

    def assert_shared_contract(self):
        tools = asyncio.run(self.server.list_tools())
        assert {tool.name for tool in tools} == COMMON_TOOLS | self.declaration['tools'].keys()
        assert all(tool.input_schema and tool.output_schema and tool.description for tool in tools)
        manual = self.call('get_user_manual')['data']
        raw = (self.package.root / 'knowledge/user_manual.md').read_bytes()
        assert manual['manual'] == raw.decode()
        assert manual['sha256'] == hashlib.sha256(raw).hexdigest()
        # Each installed revision exposes the same exact manual through MCP Skills.
        _, skill, resources = self.server.skills.snapshot()
        assert resources[skill['uri']].startswith('---\nname: ' + skill['frontmatter']['name'])
        assert resources[skill['uri'].rsplit('/', 1)[0] + '/references/user_manual.md'] == raw.decode()
        for resource in skill['resources']:
            content = resources[resource['uri']].encode()
            assert resource['size'] == len(content)
            assert resource['digest'] == 'sha256:' + hashlib.sha256(content).hexdigest()
        assert self.call('get_capabilities')['data']['profile'] == SUPERVISION_PROFILE
        assert self.call('get_run_status')['data']['run'] is None
        assert self.call('get_run_results')['data']['results'] == []
        assert self.calls == []
        assert 'get_latest_run' not in {tool.name for tool in tools}

    def assert_lifecycle(self):
        first = self.call('start_run', request_id='start')
        assert first['status'] == 'completed'
        assert self.call('start_run', request_id='start')['operation_id'] == first['operation_id']
        assert len(self.calls) == 1
        for tool, state in [('pause_run', 'paused'), ('resume_run', 'running'), ('stop_run', 'cancelled')]:
            result = self.call(tool, request_id=tool, run_id='execution')
            assert result['status'] == 'completed'
            assert self.runs['execution']['status'] == state
        self.runs['other'] = {'job_id': 'other', 'run_id': 'other', 'status': 'running'}
        assert self.call('pause_run', request_id='wrong-job', run_id='other')['error']['code'] == 'not_found'
        assert self.call('start_run')['error']['code'] == 'invalid_request'
        self.job['status'] = 'archived'
        assert self.call('start_run', request_id='archived')['status'] == 'failed'


def assert_worker_registry(blueprint, tmp_path, monkeypatch):
    """Inspect and call each real worker registry, without starting its service."""
    import importlib.util
    import sys

    payload = ROOT / blueprint / 'payloads'
    monkeypatch.syspath_prepend(str(payload))
    if blueprint == 'microduck_controller':
        source = payload / 'services/duck_control_service.py'
    elif blueprint == 'cctv_operator':
        source = payload / 'services/cctv_web_ui.py'
    else:
        source = payload / 'docker_compose/turtlebot-maze/mcp/robot_control_server.py'
    name = 'mcp_contract_' + blueprint
    spec = importlib.util.spec_from_file_location(name, source)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    if blueprint == 'microduck_controller':
        from domain.bridge import BridgeHub
        server = module.create_mcp_server(BridgeHub())
        read_tool = 'get_duck_state'
    elif blueprint == 'cctv_operator':
        service = SimpleNamespace(config={}, attach_activity_store=lambda store: None,
            ui_state=lambda: {'metrics': {'latest finding': 'Observed scene.', 'last analyzed': 'now', 'status': 'running'}})
        server = module.create_operator_mcp_server(service, job_id='job', run_id='run', run_dir=tmp_path)
        read_tool = 'get_operator_status'
    else:
        module._control = SimpleNamespace(status=lambda: {'connected': True, 'navigation_status': 'idle', 'pose': None})
        server = module.mcp
        read_tool = 'get_robot_status'
    declaration = blueprint_definition(read_blueprint(ROOT / blueprint))['response_service']['agent']
    expected = {name: tool for group in declaration['tools'].values() for name, tool in group.items()}
    tools = asyncio.run(server.list_tools())
    assert {tool.name for tool in tools} == expected.keys()
    for tool in tools:
        properties = tool.input_schema['properties']
        assert properties.keys() == expected[tool.name]['arguments'].keys()
        for argument, schema in expected[tool.name]['arguments'].items():
            assert all(properties[argument].get(key) == value for key, value in schema.items())
        assert tool.output_schema
    result = asyncio.run(server.call_tool(read_tool, {}))
    assert result.is_error is not True
    Draft202012Validator(RESULT_JSON_SCHEMA).validate(result.structured_content)
    assert result.structured_content['tool'] == read_tool
