"""Qualified architecture review outcomes as authored runtime Markdown."""
from datetime import datetime, timezone
import json

from mn_sdk.text_memory import runtime_text_memory
from .catalog_store import fingerprint


def declare_runtime_schema(memory, snapshot_id):
    """Declare query fields before the first review; never a review observation."""
    from mn_context_engine_sdk.intelligent_system import RuntimeRecord
    key=['architecture-review-schema',snapshot_id,memory.scope]
    clock=memory.restore_checkpoint(key)
    if clock is None:
        clock={'declared_at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z')}
        memory.checkpoint(key,clock)
    record=RuntimeRecord('architecture-schema-'+fingerprint(key),
        'Architecture review schema',clock['declared_at'],
        'schema_declaration_not_review_observation',
        fields={'memory_family':'architecture_schema','snapshot_id':snapshot_id,'aspect_id':''},
        kind='constraint')
    memory.record(record,namespace='job',event_id=key,allow=['architecture'])


def runtime_result(result, snapshot_id, published_at):
    from mn_context_engine_sdk.intelligent_system import RuntimeRecord
    content = {key:result[key] for key in ['task_id','kind','status','aspect_id','scope',
        'conclusion','limitations','analysis_verdict','claims','observations'] if key in result}
    # Runtime-created claims remain complete. Their source citations are
    # locators; original excerpt bodies remain in the original source corpus.
    for key in ('claims','observations'):
        content[key] = [{**item, **{field:[{k:v for k,v in ref.items() if k!='excerpt'}
            for ref in item[field]] for field in ('evidence','counterevidence_citations') if field in item}}
            for item in content.get(key,[])]
    fields = {'memory_family':'architecture_review','snapshot_id':snapshot_id,
              'task_id':content['task_id'],'task_kind':content['kind'],'status':content['status']}
    for key in ('aspect_id','scope','conclusion','analysis_verdict'):
        if isinstance(content.get(key),str) and len(content[key])<=256:
            fields[key] = content[key]
    def cell(value):
        return json.dumps(value,ensure_ascii=False,allow_nan=False).replace('|','\\u007c')
    notes = ['Validated scoped review outcome; it is navigation, not proof of runtime execution.',
             'Source claims require current original evidence and explicit counterevidence.',
             '', '| detail | value |','| --- | --- |']
    for key,value in content.items():
        if key not in fields or fields[key]!=value:
            notes.append('| '+cell(key)+' | '+cell(value)+' |')
    return RuntimeRecord('architecture-'+fingerprint([snapshot_id,content]),
        'Architecture review '+content['task_id'],published_at,'validated_scoped_review',
        fields=fields,notes='\n'.join(notes),kind='decision')


def publish_runtime_notes(store, saved):
    request = saved['request']
    memory = runtime_text_memory(request['retrieval_config'],principal='architecture',
                                 scope=request['memory_scope'])
    if memory is None:
        return
    try:
        for task_id,result in store.results().items():
            marker = f'catalog/memory/{task_id}.json'
            if store.path(marker).exists():
                continue
            key = ['architecture-publication',request['snapshot'],task_id]
            clock = memory.restore_checkpoint(key)
            if clock is None:
                clock = {'published_at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z')}
                memory.checkpoint(key,clock)
            record = runtime_result(result,request['snapshot'],clock['published_at'])
            receipt = memory.record(record,event_id=['result',task_id],allow=['architecture'],
                upstream=[{'source_ref':f'catalog/results/{task_id}.json'}])
            store.write(marker,{'source_id':receipt['source_id'],'revision':receipt['revision']})
    finally:
        memory.close()
