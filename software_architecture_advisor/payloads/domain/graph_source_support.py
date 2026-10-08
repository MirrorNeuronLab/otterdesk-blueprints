"""Complete static graph support in the explicit context-service-disabled profile."""
from mn_context_source_code import PythonCodeAdapter
from mn_context_engine_sdk.intelligent_system import TextDocumentAdapter
from mn_context_engine_sdk.intelligent_system.sources import dependency_closure
from mn_context_engine_sdk.intelligent_system.source_context import line_offsets
from .review_prompts import evidence_record


def local_support(snapshot, witnesses):
    adapters, evidence, bound, unresolved = {}, {}, {}, []
    for witness_id, witness in witnesses.items():
        path = witness['path']; source = snapshot['sources'][path]; text = source['text']
        if path not in adapters:
            try:
                sections = (PythonCodeAdapter() if path.endswith('.py') else TextDocumentAdapter()).sections(text,path)
            except SyntaxError:
                sections = TextDocumentAdapter().sections(text,path)
            adapters[path] = sections
        sections = adapters[path]
        roots = [s for s in sections if s.start_line <= witness['line_start'] <= witness['line_end'] <= s.end_line]
        if not roots:
            bound[witness_id] = []; unresolved.append('source_unit_unresolved')
            continue
        width = min(s.end_line-s.start_line for s in roots)
        selected = dependency_closure(sections,[s for s in roots if s.end_line-s.start_line == width])
        if len(selected)>128:
            bound[witness_id] = []; unresolved.append('source_span_capacity_exceeded')
            continue
        offsets = line_offsets(text); body = text.encode(); aliases=[]
        for section in selected:
            a = section.start_byte if section.start_byte is not None else offsets[section.start_line-1]
            b = section.end_byte if section.end_byte is not None else offsets[section.end_line]
            start,end = len(body[:a].decode()),len(body[:b].decode())
            record = evidence_record({'path':path,'sha256':source['sha256'],'start_offset':start,'end_offset':end,
                'start_line':section.start_line,'end_line':section.end_line,'text':body[a:b].decode()})
            evidence[record['id']] = record; aliases.append(record['id'])
        bound[witness_id] = list(dict.fromkeys(aliases))
    return bound,list(evidence.values()),list(dict.fromkeys(unresolved))
