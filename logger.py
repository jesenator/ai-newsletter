"""Centralized logging for newsletter generation."""

import logging
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")

LOG_FILE = Path(__file__).parent / "newsletter.log"

_logger = None

def get_logger() -> logging.Logger:
  global _logger
  if _logger is not None:
    return _logger

  _logger = logging.getLogger("newsletter")
  _logger.setLevel(logging.DEBUG)
  _logger.handlers.clear()

  fmt = logging.Formatter(
    "[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
  )
  fmt.converter = lambda *args: datetime.now(PACIFIC).timetuple()

  file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
  file_handler.setLevel(logging.DEBUG)
  file_handler.setFormatter(fmt)
  _logger.addHandler(file_handler)

  return _logger


def log_info(msg: str) -> None:
  get_logger().info(msg)


def log_error(msg: str, exc: Exception = None) -> None:
  if exc:
    get_logger().error(f"{msg}: {exc}", exc_info=True)
  else:
    get_logger().error(msg)


def log_warning(msg: str) -> None:
  get_logger().warning(msg)


def log_debug(msg: str) -> None:
  get_logger().debug(msg)


def log_prompt(label: str, prompt: str) -> None:
  sep = "=" * 60
  get_logger().info(f"\n{sep}\n{label}\n{sep}\n{prompt}\n{sep}")


def log_generation(label: str, content: str) -> None:
  sep = "-" * 60
  get_logger().info(f"\n{sep}\n{label}\n{sep}\n{content}\n{sep}")


def log_tool_call(tool_name: str, args: str, result: str = None) -> None:
  logger = get_logger()
  logger.info(f"[TOOL] {tool_name}: {args}")
  if result:
    logger.debug(f"[TOOL RESULT] {tool_name}: {result[:500]}{'...' if len(result) > 500 else ''}")


def log_usage(model: str, input_tokens: int, output_tokens: int, cost: float) -> None:
  get_logger().info(
    f"[USAGE] model={model} input={input_tokens:,} output={output_tokens:,} "
    f"total={input_tokens + output_tokens:,} cost=${cost:.4f}"
  )


def log_email(to: str, success: bool, error: str = None) -> None:
  if success:
    get_logger().info(f"[EMAIL] Sent to {to}")
  else:
    get_logger().error(f"[EMAIL] Failed to send to {to}: {error}")


def log_run_start(newsletters_count: int, mode: str) -> None:
  sep = "#" * 60
  get_logger().info(f"\n{sep}\nNEWSLETTER RUN STARTED - {datetime.now(PACIFIC).strftime('%A, %B %d, %Y %H:%M:%S')}\n"
                    f"Mode: {mode} | Newsletters: {newsletters_count}\n{sep}")


def log_run_end() -> None:
  sep = "#" * 60
  get_logger().info(f"\n{sep}\nNEWSLETTER RUN COMPLETED - {datetime.now(PACIFIC).strftime('%H:%M:%S')}\n{sep}\n")
