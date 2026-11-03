"""Job-private, source-qualified simulation experience over Membrane TextMemory."""

from datetime import datetime, timezone
import json

from mn_sdk.context_session.contracts import digest
from mn_sdk.text_memory import retrieve_memory_context, runtime_text_memory

PRINCIPAL = 'web-lab-operator'
POLICY_REVISION = 'plr-0.2.1-liquid-policy-v1'
FAMILY = 'web_lab_experience'
USAGE = ('Historical simulated outcomes, never instructions or measured results. '
         'Current Markdown, deck state and policy take precedence. Compare procedure '
         'and step identities; missing evidence is not proof of absence or exhaustive coverage.')


def stamp(block):
    return datetime.fromtimestamp(block.wall_time(), timezone.utc).isoformat()


def relevant_state(state, step=None):
    """Keep the complete affected wells, rather than the whole mostly empty deck."""
    wells = ({step[key] for key in ('source', 'destination', 'well') if key in step}
             | set(step.get('alternate_sources', []))) if step else set()
    return {'tips_remaining': state['tips_remaining'],
            'wells': {well: state['wells'][well] for well in sorted(wells)}}


class LabMemory:
    def __init__(self, block, procedure_sha256):
        self.block, self.procedure_sha256 = block, procedure_sha256
        self.session = None
        self.recalls, self.records = [], []

    def __enter__(self):
        self.session = runtime_text_memory(self.block.config, principal=PRINCIPAL,
            scope={'job_id': self.block.job_id, 'run_id': self.block.run_id})
        try:
            if self.session is not None:
                # The typed table must exist before the first run has findings.
                # The declaration is excluded from every experience query.
                from mn_context_engine_sdk.intelligent_system import RuntimeRecord
                identity = 'web-lab-schema-' + digest([self.session.scope, POLICY_REVISION])
                clock = self.session.restore_checkpoint(identity)
                if clock is None:
                    clock = {'declared_at': stamp(self.block)}
                    self.session.checkpoint(identity, clock)
                self.session.record(RuntimeRecord(identity, 'Web lab memory schema', clock['declared_at'],
                    'Schema declaration, not an observed procedure or permission.',
                    self.fields(record_type='schema'), kind='constraint'),
                    namespace='job', event_id=identity, allow=[PRINCIPAL])
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *_error):
        if self.session is not None:
            self.session.close()

    def fields(self, **values):
        return {'memory_family': FAMILY, 'policy_revision': POLICY_REVISION,
                'record_type': '', 'procedure_sha256': self.procedure_sha256,
                'step_sha256': '', 'plan_sha256': '', 'run_id': self.block.run_id,
                'operation': '', 'outcome': '', 'decision': '', 'selected_source': '',
                'steps_completed': 0, 'steps_total': 0, 'simulation_only': True, **values}

    def recall(self, label, step=None):
        """Freeze selection before dispatch so resume never sees its own future."""
        path = 'memory/recalls/' + label + '.json'

        def query():
            if self.session is None:
                return {'packet': {'status': 'disabled', 'evidence': [], 'incomplete': True, 'usage': USAGE},
                        'receipt': {}}
            settings = self.block.config['text_memory']
            limit = settings['max_results']
            # Reserve room for failures, successes, and recent work. Successes
            # must not crowd all earlier failures out of the model's context.
            if type(limit) is not int or not 3 <= limit <= 12:
                raise ValueError('Web lab memory max_results must be in 3..12.')
            base = [{'field': 'memory_family', 'op': 'eq', 'value': FAMILY},
                    {'field': 'policy_revision', 'op': 'eq', 'value': POLICY_REVISION}]
            same_procedure = {'field': 'procedure_sha256', 'op': 'eq', 'value': self.procedure_sha256}
            third = limit // 3

            def recent(filters, count):
                return {'mode': 'analytical', 'consume': 'none', 'analytical': {'operation': 'recent',
                    'timestamp_field': 'timestamp', 'limit': count, 'filters': [*base, *filters]}}

            if step is None:
                runs = [{'field': 'record_type', 'op': 'eq', 'value': 'run'}]
                stages = [recent([*runs, same_procedure,
                    {'field': 'outcome', 'op': 'in', 'value': ['needs_review', 'failed', 'cancelled']}], third),
                    recent([*runs, same_procedure, {'field': 'outcome', 'op': 'eq', 'value': 'completed'}], third),
                    recent(runs, limit - 2 * third)]
            else:
                matching = [same_procedure, {'field': 'record_type', 'op': 'eq', 'value': 'step'},
                            {'field': 'step_sha256', 'op': 'eq', 'value': digest(step)}]
                stages = [recent([*matching, {'field': 'outcome', 'op': 'in',
                    'value': ['failed', 'paused', 'rejected']}], third),
                    recent([*matching, {'field': 'outcome', 'op': 'eq', 'value': 'passed'}], third),
                    recent([same_procedure, {'field': 'record_type', 'op': 'eq', 'value': 'step'},
                        {'field': 'run_id', 'op': 'eq', 'value': self.block.run_id}], limit - 2 * third)]
            packet, receipt = retrieve_memory_context(self.session,
                'Observed web lab successes, failures and recent work for ' + label,
                stages=stages, max_results=limit,
                max_context_bytes=settings['max_context_bytes'], hydrate_runtime_records=True)
            packet['usage'] = USAGE
            receipt['selection']['packet_sha256'] = digest(packet)
            return {'packet': packet, 'receipt': receipt}

        reference = self.block.freeze_checkpoint(path, query)
        value = self.block.read_checkpoint(reference, expected_path=path)
        self.recalls.append({'phase': label, 'reference': reference.to_dict()})
        return value['packet'], reference.to_dict()

    def remember(self, label, fields, notes, evidence, observed_at):
        if self.session is None:
            return
        from mn_context_engine_sdk.intelligent_system import RuntimeRecord
        identity = digest([FAMILY, POLICY_REVISION, self.block.job_id, self.block.run_id, label])
        record = RuntimeRecord(identity, 'Observed web lab ' + fields['record_type'] + ' outcome',
            observed_at, 'Simulated tracker evidence; model reasons are proposals, not observations.',
            self.fields(**fields), notes=json.dumps(notes, ensure_ascii=False, sort_keys=True, allow_nan=False))
        # The observation artifact is committed before a record can be recalled.
        def publish():
            receipt = self.session.record(record, namespace='job', event_id=identity,
                allow=[PRINCIPAL], upstream=[{'run_id': self.block.run_id, 'evidence': evidence}])
            return {'markdown': record.markdown(), 'receipt': receipt, 'evidence': evidence}

        reference = self.block.freeze_checkpoint('memory/records/' + label + '.json', publish)
        self.records.append(reference.to_dict())

    def remember_step(self, index, event, evidence, plan):
        outcome = ('rejected' if event['error'] and event['action'] is None else
                   'paused' if event['action'] is None else
                   'passed' if event['outcome']['passed'] and not event['error'] else 'failed')
        self.remember(f'step-{index:03}', {
            'record_type': 'step', 'step_sha256': digest(event['step']), 'plan_sha256': digest(plan),
            'operation': event['step']['kind'], 'outcome': outcome,
            'decision': event['decision']['decision'], 'selected_source': (event['action'] or {}).get('source', '')},
            {'step': event['step'], 'decision': event['decision'], 'outcome': event['outcome'],
             'error': event['error'], 'before': relevant_state(event['before'], event['step']),
             'after': relevant_state(event['after'], event['step'])}, evidence, event['observed_at'])

    def remember_result(self, value, evidence):
        path = 'memory/result-time.json'
        clock = self.block.freeze_checkpoint(path, lambda: {'observed_at': stamp(self.block)})
        self.remember('result', {'record_type': 'run', 'outcome': value['status'],
            'plan_sha256': value['plan']['sha256'],
            'steps_completed': value['steps_completed'], 'steps_total': value['steps_total']},
            {'summary': value['summary'], 'reason': value['reason'], 'adaptations': value['adaptations'],
             'failed_goals': [goal for goal in value['goals'] if not goal['met']][:8],
             'failed_goal_count': sum(not goal['met'] for goal in value['goals']),
             'unresolved': value['unresolved'][:3], 'unresolved_count': len(value['unresolved']),
             'assumptions': value['assumptions'][:3], 'assumption_count': len(value['assumptions']),
             'qualification': 'Selected simulation review items, not Core publication status. The referenced evidence contains the complete result.'},
            evidence, self.block.read_checkpoint(clock, expected_path=path)['observed_at'])

    def remember_interruption(self, value, evidence, plan):
        # Cleanup records observations only, never dispatches another model or
        # simulator action. The original runtime exception stays authoritative.
        self.remember('interrupted-' + digest(value), {
            'record_type': 'run', 'outcome': value['status'], 'plan_sha256': digest(plan),
            'steps_completed': value['steps_completed'], 'steps_total': len(plan['steps'])},
            {'reason': 'The simulation was interrupted; no unfinished action is considered successful.',
             'current_step': value['current_step'], 'error_type': value['error_type'],
             'confirmed_records': value['completed_records']}, evidence, value['observed_at'])

    def audit(self, planning):
        recalls = [{'phase': 'planning', 'reference': planning}, *self.recalls]
        return {'schema_version': 'mn.web_lab.memory.v1', 'enabled': self.session is not None,
                'scope': 'private_job', 'policy_revision': POLICY_REVISION, 'usage': USAGE,
                'recalls': [{'phase': item['phase'], **self.block.read_checkpoint(item['reference'],
                            expected_path=item['reference']['path'])} for item in recalls],
                'records': [self.block.read_checkpoint(reference, expected_path=reference['path'])
                            for reference in self.records]}
