"""Thin specialization of the shared message-driven worker lifecycle."""
from mn_prototype_stateful_step_agent import AgentHandlerOutput, DomainOperationSpec, StatefulStepSpec, create_domain_message_agent, require_child_step_input
from mn_sdk.blueprint_support import StepLifecycleHooks, source_manifest
from mn_sdk.step_runtime import find_message_payload
from runtime.runtime import runtime_context_for_step


def bind(operation):
    keys = frozenset(source_manifest(__file__)["contracts"]["inputs"])
    spec = StatefulStepSpec(
        context_factory=runtime_context_for_step, input_keys=keys,
        hooks=StepLifecycleHooks(runtime_step_mode="agent_invocation"),
    )

    def invoke(context, *, agent_input, llm_client=None, **options):
        payload, references = operation(context.to_mapping(), llm_client=llm_client)
        return AgentHandlerOutput(payload=payload, artifacts=tuple(references))

    return create_domain_message_agent(DomainOperationSpec(
        stateful=spec,
        operation=invoke,
        input_resolver=lambda value: find_message_payload(value.payload, required_keys=keys),
    ))


def bind_child(operation):
    spec = StatefulStepSpec(context_factory=runtime_context_for_step,
        hooks=StepLifecycleHooks(runtime_step_mode="agent_invocation"))

    def invoke(context, *, agent_input, llm_client=None, **options):
        work = require_child_step_input(agent_input)
        return AgentHandlerOutput(payload=operation(context.to_mapping(), work, llm_client=llm_client))

    return create_domain_message_agent(DomainOperationSpec(stateful=spec, operation=invoke, input_resolver=lambda value: {}))
