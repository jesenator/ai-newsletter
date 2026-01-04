"""Minimal agent wrapper for newsletter generation."""

from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal

from agents import Agent as BaseAgent, Runner, ModelSettings
from agents.run import RunResultStreaming
from agents.stream_events import StreamEvent
from agents.items import MessageOutputItem
from agents import ItemHelpers
from openai.types.responses import ResponseTextDeltaEvent


def openrouter_model(model: str):
  """Return a LiteLLM-backed model configured for OpenRouter."""
  full_model = model if model.startswith("openrouter/") else f"openrouter/{model}"
  from agents.extensions.models.litellm_model import LitellmModel
  return LitellmModel(
    model=full_model,
    api_key=os.getenv("OPENROUTER_API_KEY"),
  )


@dataclass
class AgentEvent:
  kind: Literal["agent_started", "message_delta", "message", "tool_call", "tool_result", "raw"]
  text: str | None = None
  agent_name: str | None = None
  tool_name: str | None = None
  arguments: str | None = None
  call_id: str | None = None
  output: str | None = None
  raw_event: StreamEvent | None = None


class AgentStream:
  def __init__(self, result: RunResultStreaming) -> None:
    self.result = result
    self._iterator: AsyncIterator[StreamEvent] | None = None
    self._consumed = False

  def __aiter__(self) -> "AgentStream":
    if self._iterator is None:
      self._iterator = self.result.stream_events().__aiter__()
    return self

  async def __anext__(self) -> AgentEvent:
    if self._iterator is None:
      self._iterator = self.result.stream_events().__aiter__()
    try:
      event = await self._iterator.__anext__()
    except StopAsyncIteration:
      self._iterator = None
      self._consumed = True
      raise
    return self._simplify_event(event)

  @property
  def final_output(self) -> Any:
    return self.result.final_output

  def _simplify_event(self, event: StreamEvent) -> AgentEvent:
    if event.type == "agent_updated_stream_event":
      return AgentEvent(kind="agent_started", agent_name=event.new_agent.name, raw_event=event)
    if event.type == "run_item_stream_event":
      item = event.item
      if item.type == "message_output_item":
        return AgentEvent(kind="message", text=ItemHelpers.text_message_output(item), raw_event=event)
      if item.type == "tool_call_item":
        raw = item.raw_item
        return AgentEvent(
          kind="tool_call",
          tool_name=getattr(raw, "name", None),
          arguments=getattr(raw, "arguments", None),
          call_id=getattr(raw, "call_id", None),
          raw_event=event,
        )
      if item.type == "tool_call_output_item":
        raw = item.raw_item
        output = item.output if isinstance(item.output, str) else str(item.output)
        return AgentEvent(
          kind="tool_result",
          tool_name=getattr(raw, "type", None),
          call_id=getattr(raw, "call_id", None),
          output=output,
          raw_event=event,
        )
      return AgentEvent(kind="raw", raw_event=event)
    if event.type == "raw_response_event":
      data = event.data
      if isinstance(data, ResponseTextDeltaEvent):
        delta = data.delta or ""
        if delta:
          return AgentEvent(kind="message_delta", text=delta, raw_event=event)
      return AgentEvent(kind="raw", raw_event=event)
    return AgentEvent(kind="raw", raw_event=event)


class Agent:
  """Minimal agent wrapper with OpenRouter support."""

  def __init__(
    self,
    *,
    name: str,
    instructions: str,
    tools: list | None = None,
    model: str = "anthropic/claude-opus-4.5",
    default_max_turns: int = 20,
    default_model_settings: ModelSettings | None = None,
  ) -> None:
    if "/" in model:
      model = openrouter_model(model)
    self._agent = BaseAgent(
      name=name,
      model=model,
      instructions=instructions,
      tools=tools or [],
    )
    self.default_max_turns = default_max_turns
    self.default_model_settings = default_model_settings

  def stream(self, input_text: str, *, max_turns: int | None = None) -> AgentStream:
    from agents import RunConfig
    config = None
    if self.default_model_settings:
      config = RunConfig(model_settings=self.default_model_settings)
    run_result = Runner.run_streamed(
      self._agent,
      input=input_text,
      max_turns=max_turns or self.default_max_turns,
      run_config=config,
    )
    return AgentStream(run_result)

