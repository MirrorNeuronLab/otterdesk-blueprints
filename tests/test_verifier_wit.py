"""Exercise the released verifier command linked with the six packaged WASI 0.3 components."""
from hashlib import sha256
import json

from mn_sdk.blueprint.wasm import invoke_component
import pytest


def test_composed_verifier_skills(verifier_component_environment):
    env = verifier_component_environment("functional_verifier")

    def invoke(operation, payload, **options):
        return invoke_component(operation, payload, environment=env, **options)

    sources = {"src/main.py": "def read():\n    return 3\n"}
    inputs = {path: content.encode() for path, content in sources.items()}
    inputs["credentials.py"] = b"fixture private file"
    result = invoke("capture", {"extensions": [".py"]}, input_files=inputs)
    assert result["files"] == sources
    assert result["omitted"] == ["credentials.py"]
    assert invoke("snapshot", {"sources": sources})["subject"] == result["subject"]
    assert invoke("syntax", {"source": "def broken(:\n    pass"})["diagnostics"][0]["line"] == 1
    assert invoke("json-contract", {"source": '{"version":2}', "keys": {"version": 3}}) == {"passed": False}
    examples = [{"id": "negative", "input": {}, "accept": False}, {"id": "positive", "input": {"x": 1}, "accept": True}]
    observed = invoke("schema-cases", {"source": '{"type":"object","required":["x"]}', "cases": examples})
    assert [r["observed"] for r in observed] == [False, True]
    assert all(r["passed"] for r in observed)
    assert invoke("compare", {"expected": True, "baseline": True, "candidate": False}) == {"status":"unmet", "change":"regression"}
    doc = {"title":"Coverage", "sections":[{"title":"<source>", "blocks":[
        {"type":"findings","items":[{"text":"<unsafe>","source_refs":["check-1"]}]},
        {"type":"attachments","items":[{"label":"View","path":"src/report file.json"}]},
    ]}]}
    rendered=invoke("report", {"document":doc})
    assert "&lt;unsafe&gt;" in rendered["html"] and "<unsafe>" not in rendered["html"]
    assert "src/report%20file.json" in rendered["markdown"] and "Content-Security-Policy" in rendered["html"]


def test_wit_reconciliation_rejects_tampered_or_incomplete_plans(verifier_component_environment):
    env = verifier_component_environment("software_verifier_suite")
    canonical = json.dumps({"run_id":"sample", "subject":"source", "revision":None, "blockers":[],
        "checks":[{"id":"one","kind":"syntax","requirement":"Valid source.","specialist":"functional"}]},
        sort_keys=True,separators=(",",":"))
    signed = {"plan_id":sha256(canonical.encode()).hexdigest(),"canonical":canonical}
    def reconcile(plan):
        return invoke_component("reconcile", {"signed_plan":plan,"records":[]}, environment=env)
    assert reconcile(signed)["verdict"] == "INCONCLUSIVE"
    with pytest.raises(RuntimeError, match="reconcile"):
        reconcile({**signed,"canonical":canonical.replace("one","two")})


def test_core_plans_each_rust_step_and_honors_the_exact_approval(tmp_path):
    from pathlib import Path
    from block_workflow_fixture import run_sample
    from mn_sdk.blueprints import read_blueprint, compile_blueprint

    catalog=Path(__file__).resolve().parents[1]
    pkg='software_verifier_suite'
    source=catalog/pkg/'examples/sample_inputs'
    m=compile_blueprint(read_blueprint(catalog/pkg)).manifest
    nodes=[n for n in m['agents']['nodes'] if n.get('agent_type')=='executor']
    assert len(nodes)==12 and {n['config']['runner_module'] for n in nodes}=={'MirrorNeuron.Runner.Wasmtime'}
    decisions={}
    calls=[]
    def services(op,args):
        calls.append(op)
        if op=='model.generate-json':
            _,packet,schema=args
            packet,schema=json.loads(packet),json.loads(schema)
            if 'rules' in schema['properties']:
                v={'statement':'Require a nonempty name.', 'source_ids':[packet['numbered_lines'][0]['id']],
                    'subject':'name','scope':'product','modality':'must','conditions':[],'requirement_kind':'behavior'}
                return {'complete':True,'rules':[v]}
            return {'decision':{'action':'finish','status':'unknown','evidence_ids':[],'explanation':'Missing runtime observations.'}}
        if op=='approvals.request':
            req=json.loads(args[0])
            record={'metadata':req,'state':'answered','receipt':{'answer':{'option_id':'approve'}}}
            decisions[req['request_id']]=record
            return record
        if op=='approvals.status':
            return decisions[args[0]]
        raise AssertionError(op)
    values={'input_folder':str(source)}
    outcome=run_sample(pkg,inputs=values,config={'inputs':{'payload':values}},runs_root=tmp_path,wit_service=services)
    result=outcome['final_artifact']
    assert result['verdict']=='INCONCLUSIVE' and result['rules_review']['status']=='approved'
    assert len(result['rules'])==len(result['results'])==1 and result['results'][0]['status']=='unknown'
    assert set(result['specialists'])=={'functional','security','reliability','compatibility'}
    assert calls.index('model.generate-json')<calls.index('approvals.request')<calls.index('approvals.status')
    assert (tmp_path/outcome['run_id']/'web/index.html').is_file()
    rounds = sorted((tmp_path/outcome['run_id']/'specialists/rounds').glob('*.json'))
    plans = [json.loads(p.read_text()) for p in rounds]
    assert [p['steps'][0]['input']['role'] for p in plans[:-1]] == ['functional', 'security', 'compatibility', 'reliability']
    assert all(len(p['steps']) == 1 for p in plans[:-1]) and plans[-1]['decision'] == 'stop'


def test_rust_review_rejection_stops_before_verification(tmp_path):
    from pathlib import Path
    from block_workflow_fixture import run_sample
    directory=tmp_path/'source';directory.mkdir();(directory/'SPEC.md').write_text('The name must be required.')
    values={'input_folder':str(directory)}
    calls=[]
    def service(op,args):
        calls.append(op)
        if op=='model.generate-json':
            return {'complete':True,'rules':[{'statement':'Require a name.','source_ids':['L1']}]}
        if op=='approvals.request':
            return {'metadata':json.loads(args[0]),'state':'answered','receipt':{'answer':{'option_id':'reject'}}}
        raise AssertionError(op)
    with pytest.raises(RuntimeError,match='supervisor rejected'):
        run_sample('software_verifier_suite',inputs=values,config={'inputs':{'payload':values}},runs_root=tmp_path,run_id='reject',wit_service=service)
    assert calls==['model.generate-json','approvals.request']
    assert not (tmp_path/'reject'/'verification.json').exists()


@pytest.mark.parametrize("changed_line", [False, True], ids=["bound", "unbound"])
def test_native_worker_binds_recorded_test_inventory_to_captured_lines(tmp_path, changed_line):
    from block_workflow_fixture import run_sample
    from mn_verification_checks_skill.contracts import snapshot_id

    src = tmp_path / "src"
    src.mkdir()
    files = {"SPEC.md": "The name must exist.\n", "names.py": "def read_name():\n    return 'Ada'\n",
             "test_name.py": "def test_name():\n    assert read_name()\n"}
    for path, value in files.items():
        (src / path).write_text(value)
    folder = tmp_path / "evidence"
    folder.mkdir()
    def pin(value):
        raw = json.dumps(value, sort_keys=True).encode()
        ident = sha256(raw).hexdigest()
        (folder / (ident + ".json")).write_bytes(raw)
        return ident
    def digest(raw):
        return sha256(raw.encode()).hexdigest()

    selector = "test_name.py::test_name"
    subject = snapshot_id(files)
    suite = "1" * 64
    inventory = pin({
        "origin": "Reviewed test suite", "subject": subject, "revision": None,
        "suite_sha256": suite, "check_id": "record", "cases": [
            {"id": selector, "path": "test_name.py", "line": 2 if changed_line else 1, "status": "passed",
             "origin": {"path": "SPEC.md", "line": 1, "sha256": digest(files["SPEC.md"]), "basis": "reviewed_link"}}],
    })
    receipt = pin({
        "schema_version": "mn.verification.execution.v1", "subject": subject,
        "revision": None, "base_commit": None, "artifact_sha256": None, "check_id": "record",
        "suite_sha256": suite, "fixture_sha256": "2" * 64, "runner_sha256": "3" * 64,
        "target": "test-host", "cases": {"name": ["passed"]}, "test_id": selector,
        "observations": {"test_counts": {"passed": 1, "failed": 0, "skipped": 0, "inconclusive": 0}},
    })
    check = {
        "id": "record", "kind": "execution_record", "specialist": "functional",
        "target": "test-host", "cases": ["name"], "requirement": "Confirm the captured name.",
        "suite_sha256": suite, "receipt_sha256": receipt, "test_inventory_sha256": inventory,
        "behavior": {
            "specification": {"path": "SPEC.md", "start_line": 1, "end_line": 1, "sha256": digest(files["SPEC.md"])},
            "implementation": [{"path": "names.py", "symbol": "read_name"}],
            "test": {"path": "test_name.py", "symbol": "test_name"}, "test_sha256": digest(files["test_name.py"]),
            "setup": "Read a name.", "impact": "A name is displayed.", "limits": "One fixture.",
        },
    }
    inputs = {"input_folder": str(src), "evidence_folder": str(folder),
              "verification_scope": json.dumps({"checks": [check]})}
    result = run_sample("functional_verifier", inputs=inputs, config={"inputs": {"payload": inputs}}, runs_root=tmp_path)
    row = next(c for c in result["final_artifact"]["checks"] if c["id"] == "record")
    assert row["status"] == ("inconclusive" if changed_line else "passed")
    if not changed_line:
        observed = row["attempts"][0]
        assert observed["behavior"]["selector"] == selector
        assert observed["test_inventory"]["reviewed_links"] == 1


def test_native_worker_checks_derived_boundaries_against_the_supervisors_schema(tmp_path):
    from block_workflow_fixture import run_sample

    source = tmp_path / "subject"
    source.mkdir()
    (source / "names.json").write_text('{"type":"object","required":["name"]}')
    protected = {"type": "object", "required": ["name"], "properties": {"name": {"type": "string", "minLength": 1}}}
    check = {
        "id": "names", "kind": "schema_cases", "requirement": "Require a nonempty name.",
        "file": "names.json", "cases": [{"id": "nonempty", "input": {"name": "Ada"}, "accept": True}],
        "acceptance_schema": protected,
    }
    inputs = {"input_folder": str(source), "verification_scope": json.dumps({"checks": [check]})}
    result = run_sample("functional_verifier", inputs=inputs, config={"inputs": {"payload": inputs}}, runs_root=tmp_path)
    check = next(c for c in result["final_artifact"]["checks"] if c["id"] == "names")
    assert check["status"] == "failed"
    attempt = check["attempts"][0]
    rejected = next(c for c in attempt["generated_cases"] if c["input"] == {"name": ""})
    assert rejected["accept"] is False
    row = next(c for c in attempt["examples"] if c["id"] == rejected["id"])
    assert row["observed"] is True and row["passed"] is False


def test_coordinator_waits_for_published_report_before_dispatching_next_specialist(tmp_path):
    from pathlib import Path
    from block_workflow_fixture import run_sample

    roles = ["functional", "security", "compatibility", "reliability"]
    rows = {}
    events = []
    published = []
    approvals = {}

    def service(who):
        def call(op, args):
            if op == "model.generate-json":
                packet, schema = map(json.loads, args[1:])
                if "rules" in schema["properties"]:
                    return {"complete": True, "rules": [{
                        "statement": "Require a nonempty name.", "source_ids": [packet["numbered_lines"][0]["id"]],
                        "subject": "name", "scope": "product", "modality": "must",
                        "conditions": [], "requirement_kind": "behavior",
                    }]}
                return {"decision": {"action": "finish", "status": "unknown", "evidence_ids": [], "explanation": "Missing runtime observations."}}
            if op == "approvals.request":
                request = json.loads(args[0])
                receipt = {"metadata": request, "state": "answered", "receipt": {"answer": {"option_id": "approve"}}}
                approvals[request["request_id"]] = receipt
                return receipt
            if op == "approvals.status":
                return approvals[args[0]]
            if op == "mailbox.send":
                message = json.loads(args[0])
                recipient = message["recipient_job_id"]
                if message["kind"] == "assignment":
                    assert who == "manager" and published == roles[:roles.index(recipient)]
                    events.append(("assignment", recipient))
                else:
                    assert recipient == "manager" and (tmp_path / who / "web/index.html").is_file()
                    assert (tmp_path / who / "final_artifact.json").is_file()
                    events.append(("published", who))
                    published.append(who)
                ident = f"{who}-{message['request_id']}"
                rows[ident] = {**message, "id": ident, "sender_job_id": who,
                               "sender_blueprint_id": "software_verifier_suite" if who == "manager" else f"{who}_verifier"}
                return {"id": ident}
            if op == "mailbox.list":
                criteria = json.loads(args[0])
                if who == "manager" and criteria.get("reply_to"):
                    child = rows[criteria["reply_to"]]["recipient_job_id"]
                    if child not in published:
                        config = {"inputs": {"payload": {"collaboration_group_id": "group", "collaboration_peers": [
                            {"jobId": "manager", "blueprintId": "software_verifier_suite"}]}}}
                        run_sample(f"{child}_verifier", config=config, runs_root=tmp_path, run_id=child,
                                   wit_service=service(child))
                items = [r for r in rows.values() if r["recipient_job_id"] == who and r["kind"] == criteria["kind"]
                         and (not criteria.get("reply_to") or r.get("reply_to") == criteria["reply_to"])]
                return {"items": items}
            if op == "mailbox.attachment":
                return rows[args[0]]["value"]
            if op == "mailbox.acknowledge":
                return {"id": args[0]}
            raise ValueError(op)
        return call

    sample = Path(__file__).resolve().parents[1] / "software_verifier_suite/examples/sample_inputs"
    values = {"input_folder": str(sample), "collaboration_group_id": "group",
              "collaboration_peers": [{"jobId": role, "blueprintId": f"{role}_verifier"} for role in roles]}
    outcome = run_sample("software_verifier_suite", inputs=values, config={"inputs": {"payload": values}},
                         runs_root=tmp_path, run_id="manager", wit_service=service("manager"))
    assert events == [(event, role) for role in roles for event in ("assignment", "published")]
    assert {v["status"] for v in outcome["final_artifact"]["specialists"].values()} == {"received"}
