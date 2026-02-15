"""Minimal agent wrapper for newsletter generation."""

from __future__ import annotations
import os
from dataclasses import dataclass

from agents import Agent as BaseAgent, Runner, ModelSettings
from agents.run import RunResult

from logger import log_usage, log_info


MODEL_PRICING: dict[str, tuple[float, float]] = {
  # (input_price, output_price) per million tokens
  "anthropic/claude-opus-4.5": (5.0, 25.0),
  "anthropic/claude-sonnet-4.5": (3.0, 15.0),
  "anthropic/claude-haiku-4.5": (1.0, 5.0),
  "openai/gpt-5.2": (1.75, 14.0),
  "google/gemini-3-pro-preview": (2.0, 12.0),
  "google/gemini-3-flash-preview": (0.5, 3.0),
  "default": (3.0, 15.0),
}


def get_pricing_for_model(model_name: str) -> tuple[float, float]:
  return MODEL_PRICING.get(model_name, MODEL_PRICING["default"])


@dataclass
class UsageStats:
  input_tokens: int = 0
  output_tokens: int = 0
  requests: int = 0

  def add(self, input_tokens: int, output_tokens: int) -> None:
    self.input_tokens += input_tokens
    self.output_tokens += output_tokens
    self.requests += 1

  def reset(self) -> None:
    self.input_tokens = 0
    self.output_tokens = 0
    self.requests = 0

  def to_dict(self) -> dict:
    return {
      "input_tokens": self.input_tokens,
      "output_tokens": self.output_tokens,
      "total_tokens": self.input_tokens + self.output_tokens,
      "requests": self.requests,
    }


def openrouter_model(model: str):
  """Return a LiteLLM-backed model configured for OpenRouter."""
  full_model = model if model.startswith("openrouter/") else f"openrouter/{model}"
  from agents.extensions.models.litellm_model import LitellmModel
  return LitellmModel(
    model=full_model,
    api_key=os.getenv("OPENROUTER_API_KEY"),
  )


class Agent:
  """Minimal agent wrapper with OpenRouter support and cost tracking."""

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
    self._model_name = model
    self._usage = UsageStats()
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

  async def run(self, input_text: str, *, max_turns: int | None = None) -> RunResult:
    from agents import RunConfig
    config = None
    if self.default_model_settings:
      config = RunConfig(model_settings=self.default_model_settings)
    result = await Runner.run(
      self._agent,
      input=input_text,
      max_turns=max_turns or self.default_max_turns,
      run_config=config,
    )
    for response in result.raw_responses:
      if response.usage:
        self._usage.add(response.usage.input_tokens, response.usage.output_tokens)
    return result

  def get_usage(self) -> dict:
    return self._usage.to_dict()

  def get_cost(self) -> float:
    pricing = get_pricing_for_model(self._model_name)
    input_cost = (self._usage.input_tokens / 1_000_000) * pricing[0]
    output_cost = (self._usage.output_tokens / 1_000_000) * pricing[1]
    return input_cost + output_cost

  def reset_usage(self) -> None:
    self._usage.reset()

  def print_usage(self) -> None:
    usage = self.get_usage()
    cost = self.get_cost()
    print(f"\n\033[36m--- Usage Summary ---\033[0m")
    print(f"Model: {self._model_name}")
    print(f"Requests: {usage['requests']}")
    print(f"Input tokens: {usage['input_tokens']:,}")
    print(f"Output tokens: {usage['output_tokens']:,}")
    print(f"Total tokens: {usage['total_tokens']:,}")
    print(f"\033[32mEstimated cost: ${cost:.4f}\033[0m")
    log_usage(self._model_name, usage['input_tokens'], usage['output_tokens'], cost)
