"""Thin binding to the shared route-neutral agent lifecycle."""
from mn_prototype_stateful_step_agent import AgentHandlerOutput, DomainOperationSpec, StatefulStepSpec, create_domain_message_agent
from mn_sdk.blueprint_support import StepLifecycleHooks
from mn_sdk.step_runtime import find_message_payload
from runtime.runtime import runtime_context_for_step


def bind(operation):
    keys = frozenset()
    spec = StatefulStepSpec(context_factory=runtime_context_for_step, input_keys=keys,
                            hooks=StepLifecycleHooks(runtime_step_mode="agent_invocation"))
    def invoke(context, *, agent_input, **options):
        payload, refs = operation(context.to_mapping())
        return AgentHandlerOutput(payload=payload, artifacts=tuple(refs))
    return create_domain_message_agent(DomainOperationSpec(stateful=spec, operation=invoke,
        input_resolver=lambda value: find_message_payload(value.payload, required_keys=keys)))
