"""Bounded evidence collection and separate hypothesis/review specialists."""

from mn_sdk.agent_events import activity_operation
from dataclasses import asdict
from copy import deepcopy
import json
from itertools import zip_longest
from mn_sdk.blueprint_support import source_manifest
from mn_graph_analysis_skill import ensure_bounded_readonly_rgql
from .round_state import task_input, read, save, checkpoint
from .round_model import complete, evidence_room
from .handling import cleared_observation
from .graph_queries import QUERIES
from .indexing import validate_indexes
from .evidence.store import EvidenceStore
from .app.skill_bindings import bind_skills, DOC, GRAPH
from .app.activity import observe_action
from .app.planning import object_schema, HYPOTHESIS, validate
from .app.findings import REPORT, REVIEW, submit_report, review_report
from .app.prompt_context import investigation_history
from .review_packets import supplement, register, visible_financial, packet_coverage, consistency_checks, counter_query


def validate_graph_query(query):
    return ensure_bounded_readonly_rgql(query, max_limit=50)


def assessment_schema(task, evidence_ids):
    work_item = object_schema({"question": {"type": "string", "minLength": 1, "maxLength": 500},
        "requested_record": {"type": "string", "minLength": 1, "maxLength": 500},
        "why_it_matters": {"type": "string", "minLength": 1, "maxLength": 1000},
        "closure_condition": {"type": "string", "minLength": 1, "maxLength": 1000},
        "priority": {"enum": ["High", "Medium", "Low"]},
        "priority_basis": {"type": "string", "minLength": 1, "maxLength": 1000},
        "evidence_ids": {"type": "array", "maxItems": 10, "minItems": 1,
                         "items": {"enum": sorted(evidence_ids)} if evidence_ids else {"type": "string"}}})
    schema = deepcopy(object_schema({"hypothesis": HYPOTHESIS, "report": REPORT,
        "work_items": {"type": "array", "maxItems": 5 if evidence_ids else 0, "items": work_item}}))
    hypothesis = schema["properties"]["hypothesis"]["properties"]
    report = schema["properties"]["report"]["properties"]
    hypothesis["id"] = {"const": task["hypothesis"]["id"]}
    hypothesis["parent_id"] = {"type": "null"}
    finding = report["findings"]["items"]["properties"]
    finding["id"] = {"const": task["prefix"]}
    for parent, name in ((hypothesis, "supporting_evidence"), (hypothesis, "contradictory_evidence"), (finding, "evidence_ids")):
        field = dict(parent[name])
        if evidence_ids:
            field["items"] = {"enum": sorted(evidence_ids)}
        else:
            field["maxItems"] = 0
        parent[name] = field
    if not evidence_ids:
        hypothesis["status"] = {"const": "inconclusive"}
        report["findings"]["maxItems"] = 0
    return schema


@activity_operation('Collecting investigation evidence', completed='Collecting investigation evidence: completed')
def collect_evidence(context, work):
    root, frozen, task = task_input(context, work)
    name = f"case/rounds/{task['prefix']}-evidence.json"
    if (root / name).exists():
        return {"evidence": save(root, name, read(root / name))}
    case = root / "case"
    corpus, _ = validate_indexes(case, frozen["config"]["investigation"]["access_scope"])
    store = EvidenceStore(case / "evidence.sqlite3")
    runtime = bind_skills(case, corpus, store, frozen["investigation_id"],
                         [d["name"] for d in source_manifest(__file__)["skill_dependencies"]],
                         config=frozen['config'], scope=frozen['memory_scope'])
    records = []
    h = task["hypothesis"]
    operations = [(DOC, "search", {"query": h[p + "_query"], "top_k": frozen["config"]["investigation"]["top_k"]}, p) for p in ("support", "counter")]
    operations += [(GRAPH, "query", {"rgql": QUERIES[q]}, "graph") for q in h["graph_tools"] if q in QUERIES]
    for index, (skill, operation, arguments, purpose) in enumerate(operations):
        if skill == GRAPH:
            validate_graph_query(arguments["rgql"])
        runtime.read_skill(skill)
        action = {"name": "invoke_skill", "arguments": {"skill": skill, "operation": operation, "arguments": arguments}, "reason": h["expected_information"]}
        action_path = f"case/rounds/actions/{task['prefix']}-{index:02d}.json"
        if (root / action_path).exists():
            record = read(root / action_path)
            if record["action"] != action or "error" in record["result"]:
                raise ValueError("Committed evidence action changed or previously failed")
        else:
            try:
                result = observe_action(action, {"records": records + [{}]}, lambda *_: runtime.invoke_skill(skill, operation, arguments))
            except Exception as exc:
                save(root, action_path, {"action": action, "result": {"error": str(exc)}, "purpose": purpose})
                raise
            result = cleared_observation(result, frozen["source_review_flags"])
            record = {"action": action, "result": result, "purpose": purpose}
            save(root, action_path, record)
        records.append(record)
    from .source_graph import VIEWS, walk
    from .temporal_evidence import VIEWS as TEMPORAL_VIEWS, walk as temporal_walk
    from mn_sdk_rag import EvidenceSpan
    from .evidence.assistant import EvidenceAssistant
    for view in h['graph_tools']:
        if view not in VIEWS and view not in TEMPORAL_VIEWS:
            continue
        path = f"case/rounds/actions/{task['prefix']}-source-{view}.json"
        if (root/path).exists():
            record = read(root/path)
        else:
            passages = [p for r in records for p in r['result'].get('passages', [])]
            result = (temporal_walk if view in TEMPORAL_VIEWS else walk)(case, corpus, passages, view, frozen['config'])
            record = {'action':{'view':view}, 'purpose':'graph', 'result':result}
            save(root,path,record)
        documents = {d.source_id:d for d in corpus.scan()}
        record['result'] = cleared_observation(record['result'], frozen['source_review_flags'])
        for passage in record['result']['passages']:
            evidence = EvidenceSpan(**passage, provenance_kind='observed')
            EvidenceAssistant._validate_evidence(evidence, documents)
            store.add_evidence(frozen['investigation_id'], evidence)
        records.append(record)
    documents = tuple(corpus.scan())
    extra, _ = supplement(documents, frozen['source_review_flags'], frozen.get('matter', {}), records,
                          frozen['config'].get('text_memory', {}).get('max_context_bytes', 32768) // 2)
    if extra['result']['passages']:
        register(store, frozen['investigation_id'], documents, [extra])
        records.append(extra)
    # Exact spans are verified against frozen source bytes before ledger admission.
    ids = list(dict.fromkeys(p["evidence_id"] for r in records for p in r["result"].get("passages", [])))
    ref = save(root, name, {"hypothesis": h, "records": records, "evidence_ids": ids})
    return {"evidence": ref}


@activity_operation('Assessing the investigation hypothesis', completed='Assessing the investigation hypothesis: completed')
def assess_hypothesis(context, work):
    llm_client = context.resources.get("llm")
    root, frozen, task = task_input(context, work)
    name = f"case/rounds/{task['prefix']}-assessment.json"
    if (root / name).exists():
        from .claim_memory import publish
        publish(root, frozen, task['prefix'], read(root / name))
        return {"assessment": save(root, name, read(root / name))}
    collected = read(root / f"case/rounds/{task['prefix']}-evidence.json")
    store = EvidenceStore(root / "case/evidence.sqlite3")
    allowed = set(collected["evidence_ids"])
    # The 2000-byte limit applies to one proposed finding's citations, not all
    # evidence an assessor may inspect. Retain query rank and interleave support
    # with counterevidence before admitting whole source units.
    by_id = {e.evidence_id:e for e in store.evidence_for(frozen['investigation_id'])}
    support = [p['evidence_id'] for r in collected['records'] if r['purpose']=='support'
               for p in r['result'].get('passages', [])]
    counter = [p['evidence_id'] for r in collected['records'] if r['purpose']=='counter'
               for p in r['result'].get('passages', [])]
    ranked = list(dict.fromkeys([i for pair in zip_longest(support,counter) for i in pair if i]
                               + collected['evidence_ids']))
    spans = [asdict(by_id[id]) for id in ranked if id in allowed
             and by_id[id].source_id not in frozen['source_review_flags']]
    visible = {e["evidence_id"] for e in spans}
    schema = assessment_schema(task, visible)
    instruction = (
        "Assess the committed enquiry from complete visible passages. Keep its exact hypothesis ID and parent_id null. "
        "Cite only visible evidence IDs. Include ordinary alternatives and outstanding enquiries. "
        "With no visible evidence, return inconclusive and an empty findings list. "
        "Propose at most one concise report finding; use the supplied finding_id. Findings are inferred assessments. "
        "A proposed finding may cite at most 2000 UTF-8 bytes of complete passages; seeing additional passages does not waive that limit. "
        "Graph observations are navigation aids, not proof. State unexamined/omitted evidence limits. "
        "Return work_items for decisive missing records or interviews: a specific requested_record, question, "
        "why_it_matters, closure_condition, priority and priority_basis plus current evidence_ids. "
        "These are suggestions for attorney review. Do not invent a custodian, owner, deadline or completed collection. "
        "Preserve distinctions between requested/approved/posted/reversed/settled amounts and loss; no intent or liability follows from arithmetic. "
        "Reconcile your wording with verified_financial, including limited approval, reversals and net balance. "
        "Do not describe available records as missing. Re-read available sources internally; do not request them from counsel again. "
        "Return a short supported answer, its contrary evidence, and the next record that could change the decision.")
    from .evidence_admission import admit, coverage, assess_admitted
    data = {"enquiry": task["hypothesis"], "finding_id": task["prefix"], "evidence": [],
         "omitted_passages": len(allowed - visible),
         "graph_observations": investigation_history([r for r in collected["records"]
             if r["purpose"] == "graph" and 'paths' not in r['result']], max_bytes=2000),
         "search_coverage": coverage(collected['records'], visible)}
    room = min(evidence_room(frozen, "assess", instruction, data, schema),
               max(0, frozen['config'].get('text_memory',{}).get('max_context_bytes',32768)-512))
    from .intake import PreparedCorpus
    documents = PreparedCorpus(root / 'case', frozen['config']['investigation']['access_scope']).scan()
    from .financial_review import build as reconcile
    financial = reconcile(frozen.get('matter', {}), documents, frozen['source_review_flags'])
    # This envelope is budgeted together with evidence, never an uncounted append.
    financial_room = len(json.dumps(visible_financial(financial, financial['evidence']), ensure_ascii=False).encode())
    data.update(admit(spans, collected['records'], max(0, room - financial_room - 512)))
    data['verified_financial'] = visible_financial(financial, data['evidence'])
    visible = {e["evidence_id"] for e in data["evidence"]}
    data["omitted_passages"] = len(allowed - visible)
    for item in data["search_coverage"]:
        item["evidence_ids"] = [e for e in item["evidence_ids"] if e in visible]
    schema = assessment_schema(task, visible)
    from mn_sdk.memory_quality import context_requirements
    requirement = context_requirements(frozen['config'])
    quality = assess_admitted(data, collected['records']) if requirement else None
    if quality:
        save(root, f"case/rounds/{task['prefix']}-context-quality.json", quality)
    if quality and quality['action']=='insufficient_evidence':
        gaps=quality['reasons'][:40]
        value={'hypothesis':{'id':task['hypothesis']['id'],'parent_id':None,
            'question':task['hypothesis']['question'],'status':'inconclusive',
            'factual_basis':'Required source support was not available after bounded retrieval.',
            'supporting_evidence':[], 'contradictory_evidence':[],
            'alternatives':['The available packet cannot resolve the enquiry.'],
            'assessment':'Insufficient evidence; no factual finding was generated.',
            'outstanding_enquiries':gaps},
            'report':{'findings':[],'conclusion_ids':[],'follow_up':gaps}, 'work_items': []}
        validate(schema,value)
    else:
        value = complete(root, frozen, task["prefix"] + "-assess", "assess", instruction, data, schema, llm_client)
    h = value["hypothesis"]
    if h["id"] != task["hypothesis"]["id"] or h["parent_id"] is not None:
        raise ValueError("Assessment changed the committed hypothesis identity")
    cited = set(h["supporting_evidence"] + h["contradictory_evidence"])
    cited.update(e for f in value["report"]["findings"] for e in f["evidence_ids"])
    if not cited <= visible or (h["status"] in ("supported", "contradicted") and not cited):
        raise ValueError("Assessment cites unavailable evidence")
    if any(f["id"] != task["prefix"] for f in value["report"]["findings"]):
        raise ValueError("Finding identity must match committed task")
    admitted_coverage = packet_coverage(data['evidence'], documents)
    data = {"source_review_flags": frozen["source_review_flags"]}
    submit_report(data, value["report"], store, frozen["investigation_id"])
    value["counsel_issue_ids"] = task["hypothesis"].get("counsel_issue_ids", [])
    value['evidence_review_coverage'] = admitted_coverage
    value['model_dispatched'] = not (quality and quality['action']=='insufficient_evidence')
    ref = save(root, name, value)
    from .claim_memory import publish
    publish(root, frozen, task['prefix'], value)
    return {"assessment": ref}


@activity_operation('Reviewing an investigation finding', completed='Reviewing an investigation finding: completed')
def review_finding(context, work):
    llm_client = context.resources.get("llm")
    root, frozen, task = task_input(context, work)
    name = f"case/rounds/{task['prefix']}-review.json"
    if (root / name).exists():
        return {"review": save(root, name, read(root / name))}
    assessment = read(root / f"case/rounds/{task['prefix']}-assessment.json")
    store = EvidenceStore(root / "case/evidence.sqlite3")
    data = {"source_review_flags": frozen["source_review_flags"]}
    submit_report(data, assessment["report"], store, frozen["investigation_id"])
    cited = {i for f in assessment["report"]["findings"] for i in f["evidence_ids"]}
    cited.update(assessment['hypothesis']['supporting_evidence'])
    cited.update(assessment['hypothesis']['contradictory_evidence'])
    schema = deepcopy(REVIEW)
    finding_ids = [f["id"] for f in assessment["report"]["findings"]]
    schema["properties"]["accepted_ids"] = {"type": "array", "uniqueItems": True,
        "maxItems": len(finding_ids), "items": {"enum": finding_ids} if finding_ids else {"type": "string"}}
    from .evidence_admission import review_closure, coverage, admit
    from .intake import PreparedCorpus
    documents = PreparedCorpus(root / 'case', frozen['config']['investigation']['access_scope']).scan()
    corpus, _ = validate_indexes(root / 'case', frozen['config']['investigation']['access_scope'])
    collected = read(root / f"case/rounds/{task['prefix']}-evidence.json")
    records = list(collected['records'])
    # A fresh source search is independent of the assessor's chosen citations.
    query = counter_query(task['hypothesis'], frozen.get('matter', {}))
    action_path = f"case/rounds/{task['prefix']}-review-search.json"
    if (root / action_path).exists():
        independent = read(root / action_path)
    else:
        runtime = bind_skills(root / 'case', corpus, store, frozen['investigation_id'],
            [d['name'] for d in source_manifest(__file__)['skill_dependencies']],
            config=frozen['config'], scope=frozen['memory_scope'])
        runtime.read_skill(DOC)
        result = runtime.invoke_skill(DOC, 'search', {'query':query,
            'top_k':frozen['config']['investigation']['top_k']})
        independent = {'purpose':'independent_counter', 'action':{'query':query},
            'result':cleared_observation(result, frozen['source_review_flags'])}
        save(root, action_path, independent)
    records.append(independent)
    extra, financial = supplement(documents, frozen['source_review_flags'], frozen.get('matter', {}), records,
        frozen['config'].get('text_memory', {}).get('max_context_bytes', 32768) // 2)
    records.append(extra)
    register(store, frozen['investigation_id'], documents, records)
    all_spans = [asdict(e) for e in store.evidence_for(frozen['investigation_id'])
                 if e.source_id not in frozen['source_review_flags']]
    required = review_closure(all_spans, records, cited)
    available_ids = {p['evidence_id'] for r in records for p in r['result'].get('passages', [])} | cited
    spans = required + [e for e in all_spans if e['evidence_id'] in available_ids - {p['evidence_id'] for p in required}]
    if required:
        records.append({'result':{'support_groups':[{'id':'review-cited', 'complete':True, 'required':True,
            'source_evidence_ids':[p['evidence_id'] for p in required]}]}})
    if financial['events'] and finding_ids:
        schema['properties']['financial_checks'] = {'type':'array', 'minItems':len(finding_ids),
            'maxItems':len(finding_ids), 'items':object_schema({
                'finding_id':{'enum':finding_ids}, 'status':{'enum':['consistent','contradiction','unresolved']},
                'record_ids':{'type':'array', 'uniqueItems':True, 'items':{'enum':sorted({e['record_id'] for e in financial['events']})}},
                'reason':{'type':'string', 'minLength':1, 'maxLength':1000}})}
        schema['required'].append('financial_checks')
    instruction = (
        "Independently review the proposed finding against every complete cited passage and its supplied dependencies, "
        "the independent counter-search and verified_financial. Reject claims that available approval, ledger, posting "
        "or reversal records are absent; distinguish accounting net from bank settlement and loss. "
        "Accept only wording supported by these sources, preserving identity uncertainty, competing explanations and incomplete coverage. "
        "Reject overstatement, missing context, unsupported dates or allegations; explain issues concisely. "
        "When financial_checks is requested, return exactly one check per finding and list every supplied financial record_id. "
        "Unresolved reconciliation or contradiction requires rejection. "
        "accepted_ids must contain report finding IDs, NEVER evidence or source IDs. Return [] to reject all. You cannot add evidence or rewrite the finding.")
    packet = {'report':assessment['report'], 'hypothesis':assessment['hypothesis'], 'evidence':[],
        'search_coverage':coverage([r for r in records if 'purpose' in r], available_ids)}
    room = min(evidence_room(frozen, 'review', instruction, packet, schema),
        frozen['config'].get('text_memory', {}).get('max_context_bytes',32768) - 512)
    packet.update(admit(spans, records, max(0,room-len(json.dumps(visible_financial(financial, financial['evidence']),ensure_ascii=False).encode())-512)))
    packet['verified_financial'] = visible_financial(financial, packet['evidence'])
    packet['search_coverage'] = coverage([r for r in records if 'purpose' in r], {e['evidence_id'] for e in packet['evidence']})
    conflicts = consistency_checks(assessment['report'], financial)
    dispatched = cited <= {e['evidence_id'] for e in packet['evidence']}
    if not dispatched:
        value = {'accepted_ids':[], 'issues':['Complete cited dependency packet did not fit review capacity.']}
    else:
        value = complete(root, frozen, task['prefix'] + '-review', 'review', instruction, packet, schema, llm_client)
        checks = value.pop('financial_checks', [])
        if financial['events'] and finding_ids:
            if {c['finding_id'] for c in checks} != set(finding_ids):
                raise ValueError('Financial consistency review must cover every finding exactly once')
            expected = {e['record_id'] for e in financial['events']}
            for check in checks:
                if set(check['record_ids']) != expected or packet['verified_financial']['omitted_event_count']:
                    check['status'] = 'unresolved'
                    check['reason'] = 'Financial record coverage incomplete; do not publish this finding.'
                if check['status'] != 'consistent':
                    value['accepted_ids'] = [i for i in value['accepted_ids'] if i != check['finding_id']]
            conflicts.extend(checks)
    for conflict in conflicts:
        if conflict['status'] != 'consistent':
            value['accepted_ids'] = [i for i in value['accepted_ids'] if i != conflict['finding_id']]
            value['issues'].append(conflict['reason'])
    review_report(data, value)
    value['consistency_checks'] = conflicts
    value['evidence_review_coverage'] = packet_coverage(packet['evidence'], documents)
    value['independent_search'] = action_path
    value['model_dispatched'] = dispatched
    return {'review': save(root, name, value)}


@activity_operation('Summarizing the investigation round', completed='Summarizing the investigation round: completed')
def summarize_round(context, work):
    root, frozen, task = task_input(context, work)
    state = checkpoint(root, frozen)
    findings = [{"id": h["id"], "question": h["question"], "status": h["status"],
                 "assessment": h["assessment"], "counter_evidence": h["contradictory_evidence"],
                 "outstanding_enquiries": h["outstanding_enquiries"]}
                for h in state["data"]["hypotheses"].values()]
    name = f"case/rounds/summary-{task['revision']:02d}.json"
    return {"summary": save(root, name, {"findings": findings, "review": state["data"]["report_review"]})}
