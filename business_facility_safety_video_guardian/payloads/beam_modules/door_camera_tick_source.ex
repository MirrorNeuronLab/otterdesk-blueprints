defmodule MirrorNeuron.Examples.VideoSafetyDoorMonitor.DoorCameraTickSource do
  use MirrorNeuron.AgentTemplate

  alias MirrorNeuron.Message
  alias MirrorNeuron.Runtime

  @impl true
  def init(node) do
    {:ok,
     %{
       config: node.config || %{},
       tick_seq: 0,
       scheduled_token: nil,
       stream_id: nil
     }}
  end

  @impl true
  def handle_message(message, state, context) do
    case type(message) do
      "video_monitor_start" ->
        payload = payload(message) || %{}
        stream_id = payload["stream_id"] || default_stream_id(context)
        {:ok, schedule_next(%{state | stream_id: stream_id}, context, 0), []}

      "tick" ->
        emit_tick(message, state, context)

      _ ->
        {:ok, state, []}
    end
  end

  @impl true
  def recover(%{stream_id: nil} = state, _context), do: {:ok, state, []}

  def recover(state, context) do
    {:ok, schedule_next(state, context, interval_ms(state.config)), []}
  end

  @impl true
  def inspect_state(state) do
    %{
      tick_seq: state.tick_seq,
      stream_id: state.stream_id
    }
  end

  defp emit_tick(message, %{scheduled_token: token} = state, context) do
    if Map.get(payload(message) || %{}, "token") == token do
      stream_id = state.stream_id || default_stream_id(context)
      next_tick = state.tick_seq + 1
      camera_id = Map.get(state.config, "camera_id", "front-door")

      stream = %{
        "stream_id" => stream_id,
        "seq" => next_tick,
        "open" => next_tick == 1
      }

      payload = %{
        "camera_id" => camera_id,
        "tick_seq" => next_tick,
        "source_kind" => "door_camera",
        "sample_requested_at" => DateTime.utc_now() |> DateTime.to_iso8601()
      }

      next_state =
        state
        |> Map.put(:tick_seq, next_tick)
        |> Map.put(:stream_id, stream_id)
        |> Map.put(:scheduled_token, nil)
        |> schedule_next(context, interval_ms(state.config))

      {:ok, next_state,
       [
         {:event, :door_camera_frame_tick_generated,
          %{
            "stream_id" => stream_id,
            "tick_seq" => next_tick,
            "camera_id" => camera_id
          }},
         {:emit_to, target_node(state.config), "door_camera_frame_tick", payload,
          [
            class: "stream",
            content_type: "application/json",
            headers: %{
              "schema_ref" => "com.mirrorneuron.video.door_camera_frame_tick",
              "schema_version" => "1.0.0",
              "stream_role" => "video_monitor"
            },
            stream: stream
          ]}
       ]}
    else
      {:ok, state, []}
    end
  end

  defp emit_tick(_message, state, _context), do: {:ok, state, []}

  defp schedule_next(state, context, delay_ms) do
    token = state.tick_seq + 1

    spawn(fn ->
      if delay_ms > 0 do
        Process.sleep(delay_ms)
      end

      Runtime.deliver(
        context.job_id,
        context.node.node_id,
        Message.new(
          context.job_id,
          context.node.node_id,
          context.node.node_id,
          "tick",
          %{"token" => token},
          class: "control"
        )
      )
    end)

    %{state | scheduled_token: token}
  end

  defp default_stream_id(context), do: "#{context.job_id}:#{context.node.node_id}:video"

  defp interval_ms(config), do: max(Map.get(config, "interval_ms", 5000), 250)

  defp target_node(config), do: Map.get(config, "target_node", "person_detector")
end
