defmodule Synaptic.InboxPoller do
  use MirrorNeuron.AgentTemplate

  alias MirrorNeuron.Message

  @impl true
  def init(node) do
    {:ok, %{config: node.config || %{}, scheduled_token: nil}}
  end

  @impl true
  def handle_message(message, state, context) do
    case type(message) do
      "bundle_request" ->
        {:ok, schedule_next_tick(state, context, 0), []}

      "tick" ->
        payload = payload(message) || %{}

        if Map.get(payload, "token") == state.scheduled_token do
          next_state = schedule_next_tick(state, context, interval_ms(state.config))
          {:ok, next_state, [{:emit_to, "inbox_reply_agent", "poll", %{}}]}
        else
          {:ok, state, []}
        end

      _ ->
        {:ok, state, []}
    end
  end

  @impl true
  def recover(state, context) do
    {:ok, schedule_next_tick(state, context, interval_ms(state.config)), []}
  end

  defp schedule_next_tick(state, context, delay_ms) do
    token = :os.system_time(:millisecond)

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
    Map.get(config, "interval_ms", 10_000)
  end
end
