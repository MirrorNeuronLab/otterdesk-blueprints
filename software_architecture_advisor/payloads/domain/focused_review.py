"""Tech-lead review scope; reusable extraction stays in the static-code skill."""

# Boundaries, coupling, change impact, hotspot prioritization, evolution and next decisions.
ASPECTS = ('AR-02-01', 'AR-04-02', 'AR-05-03', 'AR-06-07', 'AR-22-04', 'AR-23-08')


def tasks(catalog, packets, max_tasks):
    selected = set(ASPECTS)
    if not selected <= catalog['specs'].keys():
        raise ValueError('Focused review references unknown report aspects')
    sections = [s for s in catalog['sections'] if selected.intersection(s['aspect_ids'])]
    result = [{'task_id':'analysis-'+a, 'kind':'aspect_analysis', 'aspect_id':a} for a in ASPECTS]
    result += [{'task_id':'challenge-'+a, 'kind':'aspect_challenge', 'aspect_id':a} for a in ASPECTS]
    result += [{'task_id':f"section-{s['number']:02d}", 'kind':'section_synthesis', 'section':s['number']} for s in sections]
    result += [{'task_id':'executive', 'kind':'executive_synthesis'}]
    if len(result) > max_tasks:
        raise ValueError('Focused review task budget cannot fit analysis, challenge and synthesis')
    return result, {'omitted_packets':0, 'omitted_packet_ids':[], 'omitted_packet_paths':[],
                    'truncated':False, 'total_tasks':len(result), 'profile':'focused',
                    'source_scan_policy':'No model inventory scans; static analysis covers the captured inventory and targeted source review remains bounded.',
                    'model_unscanned_packets':len(packets),
                    'unselected_aspects':sorted(catalog['specs'].keys()-selected)}
