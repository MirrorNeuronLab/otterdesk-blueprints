defmodule Synaptic.MonitorScheduler do
  use MirrorNeuron.AgentTemplate

  alias MirrorNeuron.Message

  @impl true
  def init(node) do
    {:ok,
     %{
       config: node.config || %{},
       cycle: 0,
       scheduled_token: nil,
       latest_plan: nil
     }}
  end

  @impl true
  def handle_message(message, state, context) do
    case type(message) do
      "cycle_trigger" ->
        payload = payload(message) || %{}
        next_plan = Map.get(payload, "original_plan", state.latest_plan)
        next_cycle = Map.get(payload, "cycle", state.cycle + 1)

        {:ok,
         schedule_next_tick(
           %{state | latest_plan: next_plan, cycle: max(next_cycle - 1, 0)},
           context,
           interval_ms(state.config)
         ), []}

      "tick" ->
        maybe_emit_scheduled_plan(message, state)

      _ ->
        plan =
          (payload(message) || %{})
          |> Map.put("runtime_job_id", context.job_id)

        {:ok,
         schedule_next_tick(
           %{state | latest_plan: plan, cycle: 0},
           context,
           0
         ), []}
    end
  end

  @impl true
  def recover(state, context) do
    if state.latest_plan do
      {:ok, schedule_next_tick(state, context, interval_ms(state.config)), []}
    else
      {:ok, state, []}
    end
  end

  @impl true
  def inspect_state(state) do
    %{
      cycle: state.cycle,
      scheduled_token: state.scheduled_token,
      has_plan: not is_nil(state.latest_plan)
    }
  end

  defp maybe_emit_scheduled_plan(message, %{scheduled_token: token, latest_plan: plan} = state) do
    payload = payload(message) || %{}

    cond do
      is_nil(plan) ->
        {:ok, state, []}

      Map.get(payload, "token") != token ->
        {:ok, state, []}

      true ->
        next_cycle = state.cycle + 1
        scheduled_at = DateTime.utc_now() |> DateTime.truncate(:second) |> DateTime.to_iso8601()

        next_plan =
          plan
          |> Map.put("cycle", next_cycle)
          |> Map.put("scheduled_at", scheduled_at)

        next_state = %{state | cycle: next_cycle, scheduled_token: nil, latest_plan: next_plan}

        {:ok, next_state,
         [
           {:event, :monitor_cycle_scheduled,
            %{
              "cycle" => next_cycle,
              "customer_id" => get_in(next_plan, ["customer", "customer_id"]),
              "scheduled_at" => scheduled_at
            }},
           {:emit_to, "customer_research_agent", "plan_cycle", next_plan}
         ]}
    end
  end

  defp maybe_emit_scheduled_plan(_message, state), do: {:ok, state, []}

  defp schedule_next_tick(state, context, delay_ms) do
    token = state.cycle + 1

    Process.send_after(
      self(),
      {:mirror_neuron_scheduled_message,
       Message.new(
         context.job_id,
         context.node.node_id,
         context.node.node_id,
         "tick",
         %{"token" => token},
         class: "control"
       )},
      delay_ms
    )

    %{state | scheduled_token: token}
  end

  defp interval_ms(config) do
    if fast_test_mode?(config) do
      0
    else
      configured_interval_ms(config)
    end
  end

  defp configured_interval_ms(config) do
    case Map.get(config, "interval_ms", 60_000) do
      value when is_integer(value) and value >= 0 -> value
      _ -> 60_000
    end
  end

  defp fast_test_mode?(config) do
    Map.get(config, "fast_test_mode", false) == true
  end
end
