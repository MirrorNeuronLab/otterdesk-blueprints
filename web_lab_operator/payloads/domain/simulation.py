"""Observe, decide and execute a bounded simulated procedure inside one block."""

import asyncio
import hashlib

from mn_sdk.blueprint.hooks import report_activity
from mn_sdk.blueprint.memory import digest
from mn_sdk_common.files import atomic_write_json

from .decisions import choose
from .lab import SimulatedLab
from .live_ui import LiveLabUi
from .memory import LabMemory, stamp
from .protocol import action_for, goal_results, initial_state, number, validate_plan
from .supervision import event_rows, outcome_notice, publish_notice, risks_for


def run(block, inputs):
    procedure, plan = inputs['procedure'], validate_plan(inputs['plan'], inputs['procedure']['markdown'])
    if hashlib.sha256(procedure['markdown'].encode()).hexdigest() != procedure['sha256']:
        raise ValueError("The supplied procedure identity changed.")
    policy = block.config['simulation']
    if type(policy['max_steps']) is not int or not 1 <= policy['max_steps'] <= 80:
        raise ValueError("max_steps must be in 1..80.")
    number(policy['max_duration_seconds'], 1, 900, 'Procedure duration')
    number(policy['action_delay_seconds'], 0, 2, 'Animation delay')
    if len(plan['steps']) > policy['max_steps']:
        raise ValueError("The procedure exceeds the configured step limit.")
    block.store.commit('plan.json', plan, kind='lab_plan')
    with LabMemory(block, procedure['sha256']) as memory:
        if plan['status'] != 'ready':
            publish_notice(block, 'plan', {'code': 'needs_review', 'title': 'Procedure needs review',
                           'message': 'The simulation did not start. Clarify the plan assumptions and unresolved instructions before another run.'})
            return save(block, plan, procedure, [], initial_state(plan), 'needs_review',
                        'Clarify the plan assumptions and unresolved instructions before starting.', memory)
        return asyncio.run(execute(block, plan, procedure, policy, memory))


async def execute(block, plan, procedure, policy, memory):
    lab, ui = SimulatedLab(plan), None
    trace, status, reason = [], 'running', ''
    state = initial_state(plan)
    projection = {'status': status, 'summary': plan['summary'], 'state': state,
                  'current_step': '', 'operation': None, 'reason': '',
                  'steps_completed': 0, 'steps_total': len(plan['steps']), 'events': []}
    deadline = block.monotonic() + policy['max_duration_seconds']
    block.deadline = min(block.deadline, deadline) if block.deadline is not None else deadline
    check = block.check

    async def tick(operation):
        check()
        projection.update(state=lab.observe(), operation=operation)
        await ui.publish()
        await asyncio.sleep(policy['action_delay_seconds'])

    try:
        await lab.setup()
        ui = LiveLabUi(block, lab.lh, lambda: projection)
        await ui.start()
        state = lab.observe()
        projection['state'] = state
        for index, step in enumerate(plan['steps']):
            check()
            projection['current_step'] = step['id']
            projection['operation'] = {'label': 'Reviewing the next step', 'resource': ''}
            risks = risks_for(step, state)
            projection['events'] = event_rows(trace) + [
                {'step': step['id'], 'decision': 'warning', 'reason': risk['message']} for risk in risks]
            await ui.publish()
            path = f'simulation/steps/{index:03}.json'
            history, memory_ref = await asyncio.to_thread(memory.recall, f'step-{index:03}', step)
            if block.store.path(path).exists():
                # Each attempt creates a new, empty simulation. Reconstruct only
                # confirmed actions; physical robots can never enter this path.
                reference = block.freeze_checkpoint(path, lambda: None)
                event = block.read_checkpoint(reference, expected_path=path)
                if event['before'] != state or event['step'] != step:
                    raise ValueError("Saved simulation evidence differs from this procedure.")
                if event['action'] is not None:
                    if event['error']:
                        raise ValueError("A partly failed simulation cannot resume. Review its evidence and start a new run.")
                    await lab.perform(event['action'], check, lambda _operation: asyncio.sleep(0))
                    if lab.observe() != event['after']:
                        raise ValueError("Replayed simulator state differs from the saved observation.")
            else:
                for risk in risks:
                    await asyncio.to_thread(publish_notice, block, step['id'] + ':before', risk)
                decision = await asyncio.to_thread(choose, block, step, state,
                                                 trace[-1]['outcome'] if trace else None, history)
                check()
                proposal = decision
                error, action, outcome = '', None, {'passed': False}
                try:
                    action = action_for(step, state, decision)
                except ValueError as problem:
                    error = str(problem)
                    decision = {'step_id': step['id'], 'decision': 'pause', 'source': '', 'reason': error}
                if action is not None:
                    report_activity(f"Simulating {step['kind'].replace('_', ' ')}",
                                    owner_blueprint='web_lab_operator', step_id=block.step_id,
                                    run_dir=block.store.run_dir)
                    # A failed/partial backend command is never retried against
                    # the same state. Preserve its observation and end this run.
                    try:
                        outcome = await lab.perform(action, check, tick)
                    except Exception as problem:
                        if getattr(problem, 'code', '') or isinstance(problem, TimeoutError):
                            raise
                        error = f"Simulation command failed ({type(problem).__name__}). Review the observed deck."
                event = {'step': step, 'decision': decision, 'action': action,
                         'proposal': proposal, 'before': state, 'after': lab.observe(), 'outcome': outcome, 'error': error,
                         'observed_at': stamp(block), 'memory_recall': memory_ref, 'risks': risks}
                reference = block.freeze_checkpoint(path, lambda: event)
            trace.append(event)
            state = event['after']
            projection.update(state=state, steps_completed=sum(e['outcome']['passed'] for e in trace),
                              operation=None,
                              reason=event['error'] or ('The volume check did not pass.'
                                     if event['action'] is not None and not event['outcome']['passed'] else event['decision']['reason']),
                              events=event_rows(trace))
            await ui.publish()
            notice = outcome_notice(event)
            if notice:
                await asyncio.to_thread(publish_notice, block, step['id'] + ':after', notice)
            await asyncio.to_thread(memory.remember_step, index, event, reference.to_dict(), plan)
            if event['error'] or event['action'] is None or not event['outcome']['passed']:
                status, reason = 'needs_review', projection['reason'] or 'A volume check did not pass.'
                break
            if event['decision']['decision'] == 'adapt':
                report_activity('Used a declared alternate source after observing insufficient liquid',
                                kind='finding', owner_blueprint='web_lab_operator',
                                step_id=block.step_id, run_dir=block.store.run_dir)
        else:
            met = all(goal['met'] for goal in goal_results(plan, state))
            status = 'completed' if met else 'needs_review'
            reason = 'All simulated steps and final volume goals passed.' if met else 'One or more final volume goals did not pass.'
            if not met:
                await asyncio.to_thread(publish_notice, block, 'goals', {
                    'code': 'needs_review', 'title': 'Final volumes need review',
                    'message': reason + ' Review the saved volume goals before another run.'})
        projection.update(status=status, reason=reason, operation=None)
        await ui.publish()
        return await asyncio.to_thread(save, block, plan, procedure, trace, state, status, reason, memory)
    except BaseException as error:
        status = 'cancelled' if getattr(error, 'code', '') == 'cancelled' else 'failed'
        projection.update(status=status, state=lab.observe(), operation=None)
        if ui is not None:
            await ui.publish()
        # Failure observations are qualified; they do not become successful steps.
        interruption = {
            'status': status, 'state': lab.observe(), 'completed_records': len(trace),
            'steps_completed': sum(event['outcome']['passed'] for event in trace),
            'current_step': projection['current_step'], 'observed_at': stamp(block),
            'error_type': type(error).__name__, 'simulation_only': True}
        evidence = block.store.commit('simulation/interruptions/' + digest(interruption) + '.json',
                                      interruption, kind='interrupted_simulation')
        atomic_write_json(block.store.path('interrupted-simulation.json'), interruption)
        try:
            await asyncio.to_thread(memory.remember_interruption, interruption, evidence.to_dict(), plan)
        except Exception as memory_error:
            # A memory outage must not hide the cancellation/failure that caused
            # cleanup. Its own failure remains inspectable and never means success.
            atomic_write_json(block.store.path('memory-interruption-error.json'), {
                'status': 'failed', 'error_type': type(memory_error).__name__, 'simulation_only': True})
        raise
    finally:
        try:
            if ui is not None:
                await ui.close(status if status in {'failed', 'cancelled'} else 'stopped')
        finally:
            await lab.stop()


def save(block, plan, procedure, trace, state, status, reason, memory):
    trace_ref = block.store.commit('trace.json', {'initial': initial_state(plan), 'events': trace}, kind='lab_trace')
    value = {'schema_version': 'mn.web_lab.simulation.v1', 'status': status,
             'simulation_only': True, 'procedure_sha256': procedure['sha256'],
             'summary': plan['summary'], 'reason': reason, 'state': state,
             'steps_completed': sum(e['outcome']['passed'] for e in trace),
             'steps_total': len(plan['steps']), 'goals': goal_results(plan, state),
             'adaptations': sum(e['decision']['decision'] == 'adapt' and e['outcome']['passed'] for e in trace),
             'trace': trace_ref.to_dict(),
             'plan': block.store.commit('plan.json', plan, kind='lab_plan').to_dict(),
             'procedure': procedure['procedure'],
             'assumptions': plan['assumptions'], 'unresolved': plan['unresolved']}
    memory.remember_result(value, {'trace': value['trace'], 'plan': value['plan'], 'procedure': value['procedure']})
    value['memory'] = block.store.commit('memory.json', memory.audit(procedure['memory_recall']), kind='memory_audit').to_dict()
    artifact = block.store.commit('simulation.json', value, kind='lab_simulation')
    reference = block.commit_checkpoint('simulation-checkpoint.json', value)
    return {'simulation': reference.to_dict(), 'simulation_artifact': artifact.to_dict()}


def verify(block, result):
    value = block.read_checkpoint(result['simulation'], expected_path='simulation-checkpoint.json')
    trace = block.read_evidence(value['trace'])
    if trace['initial'] != initial_state(block.read_evidence(value['plan'])):
        raise ValueError("The simulation trace has an invalid initial deck.")
    final = trace['events'][-1]['after'] if trace['events'] else trace['initial']
    if final != value['state']:
        raise ValueError("The simulation result does not match its final observation.")
    if block.read_evidence(result['simulation_artifact']) != value:
        raise ValueError("The saved simulation result changed.")
    block.read_evidence(value['memory'])
    return True
