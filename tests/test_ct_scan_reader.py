"""Deterministic CT blueprint tests; no GPU, network or patient data."""
import base64
import importlib
import json
import sys
from pathlib import Path

import pytest
from mn_sdk.blueprints import blueprint_definition, compile_blueprint, read_blueprint
from mn_sdk.blueprints.definition import catalog_record
from mn_sdk.model_access.custom import resolve_requirement_entry

ROOT = Path(__file__).resolve().parents[1] / 'ct_scan_reader'


def test_blueprint_compiles_with_strict_nvidia_48_gib_and_special_docker_model():
    package = read_blueprint(ROOT)
    source = blueprint_definition(package)
    compiled = compile_blueprint(package).manifest
    gpu = source['requirements']['gpu']
    assert gpu == {'min_count': 1, 'vendor': 'nvidia', 'driver': 'cuda', 'min_memory_mb': 49152,
                   'memory_operator': '>=', 'enforcement': 'required'}
    model = source['runtime']['models']['ct']
    assert model['customize_mode'] is True
    assert model['model_spec']['requirements']['min_vram_gb'] == 48
    import re
    assert re.fullmatch(r'docker\.io/homerquan/nv-reason-ct@sha256:[a-f0-9]{64}', model['model_spec']['docker']['image'])
    assert model['model_spec']['source'] == 'docker'
    assert compiled['agents']['nodes']
    # Validate with the existing special model resolver, with no SDK catalog entry.
    resolved = resolve_requirement_entry({'model':model['model'], 'manifest_config':model,
        'backend':'nim','customize_mode':True}, catalog={}, catalog_resolver=lambda *args,**kwargs: (_ for _ in ()).throw(KeyError()))
    assert resolved['cataloged'] is False
    assert resolved['customize_mode'] is True


def test_chat_requests_upload_and_safety_copy_is_present_in_product_surfaces():
    package = read_blueprint(ROOT)
    entry = catalog_record(package, 'ct_scan_reader')
    assert 'conversation_file_upload:nifti' in entry['capabilities']
    assert entry['setup_guide']['sample']['available'] is False
    assert 'upload' in entry['setup_guide']['introduction'].lower()
    assert 'not for real diagnosis' in entry['description'].lower()
    file_field = entry['setup_guide']['fields'][0]
    assert file_field['path'] == 'inputs.payload.ct_file'
    assert file_field['path_kind'] == 'file' and file_field['role'] == 'input'
    for name in ['README.md','SPEC.md','TERM.md','knowledge/conversation_guide.md']:
        assert 'not for real diagnosis' in (ROOT/name).read_text().lower()


@pytest.fixture
def reporting(monkeypatch):
    sys.path.insert(0,str(ROOT/'payloads'))
    module = importlib.import_module('domain.reporting')
    monkeypatch.setattr(module,'source_manifest',lambda _: blueprint_definition(read_blueprint(ROOT)))
    return module


def test_report_dispatches_exact_model_and_is_durable_idempotent(reporting,tmp_path):
    scan=tmp_path/'scan.nii.gz';scan.write_bytes(b'synthetic-injected-volume')
    output=tmp_path/'run';output.mkdir()
    context={'run_dir':output,'payload':{'ct_file':str(scan),'region':'chest','prompt':'Research report'}}
    calls=[]
    def request(*args,**kwargs):
        calls.append((args,kwargs))
        assert base64.b64decode(args[3]['volume_base64']) == scan.read_bytes()
        return {'answer':'Synthetic model output for contract testing.','research_only':True,'model_revision':'pinned'}
    payload,refs=reporting.review_ct(context,request=request)
    assert calls[0][0][:3] == ('vlm','nv-reason-ct:0.1.0','/ct')
    assert calls[0][1]['num_retries'] == 0
    assert payload['research_only'] is True and len(refs)==2
    saved=json.loads((output/'final_artifact.json').read_text())
    assert saved['research_only'] and saved['input_sha256']
    assert 'Not for real diagnosis' in (output/'report.md').read_text()
    reporting.review_ct(context,request=request)
    assert len(calls)==1
    (output/'report.md').unlink()
    reporting.review_ct(context,request=request)
    assert (output/'report.md').exists() and len(calls)==1
    context['payload']['region']='abdomen'
    with pytest.raises(ValueError,match='different inputs'):reporting.review_ct(context,request=request)


@pytest.mark.parametrize('result',[{}, {'answer':'','research_only':True}, {'answer':'Invented clinical claim.','research_only':False}])
def test_invalid_model_output_never_publishes_a_report(reporting,tmp_path,result):
    scan=tmp_path/'scan.nii';scan.write_bytes(b'synthetic')
    with pytest.raises(ValueError,match='valid experimental report'):
        reporting.review_ct({'run_dir':tmp_path,'payload':{'ct_file':str(scan),'region':'chest'}},request=lambda *a,**kw:result)
    assert not (tmp_path/'final_artifact.json').exists()


def test_domain_stays_outside_steps_and_runtime():
    for directory in ('steps','runtime'):
        for file in (ROOT/'payloads'/directory).glob('*.py'):
            assert 'from domain' not in file.read_text()
    assert not (ROOT/'payloads/agents/domain.py').exists()

@pytest.fixture
def model_server(monkeypatch):
    import importlib.util
    import struct
    sys.path.insert(0, str(ROOT/'payloads/model'))
    spec=importlib.util.spec_from_file_location('ct_blueprint_model_server',ROOT/'payloads/model/server.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    data=bytearray(368)
    struct.pack_into('<i',data,0,348);struct.pack_into('<4h',data,40,3,2,2,2)
    struct.pack_into('<2h',data,70,4,16);struct.pack_into('<f',data,108,352)
    data[344:348]=b'n+1\0'
    return module,bytes(data)


def test_model_api_decodes_gzip_and_rejects_bombs_and_malformed_headers(model_server,monkeypatch):
    import gzip
    server,data=model_server
    assert server.decode_volume(base64.b64encode(gzip.compress(data)).decode())==data
    for invalid in (b'fake',data[:352],data[:344]+b'ni1\0'+data[348:]):
        with pytest.raises(ValueError):server.decode_volume(base64.b64encode(invalid).decode())
    monkeypatch.setattr(server,'MAX_EXPANDED',512)
    with pytest.raises(ValueError):server.decode_volume(base64.b64encode(gzip.compress(b'0'*513)).decode())


def test_docker_api_accepts_only_volume_bytes_and_bounded_research_inputs(model_server,monkeypatch):
    from fastapi.testclient import TestClient
    server,data=model_server
    calls=[]
    monkeypatch.setattr(server,'infer',lambda volume,region,prompt: calls.append((volume,region,prompt)) or {'answer':'Synthetic output','research_only':True,'model_revision':'pinned'})
    client=TestClient(server.app)
    response=client.post('/v1/ct',json={'volume_base64':base64.b64encode(data).decode(),'region':'chest','prompt':'Research report'})
    assert response.status_code==200 and response.json()['research_only'] is True
    assert calls==[(data,'chest','Research report')]
    for body in ({'ct_path':'/etc/passwd','region':'chest','prompt':'Read'}, {'volume_base64':'AAAA','region':'brain','prompt':'Read'}):
        assert client.post('/v1/ct',json=body).status_code==400
    assert client.get('/health').status_code==503
    assert client.get('/v1/models').json()['data'][0]['id']=='nvidia/NV-Reason-CT'
