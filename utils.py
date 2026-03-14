"""Utility functions for newsletter generation."""

import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")

def now_pacific() -> datetime:
  return datetime.now(PACIFIC)


def ensure_data_dir(data_dir: Path):
  data_dir.mkdir(exist_ok=True)


def save_newsletter(data_dir: Path, content: str, date: str) -> Path:
  ensure_data_dir(data_dir)
  base_filename = f"newsletter_{date.replace(' ', '_').replace(',', '')}"
  newsletter_file = data_dir / f"{base_filename}.html"
  if newsletter_file.exists():
    counter = 2
    while (data_dir / f"{base_filename}_{counter}.html").exists():
      counter += 1
    newsletter_file = data_dir / f"{base_filename}_{counter}.html"
  newsletter_file.write_text(content)
  return newsletter_file


def open_in_browser(filepath: Path):
  import subprocess
  subprocess.run(["open", str(filepath)])


def clean_html_output(content: str) -> str:
  content = re.sub(r"```html\s*", "", content)
  content = re.sub(r"```\s*", "", content)
  html_match = re.search(
    r"(<!DOCTYPE html>.*?</html>|<html>.*?</html>)",
    content,
    re.DOTALL | re.IGNORECASE,
  )
  if html_match:
    return html_match.group(1)
  return content.strip()


def strip_footer(text: str) -> str:
  if not text:
    return text
  text = re.sub(r"<footer[^>]*>.*?</footer>", "", text, flags=re.DOTALL | re.IGNORECASE)
  text = re.sub(
    r'<div[^>]*>\s*Made by\s*<a[^>]*>jessewgilbert\.com</a>.*?</div>',
    "", text, flags=re.DOTALL | re.IGNORECASE
  )
  return text

def strip_tags(text: str) -> str:
  if not text:
    return ""
  text = strip_footer(text)
  text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
  text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
  text = re.sub(r"<[^>]+>", " ", text)
  text = re.sub(r"[^\S\n]+", " ", text)  # collapse spaces/tabs but keep newlines
  text = re.sub(r" *\n", "\n", text)  # remove trailing spaces before newlines
  text = re.sub(r"\n{3,}", "\n\n", text)  # max 2 newlines
  return text.strip()


def load_recent_newsletters_for_prompt(data_dir: Path, n: int) -> str:
  """Load recent newsletters as plain text (stripped HTML) to avoid repeats.
  Excludes counter-suffixed files (e.g. newsletter_2026-01-16_2.html)."""
  ensure_data_dir(data_dir)
  counter_pattern = re.compile(r"newsletter_.*_\d+\.html$")
  files = sorted(
    f for f in data_dir.glob("newsletter_*.html")
    if "reference" not in f.name and not counter_pattern.match(f.name)
  )[-n:]
  if not files:
    return "<none>No prior newsletters saved.</none>"

  lines = []
  for path in files:
    date = path.stem.replace("newsletter_", "")
    text = strip_tags(path.read_text())
    lines.append(f"<newsletter date=\"{date}\" filename=\"{path.name}\">")
    if text.strip():
      lines.append(f"<text>\n{text}\n</text>")
    else:
      lines.append("<text>No content available.</text>")
    lines.append("</newsletter>")
  return "\n".join(lines)


def load_reference_newsletter(data_dir: Path, filename: str) -> str:
  """Load a specific newsletter as full HTML for format reference."""
  path = data_dir / filename
  if path.exists():
    return strip_footer(path.read_text())
  return ""

